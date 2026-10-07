"""Bounded, resumable public capture using gzip pages and metadata-only SQLite.

The final concatenated gzip decompresses to canonical JSONL. Manifest bytes and
sha256 describe that JSONL; compressed transport identity is recorded separately.
No SQLite copy of source payloads and no uncompressed output are written here.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date, datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import uuid
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from analytics311.capture import (BASE_URL, FIELD_TYPES, SELECT, QUARANTINE_CODES,
    SocrataClient, _Requests, _count, _job_lock, _json, _load, _metadata, _record,
    _revision, _save, _sha, _utc_now)
from analytics311.errors import AnalyticsError

MAX_STORAGE = 500_000_000
MIN_FREE = 1_000_000_000
RESERVE = 1_048_576


def require(condition, code, message):
    if not condition:
        raise AnalyticsError(code, message)


def regular(path, *, allow_shared=False):
    require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(),
            "output_conflict", "Capture paths must not be links or junctions.")
    if path.exists():
        require(path.is_file() and (allow_shared or path.stat().st_nlink == 1), "output_conflict", "Capture file must be a regular, unshared file.")


def paths(output):
    output = Path(os.path.abspath(output))
    require(output.name.endswith(".jsonl.gz"), "invalid_spec", "Compressed output must end in .jsonl.gz.")
    # Refuse directory aliases before resolving; explicit user-selected storage only.
    for parent in (output.parent, *output.parents):
        require(not parent.is_symlink() and not getattr(parent, "is_junction", lambda: False)(),
                "output_conflict", "Capture directory must not traverse links or junctions.")
    return output, output.with_name(output.name + ".capture.sqlite3"), output.with_name(output.name + ".chunks"), output.with_suffix("").with_suffix(".manifest.json")


def checkpoint(db, state):
    with db:
        _save(db, state)


def entries(db, table="chunks"):
    with closing(db.execute(f"SELECT metadata FROM {table} ORDER BY sequence")) as cursor:
        for (payload,) in cursor:
            yield json.loads(payload)


def owned_inventory(db, directory, state, output, manifest_path, requests):
    # A crash between exclusive hard-link publication and unlinking the owned
    # staging name is recoverable only for that exact inode and expected hash.
    for key, target, expected in (("assembly", output, state.get("transport_sha256")),
                                  ("manifest_stage", manifest_path, None)):
        name = state.get(key)
        if name and Path(name).name == name:
            staged = directory / name
            if staged.exists() and target.exists() and os.path.samefile(staged, target):
                regular(staged, allow_shared=True)
                require(staged.stat().st_nlink == 2, "output_conflict", "Publication inode has an unexpected additional alias.")
                if key == "assembly":
                    require(expected and _sha(staged, requests) == expected, "invalid_capture_state", "Linked gzip changed before recovery.")
                else:
                    require(staged.read_bytes() == (_json(manifest_for(state, output)) + "\n").encode(), "invalid_capture_state", "Linked manifest changed before recovery.")
                staged.unlink()
    regular(output)
    regular(manifest_path)
    names = {item["name"] for table in ("chunks", "abandoned") for item in entries(db, table)}
    if state.get("pending"):
        names.add(state["pending"]["name"])
    if state.get("assembly"):
        names.add(state["assembly"])
    if state.get("manifest_stage"):
        names.add(state["manifest_stage"])
    require(all(Path(name).name == name for name in names), "invalid_capture_state", "Checkpoint contains an invalid chunk path.")
    for path in directory.iterdir():
        regular(path)
        require(path.name in names, "output_conflict", "Unrecognized chunk-directory file retained; choose a new output or inspect it.")
    for item in entries(db, "abandoned"):
        path = directory / item["name"]
        require(path.is_file() and path.stat().st_size == item["compressed_bytes"], "invalid_capture_state", "Retained interrupted chunk changed size.")


def disk_guard(db, state, output, stage, directory, options, extra=0):
    # Reserve the entire second gzip copy before accepting another source page.
    total = state.get("compressed_bytes", 0) + extra
    abandoned = sum(item["compressed_bytes"] for item in entries(db, "abandoned"))
    auxiliary = sum(path.stat().st_size for path in (stage, Path(str(stage) + "-journal")) if path.exists())
    existing_final = sum(path.stat().st_size for path in (output, directory / state.get("assembly", "__absent__")) if path.is_file())
    require(existing_final <= max(20, state.get("compressed_bytes", 0)), "invalid_capture_state", "Publication exceeds the checkpoint's compressed size.")
    staged = state.get("compressed_bytes", 0) + abandoned + auxiliary + existing_final
    remaining = extra + max(20, total) - existing_final + RESERVE
    require(staged + remaining <= options["max_storage_bytes"], "budget_exceeded", "Compressed chunks, checkpoint and final gzip exceed the bounded storage budget.")
    require(shutil.disk_usage(output.parent).free - remaining >= MIN_FREE, "budget_exceeded", "Capture preserves at least 1 GB free plus final gzip space; resume on suitable storage.")


def verify_chunk(path, item, identity, before, requests, digest=None):
    regular(path)
    require(path.is_file() and path.stat().st_size == item["compressed_bytes"] and _sha(path, requests) == item["compressed_sha256"],
            "invalid_capture_state", "Compressed chunk identity differs from its checkpoint.")
    start, end = (datetime.fromisoformat(identity["window"][key]) for key in ("gte", "lt"))
    rows, size, cursor, maximum, raw = 0, 0, before, None, hashlib.sha256()
    try:
        with gzip.open(path, "rb") as stream:
            while True:
                requests.check_time()
                line = stream.readline(1024 * 1024 + 1)
                if not line:
                    break
                require(len(line) <= 1024 * 1024 and line.endswith(b"\n"), "invalid_capture_state", "Chunk has an oversized or partial record.")
                cursor, payload, length, updated = _record(json.loads(line), start, end, cursor, set(identity["fields"]))
                require(line == payload.encode("utf-8") + b"\n", "invalid_capture_state", "Chunk JSONL is not canonical.")
                rows += 1
                size += length
                require(rows <= item["rows"] and size <= item["bytes"], "invalid_capture_state", "Decompressed chunk exceeds declared bounds.")
                maximum = max(maximum, updated) if maximum else updated
                raw.update(line)
                if digest is not None:
                    digest.update(line)
    except (OSError, EOFError, ValueError, UnicodeError):
        raise AnalyticsError("invalid_capture_state", "Compressed chunk cannot be read as bounded canonical JSONL.") from None
    require((rows, size, cursor, maximum, raw.hexdigest()) == (item["rows"], item["bytes"], item["cursor"], item["max_updated_at"], item["sha256"]),
            "invalid_capture_state", "Chunk records do not reconcile with their checkpoint.")
    require(item["before"] == before, "invalid_capture_state", "Chunk cursor chain is broken.")


def commit_chunk(db, state, item):
    state.update(rows=state["rows"] + item["rows"], bytes=state["bytes"] + item["bytes"],
                 compressed_bytes=state["compressed_bytes"] + item["compressed_bytes"], pages=state["pages"] + 1,
                 cursor=item["cursor"], max_updated_at=max(filter(None, (state["max_updated_at"], item["max_updated_at"])), default=None))
    state.pop("pending", None)
    with db:
        db.execute("INSERT INTO chunks(metadata) VALUES (?)", (_json(item),))
        _save(db, state)


def reconcile_chunks(db, state, directory, requests):
    # An intention is durably recorded before a new chunk filename is created.
    # Truncated owned writes are retained and charged; never overwritten.
    pending = state.get("pending")
    if pending:
        path = directory / pending["name"]
        if path.exists() and path.stat().st_size == pending["compressed_bytes"]:
            verify_chunk(path, pending, state["identity"], state["cursor"], requests)
            commit_chunk(db, state, pending)
        else:
            if path.exists():
                require(path.stat().st_size < pending["compressed_bytes"], "invalid_capture_state", "Pending chunk exceeds its intended size.")
                with db:
                    db.execute("INSERT INTO abandoned(metadata) VALUES (?)", (_json({"name": path.name, "compressed_bytes": path.stat().st_size}),))
                    state.pop("pending")
                    _save(db, state)
            else:
                state.pop("pending")
                checkpoint(db, state)
    digest, rows, size, compressed, cursor, maximum, chunks = hashlib.sha256(), 0, 0, 0, None, None, 0
    for item in entries(db):
        verify_chunk(directory / item["name"], item, state["identity"], cursor, requests, digest)
        rows += item["rows"]
        size += item["bytes"]
        compressed += item["compressed_bytes"]
        cursor = item["cursor"]
        maximum = max(filter(None, (maximum, item["max_updated_at"])), default=None)
        chunks += 1
    require((rows, size, compressed, cursor, maximum) == (state["rows"], state["bytes"], state["compressed_bytes"], state["cursor"], state["max_updated_at"]),
            "invalid_capture_state", "Committed chunk totals differ from checkpoint.")
    require(chunks <= state["pages"] <= chunks + 1, "invalid_capture_state", "Checkpoint page count differs from chunk count.")
    return digest.hexdigest()


def manifest_for(state, output):
    identity = state["identity"]
    bounds = {key: datetime.fromisoformat(identity["window"][key]).replace(tzinfo=ZoneInfo("America/New_York")).isoformat() for key in ("gte", "lt")}
    identifier = hashlib.sha256(_json({"identity": identity, "sha256": state["artifact_sha256"]}).encode()).hexdigest()[:20]
    return {"dataset_version": "capture-" + identifier, "kind": "reconciled_public_capture", "source_kind": "real_public_records",
            "source_dataset": identity["source_id"], "source": BASE_URL + "/resource/" + identity["source_id"] + ".json",
            "selected_fields": identity["fields"], "source_date_bounds": identity["window"],
            "row_count": state["rows"], "unique_key_count": state["rows"], "bytes": state["bytes"], "sha256": state["artifact_sha256"],
            "capture_started_at": state["started_at"], "reconciled_at": state["reconciled_at"], "observed_complete": True,
            "extraction_complete": True, "transactional_source_snapshot": False,
            "coverage": {**bounds, "complete": False, "observed_complete": True,
                         "reason": "Observed counts/revisions reconcile; provider point-in-time isolation is not established."},
            "reconciliation": {"initial_count": state["initial_count"], "final_count": state["final_count"],
                "initial_metadata": state["initial_metadata"], "final_metadata": state["final_metadata"],
                "captured_max_updated_at": state["max_updated_at"], "pages": state["pages"]},
            "transport": {"encoding": "concatenated-gzip", "file": output.name, "bytes": state["transport_bytes"],
                          "sha256": state["transport_sha256"], "manifest_hash_describes": "decompressed-canonical-jsonl"},
            "warnings": ["Complete observed enumeration is not a transactional source snapshot or certified citywide temporal coverage.",
                         "No operator flag can turn this capture into complete analysis coverage.",
                         "Keep provenance and pass the separate coverage-certification gate before comparative population claims."]}


def append_exact(path, blocks, requests):
    """Verify an owned publication prefix, then append only missing exact bytes."""
    regular(path)
    digest, size = hashlib.sha256(), 0
    with path.open("r+b" if path.exists() else "x+b") as stream:
        for block in blocks:
            requests.check_time()
            existing = stream.read(len(block))
            require(existing == block[:len(existing)], "invalid_capture_state", "Owned publication prefix changed; file retained.")
            if len(existing) < len(block):
                stream.write(block[len(existing):])
            digest.update(block)
            size += len(block)
        require(stream.read(1) == b"", "invalid_capture_state", "Owned publication has unexpected trailing bytes.")
        stream.flush()
        os.fsync(stream.fileno())
    return size, digest.hexdigest()


def publish(db, state, output, stage, directory, manifest_path, requests, options):
    raw_hash = reconcile_chunks(db, state, directory, requests)
    require(not state.get("artifact_sha256") or state["artifact_sha256"] == raw_hash, "invalid_capture_state", "Raw digest changed before publication.")
    state.update(artifact_sha256=raw_hash, status="publishing")
    state.setdefault("assembly", "assembly-" + uuid.uuid4().hex + ".gz")
    state.setdefault("manifest_stage", "manifest-" + uuid.uuid4().hex + ".json")
    checkpoint(db, state)
    disk_guard(db, state, output, stage, directory, options)

    def blocks():
        found = False
        for item in entries(db):
            found = True
            copied_hash, copied_bytes = hashlib.sha256(), 0
            with (directory / item["name"]).open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    disk_guard(db, state, output, stage, directory, options)
                    copied_hash.update(block)
                    copied_bytes += len(block)
                    require(copied_bytes <= item["compressed_bytes"], "invalid_capture_state", "Chunk grew during publication; partial output retained.")
                    yield block
            require(copied_bytes == item["compressed_bytes"] and copied_hash.hexdigest() == item["compressed_sha256"],
                    "invalid_capture_state", "Chunk changed during publication; no complete artifact published.")
        if not found:
            yield gzip.compress(b"", mtime=0)

    assembly = directory / state["assembly"]
    if output.exists():
        regular(output)
        require(state.get("transport_sha256") == _sha(output, requests) and output.stat().st_size == state.get("transport_bytes"),
                "output_conflict", "Existing gzip differs from this capture; it will not be overwritten.")
    else:
        with closing(blocks()) as source:
            size, digest = append_exact(assembly, source, requests)
        state.update(transport_bytes=size, transport_sha256=digest)
        checkpoint(db, state)
        # Hard-link creation cannot replace an existing destination on any OS.
        os.link(assembly, output)
        assembly.unlink()
    manifest = manifest_for(state, output)
    if manifest_path.exists():
        require(manifest_path.read_bytes() == (_json(manifest) + "\n").encode(), "output_conflict", "Existing manifest differs; it will not be overwritten.")
    else:
        manifest_stage = directory / state["manifest_stage"]
        append_exact(manifest_stage, [(_json(manifest) + "\n").encode()], requests)
        os.link(manifest_stage, manifest_path)
        manifest_stage.unlink()
    state.update(status="complete", observed_complete=True)
    state.pop("error", None)
    checkpoint(db, state)
    return {"status": "complete", "file": str(output), "manifest": str(manifest_path), "checkpoint": str(stage),
            "rows": state["rows"], "bytes": state["bytes"], "sha256": raw_hash, "transport": manifest["transport"],
            "observed_complete": True, "coverage_complete": False, "transactional_source_snapshot": False}


def capture_compressed(start, end, output, *, page_size=1000, max_rows=10_000_000, max_bytes=8_000_000_000,
                       max_storage_bytes=MAX_STORAGE, max_pages=20000, max_seconds=14400,
                       retries=3, request_timeout_seconds=120, client=None):
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError):
        raise AnalyticsError("invalid_spec", "Capture requires YYYY-MM-DD dates.") from None
    require(date(2020, 1, 1) <= a < b, "invalid_spec", "Use a positive 2020-present NYC calendar window.")
    options = {"page_size": page_size, "max_rows": max_rows, "max_bytes": max_bytes, "max_storage_bytes": max_storage_bytes,
               "max_pages": max_pages, "max_seconds": max_seconds, "retries": retries, "request_timeout_seconds": request_timeout_seconds}
    limits = {"page_size": (1, 1000), "max_rows": (1, 100_000_000), "max_bytes": (1, 100_000_000_000),
              "max_storage_bytes": (RESERVE, MAX_STORAGE), "max_pages": (1, 100000), "max_seconds": (1, 86400),
              "retries": (0, 5), "request_timeout_seconds": (1, 180)}
    for key, value in options.items():
        require(type(value) is int and limits[key][0] <= value <= limits[key][1], "invalid_spec", f"Budget {key} must be an integer in {limits[key]}.")
    output, stage, directory, manifest_path = paths(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = stage.with_name(stage.name + ".lock")
    for path in (output, stage, manifest_path, lock, Path(str(stage) + "-journal")):
        regular(path, allow_shared=path in (output, manifest_path))
    identity = {"capture_version": 1, "source_id": "erm2-nwe9", "fields": list(FIELD_TYPES) + ["source_row_id", "source_updated_at"],
                "order": "unique_key ASC", "window": {"gte": a.isoformat() + "T00:00:00", "lt": b.isoformat() + "T00:00:00"}}
    where = f"created_date >= '{identity['window']['gte']}' AND created_date < '{identity['window']['lt']}'"
    requests = _Requests(client or SocrataClient(), time.monotonic() + max_seconds, retries, request_timeout_seconds)
    with _job_lock(lock):
        existed = stage.exists()
        if not existed:
            require(not any(path.exists() for path in (directory, output, manifest_path, Path(str(stage) + "-journal"))), "output_conflict", "Capture artifacts exist without a matching checkpoint; nothing will be overwritten.")
            require(shutil.disk_usage(output.parent).free >= MIN_FREE + RESERVE, "budget_exceeded", "Insufficient free space for the reserved 1 GB and capture checkpoint.")
            directory.mkdir()
            # Exclusive creation avoids replacing an unrelated checkpoint.
            stage.touch(exist_ok=False)
        require(directory.is_dir() and not directory.is_symlink() and not getattr(directory, "is_junction", lambda: False)(), "output_conflict", "Chunk directory must be a real directory.")
        with closing(sqlite3.connect(stage, timeout=5)) as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA cache_size=-1024")
            db.execute("PRAGMA max_page_count=8192")
            try:
                if not existed:
                    with db:
                        db.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
                        for table in ("chunks", "abandoned"):
                            db.execute(f"CREATE TABLE {table}(sequence INTEGER PRIMARY KEY,metadata TEXT NOT NULL)")
                        _save(db, {"identity": identity, "format": "gzip-page-capture-v1", "status": "initializing", "started_at": _utc_now(),
                                   "rows": 0, "bytes": 0, "compressed_bytes": 0, "pages": 0, "cursor": None, "max_updated_at": None, "observed_complete": False})
                state = _load(db)
                require(state.get("identity") == identity and state.get("format") == "gzip-page-capture-v1", "capture_identity_mismatch", "Resume identity differs from checkpoint.")
                require(state["status"] != "quarantined", "capture_quarantined", "Source drift or corrupted records quarantined this capture; retain it and choose a fresh output.")
                owned_inventory(db, directory, state, output, manifest_path, requests)
                reconcile_chunks(db, state, directory, requests)
                require(state["rows"] <= max_rows and state["bytes"] <= max_bytes, "budget_exceeded", "Checkpoint exceeds supplied raw row/byte bounds.")
                if state["status"] in {"ready", "publishing", "complete"}:
                    return publish(db, state, output, stage, directory, manifest_path, requests, options)
                disk_guard(db, state, output, stage, directory, options)
                metadata, count = _metadata(requests, "erm2-nwe9"), _count(requests, "erm2-nwe9", where)
                if "initial_count" in state:
                    require(metadata == state["initial_metadata"] and count == state["initial_count"], "source_changed", "Source observations changed since capture began.")
                else:
                    state.update(initial_metadata=metadata, initial_count=count)
                require(count["row_count"] <= max_rows, "budget_exceeded", "Full source window exceeds max_rows.")
                state.update(status="capturing")
                state.pop("error", None)
                checkpoint(db, state)
                start_dt, end_dt = (datetime.fromisoformat(identity["window"][key]) for key in ("gte", "lt"))
                while not state.get("enumerated"):
                    requests.check_time()
                    require(state["pages"] < max_pages, "budget_exceeded", "Capture page-operation budget exhausted; increase within bounds and resume.")
                    disk_guard(db, state, output, stage, directory, options)
                    page_where = where + (f" AND unique_key > '{state['cursor']}'" if state["cursor"] else "")
                    rows, headers = requests.get("/resource/erm2-nwe9.json", {"$select": SELECT, "$where": page_where, "$order": "unique_key ASC", "$limit": page_size})
                    require(_revision(headers) == count["revision_headers"], "source_changed", "Source revision changed during pagination.")
                    require(isinstance(rows, list) and len(rows) <= page_size, "invalid_source_record", "Source response is not a bounded page.")
                    if not rows:
                        state.update(pages=state["pages"] + 1, enumerated=True)
                        checkpoint(db, state)
                        break
                    cursor, raw_bytes, maximum, raw_digest = state["cursor"], 0, None, hashlib.sha256()
                    buffer = io.BytesIO()
                    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0, compresslevel=6) as zipped:
                        for row in rows:
                            requests.check_time()
                            cursor, payload, size, updated = _record(row, start_dt, end_dt, cursor, set(identity["fields"]))
                            raw_bytes += size
                            require(state["bytes"] + raw_bytes <= max_bytes, "budget_exceeded", "Raw JSONL byte budget exhausted.")
                            encoded = payload.encode("utf-8") + b"\n"
                            zipped.write(encoded)
                            raw_digest.update(encoded)
                            maximum = max(maximum, updated) if maximum else updated
                    require(state["rows"] + len(rows) <= count["row_count"], "source_count_mismatch", "Enumeration exceeds observed source count.")
                    compressed = buffer.getvalue()
                    item = {"name": "page-" + uuid.uuid4().hex + ".gz", "rows": len(rows), "bytes": raw_bytes, "before": state["cursor"],
                            "cursor": cursor, "max_updated_at": maximum, "sha256": raw_digest.hexdigest(), "compressed_bytes": len(compressed),
                            "compressed_sha256": hashlib.sha256(compressed).hexdigest()}
                    disk_guard(db, state, output, stage, directory, options, len(compressed))
                    state["pending"] = item
                    checkpoint(db, state)
                    with (directory / item["name"]).open("xb") as stream:
                        stream.write(compressed)
                        stream.flush()
                        os.fsync(stream.fileno())
                    commit_chunk(db, state, item)
                final_count, final_metadata = _count(requests, "erm2-nwe9", where), _metadata(requests, "erm2-nwe9")
                require(final_count == state["initial_count"] and final_metadata == state["initial_metadata"], "source_changed", "Final source observations differ from initial observations.")
                require(state["rows"] == final_count["unique_count"] and state["max_updated_at"] == final_count["max_updated_at"], "source_count_mismatch", "Captured keys/update maximum do not match full window.")
                state.update(status="ready", final_count=final_count, final_metadata=final_metadata, reconciled_at=_utc_now(), observed_complete=True)
                checkpoint(db, state)
                return publish(db, state, output, stage, directory, manifest_path, requests, options)
            except (AnalyticsError, KeyboardInterrupt, sqlite3.Error, OSError) as exc:
                db.rollback()
                if "state" in locals() and state.get("identity") == identity:
                    state = _load(db)
                    code = exc.code if isinstance(exc, AnalyticsError) else "interrupted" if isinstance(exc, KeyboardInterrupt) else "capture_storage_error"
                    if code not in {"capture_identity_mismatch", "capture_quarantined", "output_conflict"}:
                        if code in QUARANTINE_CODES:
                            state["status"] = "quarantined"
                        elif state["status"] not in {"ready", "publishing", "complete"}:
                            state["status"] = "paused"
                        state["error"] = {"code": code, "at": _utc_now()}
                        checkpoint(db, state)
                if isinstance(exc, (AnalyticsError, KeyboardInterrupt)):
                    raise
                raise AnalyticsError("capture_storage_error", "Capture storage failed; committed chunks retained for bounded resume.") from None


def compressed_status(output):
    """Read progress only; this does not requalify or verify artifact contents."""
    output, stage, _, manifest_path = paths(output)
    regular(stage)
    require(stage.is_file(), "capture_not_found", "No compressed capture checkpoint exists.")
    with closing(sqlite3.connect(stage.as_uri() + "?mode=ro", uri=True)) as db:
        state = _load(db)
        require(state.get("format") == "gzip-page-capture-v1", "capture_identity_mismatch", "Checkpoint is not a compressed capture.")
        return {"status": state["status"], "rows": state["rows"], "bytes": state["bytes"],
                "compressed_chunk_bytes": state["compressed_bytes"], "pages": state["pages"],
                "source_count": state.get("initial_count", {}).get("row_count"), "window": state["identity"]["window"],
                "observed_complete": state.get("observed_complete", False), "error": state.get("error"),
                "file": str(output) if state["status"] == "complete" else None,
                "manifest": str(manifest_path) if state["status"] == "complete" else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--status", action="store_true", help="Read checkpoint progress without source requests or content validation")
    parser.add_argument("--output", required=True, help="New or same-identity resumed .jsonl.gz destination")
    for option, default in (("page-size", 1000), ("max-rows", 10_000_000), ("max-bytes", 8_000_000_000),
                            ("max-storage-bytes", MAX_STORAGE), ("max-pages", 20000), ("max-seconds", 14400),
                            ("retries", 3), ("request-timeout-seconds", 120)):
        parser.add_argument("--" + option, type=int, default=default)
    args = vars(parser.parse_args())
    status_only = args.pop("status")
    if not status_only and (not args["start"] or not args["end"]):
        parser.error("--start and --end are required unless --status is supplied")
    try:
        print(_json(compressed_status(args["output"]) if status_only else capture_compressed(**args)))
    except AnalyticsError as exc:
        print(_json({"status": "failed", **exc.as_dict()}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
