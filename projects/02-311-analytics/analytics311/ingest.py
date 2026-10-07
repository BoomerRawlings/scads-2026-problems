"""Streaming normalization and resumable, idempotent Elasticsearch ingestion."""

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .elastic import validate_index, _complete
from .errors import AnalyticsError
from .jobs import _lease, _open_file, _redirect, _regular, _same

KEYWORD_FIELDS = ("complaint_type", "descriptor", "borough", "agency", "agency_name", "status",
                  "incident_zip", "community_board", "council_district", "police_precinct",
                  "nta2020", "ntaname", "nta_join_status")


def _date(raw, field, flags):
    if raw is None or raw == "":
        flags.append(f"missing_{field}")
        return None
    if not isinstance(raw, str):
        flags.append(f"invalid_{field}")
        return None
    if "T" not in raw and " " not in raw.strip():
        flags.append(f"invalid_{field}")
        return None
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        flags.append(f"invalid_{field}")
        return None
    if value.tzinfo is None:
        try:
            local_zone = ZoneInfo("America/New_York")
        except ZoneInfoNotFoundError:
            raise AnalyticsError("invalid_config", "America/New_York timezone data unavailable; install the declared tzdata dependency.") from None
        candidates = set()
        for fold in (0, 1):
            local = value.replace(tzinfo=local_zone, fold=fold)
            try:
                utc = local.astimezone(timezone.utc)
                if utc.astimezone(local_zone).replace(tzinfo=None) == value:
                    candidates.add(utc)
            except (OverflowError, ValueError):
                flags.append(f"invalid_{field}")
                return None
        if len(candidates) != 1:
            flags.append(f"{'ambiguous' if candidates else 'nonexistent'}_{field}")
            return None
        value = next(iter(candidates))
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        flags.append(f"invalid_{field}")
        return None


def normalize_record(raw):
    if not isinstance(raw, dict):
        raise AnalyticsError("invalid_record", "Every source record must be an object.")
    identifier = raw.get("unique_key")
    if isinstance(identifier, bool) or not isinstance(identifier, (str, int)) or not str(identifier).strip():
        raise AnalyticsError("invalid_record", "Source record requires a nonempty unique_key.")
    record = {"unique_key": str(identifier).strip()}
    if len(record["unique_key"].encode("utf-8")) > 512:
        raise AnalyticsError("invalid_record", "unique_key exceeds Elasticsearch's 512-byte identifier limit.")
    flags = []
    for field in KEYWORD_FIELDS:
        if raw.get(field) is not None:
            if (isinstance(raw[field], (str, int)) and not isinstance(raw[field], bool)
                    and len(str(raw[field]).encode("utf-8")) <= 32766):
                record[field] = str(raw[field]).strip()
            else:
                flags.append(f"invalid_{field}")
    dates = {}
    for field in ("created_date", "closed_date"):
        original = raw.get(field)
        if isinstance(original, str):
            if len(original) > 1024:
                raise AnalyticsError("invalid_record", f"Source {field} exceeds the 1024-character timestamp limit.")
            record["source_" + field] = original
        dates[field] = _date(original, field, flags)
        if dates[field] is not None:
            record[field] = dates[field].isoformat(timespec="milliseconds").replace("+00:00", "Z")
    record["is_closed"] = record.get("status", "").casefold() == "closed"
    created, closed = dates["created_date"], dates["closed_date"]
    if created is not None and closed is not None:
        duration = (closed - created).total_seconds() / 3600
        if duration < 0:
            flags.append("negative_closure_duration")
        elif record["is_closed"]:
            record["closure_hours"] = duration
        else:
            flags.append("closed_date_without_closed_status")
    elif record["is_closed"]:
        flags.append("closed_without_valid_duration")

    latitude, longitude = raw.get("latitude"), raw.get("longitude")
    location = raw.get("location")
    if latitude in (None, "") and longitude in (None, "") and isinstance(location, dict):
        coordinates = location.get("coordinates")
        if isinstance(coordinates, (list, tuple)) and len(coordinates) == 2:
            longitude, latitude = coordinates
        else:
            latitude, longitude = location.get("lat", location.get("latitude")), location.get("lon", location.get("longitude"))
    if latitude in (None, "") and longitude in (None, ""):
        flags.append("missing_geometry")
    else:
        try:
            if isinstance(latitude, bool) or isinstance(longitude, bool):
                raise ValueError()
            lat, lon = float(latitude), float(longitude)
            if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError()
            record["location"] = {"lat": lat, "lon": lon}
        except (ValueError, TypeError, OverflowError):
            flags.append("invalid_geometry")
    record["quality_flags"] = sorted(set(flags))
    return record


def validate_normalized_record(record):
    """Validate staged canonical JSONL without discarding its source/audit fields."""
    allowed = set(KEYWORD_FIELDS) | {"unique_key", "created_date", "closed_date", "source_created_date",
                "source_closed_date", "location", "is_closed", "closure_hours", "quality_flags"}
    if not isinstance(record, dict) or set(record) - allowed:
        raise AnalyticsError("invalid_record", "Normalized record has unsupported fields.")
    if not isinstance(record.get("unique_key"), str) or record["unique_key"] != record["unique_key"].strip():
        raise AnalyticsError("invalid_record", "Normalized unique_key must be a trimmed string.")
    for field in KEYWORD_FIELDS:
        if field in record and (not isinstance(record[field], str) or record[field] != record[field].strip()
                                or len(record[field].encode("utf-8")) > 32766):
            raise AnalyticsError("invalid_record", f"Normalized {field} must be a bounded string.")
    flags = record.get("quality_flags")
    if not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags) or len(flags) != len(set(flags)):
        raise AnalyticsError("invalid_record", "Normalized quality_flags must be a unique list of strings.")
    known_flags = {"missing_geometry", "invalid_geometry", "negative_closure_duration", "closed_without_valid_duration",
                   "closed_date_without_closed_status"} | {f"invalid_{field}" for field in KEYWORD_FIELDS}
    known_flags |= {f"{prefix}_{field}" for prefix in ("missing", "invalid", "ambiguous", "nonexistent")
                    for field in ("created_date", "closed_date")}
    known_flags |= {f"nta_{status}" for status in ("missing_geometry", "invalid_geometry", "unmatched", "ambiguous")}
    if set(flags) - known_flags:
        raise AnalyticsError("invalid_record", "Normalized record contains unknown quality flags.")
    raw = dict(record)
    for field in ("created_date", "closed_date"):
        source_field = "source_" + field
        if source_field in record:
            if not isinstance(record[source_field], str):
                raise AnalyticsError("invalid_record", f"Normalized {source_field} must be a string.")
            raw[field] = record[source_field]
        if field in record:
            try:
                date = datetime.fromisoformat(record[field].replace("Z", "+00:00"))
                if date.tzinfo is None:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                raise AnalyticsError("invalid_record", f"Normalized {field} must be a timezone-aware timestamp.") from None
    expected = normalize_record(raw)
    for field in ("created_date", "closed_date"):
        if (field in record) != (field in expected):
            raise AnalyticsError("invalid_record", f"Normalized {field} disagrees with its source timestamp.")
        if field in record and datetime.fromisoformat(record[field].replace("Z", "+00:00")) != datetime.fromisoformat(expected[field].replace("Z", "+00:00")):
            raise AnalyticsError("invalid_record", f"Normalized {field} disagrees with its source timestamp.")
    if type(record.get("is_closed")) is not bool or record["is_closed"] != expected["is_closed"]:
        raise AnalyticsError("invalid_record", "Normalized is_closed disagrees with the source status.")
    if ("closure_hours" in record) != ("closure_hours" in expected):
        raise AnalyticsError("invalid_record", "Normalized closure duration is inconsistent with dates and status.")
    if "closure_hours" in record:
        duration = record["closure_hours"]
        try:
            valid_duration = (not isinstance(duration, bool) and isinstance(duration, (int, float)) and math.isfinite(duration)
                              and math.isclose(duration, expected["closure_hours"], rel_tol=1e-12, abs_tol=1e-9))
        except (OverflowError, ValueError):
            valid_duration = False
        if not valid_duration:
            raise AnalyticsError("invalid_record", "Normalized closure duration is inconsistent with dates and status.")
    if "location" in record:
        location = record["location"]
        if (not isinstance(location, dict) or set(location) != {"lat", "lon"}
                or any(isinstance(location[k], bool) or not isinstance(location[k], (int, float)) for k in location)
                or location != expected.get("location")):
            raise AnalyticsError("invalid_record", "Normalized location must contain valid numeric latitude and longitude.")
    # Derived NTA assignment cannot be rechecked without the pinned boundary file;
    # validate its structure and require the boundary hash in the dataset manifest.
    status = record.get("nta_join_status")
    if status is not None:
        if status not in {"matched", "missing_geometry", "invalid_geometry", "unmatched", "ambiguous"}:
            raise AnalyticsError("invalid_record", "Unknown normalized NTA join status.")
        if status == "matched" and (not record.get("nta2020") or not record.get("ntaname")):
            raise AnalyticsError("invalid_record", "Matched NTA record requires code and name.")
        if status != "matched" and ("nta2020" in record or "ntaname" in record or "nta_" + status not in flags):
            raise AnalyticsError("invalid_record", "Unmatched NTA records need a quality flag and no assigned neighborhood.")
    required_flags = set(expected["quality_flags"])
    for field in ("created_date", "closed_date", "geometry"):
        if f"invalid_{field}" in flags:
            required_flags.discard(f"missing_{field}")
    if not required_flags <= set(flags):
        raise AnalyticsError("invalid_record", "Normalized record omitted required source quality flags.")
    return dict(record)


def create_index(client, index, mapping_path=None):
    validate_index(index)
    from .resources import asset_path
    baseline = json.loads(asset_path("config/mapping.json").read_text(encoding="utf-8"))
    mapping = baseline
    if mapping_path is not None:
        try:
            mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            raise AnalyticsError("invalid_configuration", "Cannot read the custom index configuration") from None
        if not isinstance(mapping, dict) or set(mapping) - {"mappings", "settings"} or mapping.get("mappings") != baseline["mappings"]:
            raise AnalyticsError("invalid_configuration", "Custom index configuration may change settings, but must preserve the complete versioned mapping")
    settings = mapping.get("settings", {})
    if not isinstance(settings, dict):
        raise AnalyticsError("invalid_configuration", "Index settings must be an object")
    nested = settings.get("index", {})
    if not isinstance(nested, dict):
        raise AnalyticsError("invalid_configuration", "Nested index settings must be an object")
    for pipeline in ("default_pipeline", "final_pipeline"):
        if any(source.get(key) not in (None, "_none") for source, key in ((settings, pipeline), (settings, "index."+pipeline), (nested, pipeline))):
            raise AnalyticsError("invalid_configuration", "Source index ingest pipelines could change normalized records; disable them")
        # Override any matching index template, not only explicit input settings.
        settings["index." + pipeline] = "_none"
    mapping["settings"] = settings
    response = client.request("PUT", f"/{index}", mapping)
    if response.get("acknowledged") is not True:
        raise AnalyticsError("backend_unavailable", "Elasticsearch did not acknowledge index creation.")
    return {"index": index, "created": True}


def freeze_index(client, index, expected_count=None):
    """Prevent further writes before refreshing/counting the publishable snapshot."""
    validate_index(index)
    response = client.request("PUT", f"/{index}/_block/write")
    if (response.get("acknowledged") is not True or response.get("shards_acknowledged") is not True
            or response.get("indices") != [{"name": index, "blocked": True}]):
        raise AnalyticsError("backend_unavailable", "Elasticsearch did not acknowledge the snapshot write block.")
    refresh = client.request("POST", f"/{index}/_refresh")
    _complete(refresh, search=False)
    result = client.request("GET", f"/{index}/_count")
    _complete(result, search=False)
    count = result.get("count")
    if type(count) is not int or count < 0:
        raise AnalyticsError("partial_execution", "Elasticsearch omitted an exact snapshot record count.")
    if expected_count is not None and count != expected_count:
        raise AnalyticsError("count_mismatch", f"Frozen index has {count} unique records; expected {expected_count}. No manifest should be published.")
    settings = client.request("GET", f"/{index}/_settings")
    if set(settings) != {index}:
        raise AnalyticsError("invalid_config", "Snapshot must resolve to exactly its concrete index.")
    index_uuid = settings[index].get("settings", {}).get("index", {}).get("uuid")
    if not isinstance(index_uuid, str) or not index_uuid:
        raise AnalyticsError("partial_execution", "Elasticsearch omitted the frozen index identity.")
    return {"index": index, "index_uuid": index_uuid, "row_count": count, "immutable": True}


def _fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _save_checkpoint(path, value):
    previous = _regular(path, missing=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    opened = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        current = _regular(path, missing=True)
        if ((previous is None) != (current is None)
                or (previous is not None and (not _same(previous, current)
                    or previous.st_mtime_ns != current.st_mtime_ns or previous.st_size != current.st_size))):
            raise AnalyticsError("unsafe_checkpoint_path", "Checkpoint changed outside its ingestion lease")
        temp.replace(path)
    finally:
        current = _regular(temp, missing=True)
        if current is not None and _same(opened, current):
            temp.unlink()


@contextmanager
def ingestion_lease(checkpoint_path):
    """Hold a nonblocking OS lease for one checkpoint on a local filesystem.

    The adjacent .lock file is persistent; never delete it to unlock. Process
    exit releases ownership automatically. This is neither a distributed lock
    nor protection for distinct checkpoints targeting the same index. Without
    a checkpoint, callers must coordinate their own single writer.
    """
    if checkpoint_path is None:
        yield None
        return
    try:
        if not os.fspath(checkpoint_path):
            raise AnalyticsError("unsafe_checkpoint_path", "Checkpoint path must name a file")
        requested = Path(checkpoint_path)
        if os.name == "nt" and requested.drive.startswith("\\\\"):
            raise AnalyticsError("unsafe_checkpoint_path", "Ingestion checkpoint leases require an ordinary local filesystem path")
        if os.name == "nt" and any(":" in part or part.endswith((" ", "."))
                                  or PureWindowsPath(part).is_reserved()
                                  for part in requested.parts if part not in (requested.anchor, "..")):
            raise AnalyticsError("unsafe_checkpoint_path", "Checkpoint path contains a Windows alias or alternate data stream")
        checkpoint = Path(os.path.abspath(os.fspath(requested)))
        # Check every ancestor before creating missing directories: resolving
        # first would hide parent symlinks and Windows junctions.
        for parent in reversed(checkpoint.parents):
            try:
                metadata = parent.lstat()
            except FileNotFoundError:
                parent.mkdir(exist_ok=True)
                metadata = parent.lstat()
            if _redirect(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise AnalyticsError("unsafe_checkpoint_path", "Checkpoint ancestors must be ordinary local directories")
        original = _regular(checkpoint, missing=True)
        # Existing Windows 8.3 names must select the same lock as their long
        # pathname. All redirects were refused before canonicalizing it.
        canonical = checkpoint.resolve(strict=False)
        current = _regular(checkpoint, missing=True)
        if ((original is None) != (current is None)
                or (original is not None and not _same(original, current))):
            raise AnalyticsError("unsafe_checkpoint_path", "Checkpoint changed while selecting its lease")
        checkpoint = canonical
        with _lease(checkpoint.with_name(checkpoint.name + ".lock")):
            _regular(checkpoint, missing=True)
            yield checkpoint
    except AnalyticsError as exc:
        if exc.code == "job_busy":
            raise AnalyticsError("ingestion_busy", "A live process owns this ingestion checkpoint; retry after it finishes") from None
        if exc.code == "unsafe_job_path":
            raise AnalyticsError("unsafe_checkpoint_path", "Checkpoint and lease files must be ordinary files without links") from None
        raise
    except (OSError, TypeError, ValueError):
        raise AnalyticsError("io_error", "Cannot access the local ingestion checkpoint or its lease") from None


def _valid_checkpoint(saved, expected, source_size):
    """A byte offset alone cannot prove which bytes earlier batches indexed."""
    if not isinstance(saved, dict):
        return False
    if any(saved.get(key) != expected[key] for key in
           ("checkpoint_version", "source_sha256", "index", "index_uuid")):
        return False
    if saved.get("normalized_input") is not expected["normalized_input"]:
        return False
    if (type(saved.get("complete")) is not bool or type(saved.get("quarantined")) is not bool
            or saved["quarantined"]):
        return False
    if any(type(saved.get(key)) is not int or saved[key] < 0
           for key in ("byte_offset", "processed_rows", "source_lines")):
        return False
    if (saved["byte_offset"] > source_size or saved["processed_rows"] > saved["source_lines"]
            or saved["source_lines"] > saved["byte_offset"]
            or (saved["complete"] and saved["byte_offset"] != source_size)):
        return False
    if (not isinstance(saved.get("prefix_sha256"), str)
            or not re.fullmatch("[0-9a-f]{64}", saved["prefix_sha256"])):
        return False
    if saved["complete"] and saved["prefix_sha256"] != saved["source_sha256"]:
        return False
    if "pending" in saved:
        pending = saved["pending"]
        if (saved["complete"] or not isinstance(pending, dict) or set(pending) != {"byte_offset", "prefix_sha256"}
                or type(pending["byte_offset"]) is not int
                or not saved["byte_offset"] < pending["byte_offset"] <= source_size
                or not isinstance(pending["prefix_sha256"], str)
                or not re.fullmatch("[0-9a-f]{64}", pending["prefix_sha256"])):
            return False
    quality = saved.get("quality_counts")
    return (isinstance(quality, dict) and all(isinstance(key, str) and type(value) is int
            and 0 <= value <= saved["processed_rows"] for key, value in quality.items()))


def ingest_jsonl(source_path, client, index, batch_size=500, checkpoint_path=None, *, normalized=False):
    """Upsert deterministic IDs. Checkpoint only fully acknowledged batches.

    A partial bulk failure may have written successful items; replay safely upserts
    the entire failed batch. Processed rows are not a unique indexed-row count.
    """
    with ingestion_lease(checkpoint_path) as checkpoint:
        return _ingest_jsonl_unlocked(source_path, client, index, batch_size, checkpoint, normalized=normalized)


def _ingest_jsonl_unlocked(source_path, client, index, batch_size=500, checkpoint_path=None, *, normalized=False):
    """Implementation for callers holding ingestion_lease through publication."""
    validate_index(index)
    if type(normalized) is not bool:
        raise AnalyticsError("invalid_config", "normalized input mode must be a boolean.")
    if type(batch_size) is not int or not 1 <= batch_size <= 5000:
        raise AnalyticsError("invalid_config", "Ingestion batch_size must be between 1 and 5000.")
    settings = client.request("GET", f"/{index}/_settings")
    if set(settings) != {index}:
        raise AnalyticsError("invalid_config", "Ingestion requires an existing concrete index; create its explicit mapping first.")
    index_settings = settings[index].get("settings", {}).get("index", {})
    if any(index_settings.get(key, "_none") != "_none" for key in ("default_pipeline", "final_pipeline")):
        raise AnalyticsError("invalid_configuration", "Source ingestion requires disabled default/final pipelines to preserve normalized records")
    index_uuid = index_settings.get("uuid")
    if not isinstance(index_uuid, str) or not index_uuid:
        raise AnalyticsError("invalid_config", "Ingestion requires a stable index UUID.")
    source = Path(source_path)
    checkpoint = Path(checkpoint_path) if checkpoint_path else None
    source_stat = source.stat()
    fingerprint = _fingerprint(source)
    progress = {"checkpoint_version": 2, "source_sha256": fingerprint, "index": index, "index_uuid": index_uuid, "normalized_input": normalized,
                "byte_offset": 0, "prefix_sha256": hashlib.sha256(b"").hexdigest(), "processed_rows": 0,
                "source_lines": 0, "quality_counts": {}, "complete": False, "quarantined": False}
    resumed = False
    if checkpoint is not None and checkpoint.exists():
        try:
            descriptor = _open_file(checkpoint, os.O_RDONLY)
            with os.fdopen(descriptor, "rb") as stream:
                content = stream.read(1024 * 1024 + 1)
            if len(content) > 1024 * 1024:
                raise ValueError()
            saved = json.loads(content)
        except (ValueError, UnicodeError, OSError, RecursionError):
            raise AnalyticsError("invalid_checkpoint", "Ingestion checkpoint is unreadable.") from None
        if not _valid_checkpoint(saved, progress, source_stat.st_size):
            raise AnalyticsError("invalid_checkpoint", "Checkpoint is invalid, quarantined, or lacks version-2 consumed-byte verification; use the matching source/index or start a new versioned index.")
        progress = saved
        resumed = True
    if progress.get("complete"):
        return progress
    write_block = index_settings.get("blocks", {}).get("write", index_settings.get("blocks.write"))
    if write_block in {True, "true"}:
        raise AnalyticsError("invalid_config", "Ingestion target is frozen; create a new versioned index for new data.")
    if not resumed:
        # A manifest for this input file cannot describe records retained from an
        # unrelated earlier job. Refresh includes previously acknowledged writes.
        _complete(client.request("POST", f"/{index}/_refresh"), search=False)
        existing = client.request("GET", f"/{index}/_count")
        _complete(existing, search=False)
        if existing.get("count") != 0:
            raise AnalyticsError("invalid_config", "New ingestion requires an empty index; resume the matching checkpoint or create a new versioned index.")
        if checkpoint is not None:
            # Even a partially successful FIRST batch must have an identity-pinned
            # zero-offset checkpoint from which replay is safe.
            _save_checkpoint(checkpoint, progress)
    quality = Counter(progress["quality_counts"])
    with source.open("rb") as stream:
        read_digest = hashlib.sha256()
        remaining = progress["byte_offset"]
        last_byte = None
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise AnalyticsError("invalid_checkpoint", "Source ended before its acknowledged checkpoint offset.")
            read_digest.update(chunk)
            remaining -= len(chunk)
            last_byte = chunk[-1:]
        if (read_digest.hexdigest() != progress["prefix_sha256"]
                or (0 < progress["byte_offset"] < source_stat.st_size and last_byte != b"\n")):
            raise AnalyticsError("invalid_checkpoint", "Source prefix differs from acknowledged bytes or offset is not a JSONL boundary; discard the unfinished snapshot.")
        if "pending" in progress:
            # An unacknowledged bulk may still have upserted some records. Its
            # actual input must match before a replay can be considered safe.
            pending = progress["pending"]
            attempted_digest = read_digest.copy()
            remaining = pending["byte_offset"] - progress["byte_offset"]
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise AnalyticsError("invalid_checkpoint", "Source ended before its attempted bulk offset.")
                attempted_digest.update(chunk)
                remaining -= len(chunk)
                last_byte = chunk[-1:]
            if (attempted_digest.hexdigest() != pending["prefix_sha256"]
                    or (pending["byte_offset"] < source_stat.st_size and last_byte != b"\n")):
                raise AnalyticsError("invalid_checkpoint", "Previously attempted bulk used different source bytes; discard the unfinished snapshot.")
            stream.seek(progress["byte_offset"])
            progress.pop("pending")
        acknowledged = dict(progress)
        batch, batch_bytes = [], 0
        while True:
            line = stream.readline(10 * 1024 * 1024 + 1)
            if len(line) > 10 * 1024 * 1024:
                raise AnalyticsError("budget_exceeded", "A source JSONL line exceeds the 10 MiB limit.")
            if line:
                read_digest.update(line)
                progress["source_lines"] += 1
                if line.strip():
                    try:
                        record = (validate_normalized_record if normalized else normalize_record)(json.loads(line))
                    except (ValueError, UnicodeError):
                        raise AnalyticsError("invalid_record", f"Invalid JSON on source line {progress['source_lines']}.") from None
                    # Serialize each normalized row once; keep only its ID and
                    # wire bytes while buffering a bounded bulk request.
                    encoded = (json.dumps({"index": {"_id": record["unique_key"]}}, allow_nan=False) + "\n"
                               + json.dumps(record, allow_nan=False) + "\n").encode("utf-8")
                    batch.append((record["unique_key"], encoded))
                    batch_bytes += len(encoded)
                    quality.update(record["quality_flags"])
            if batch and (len(batch) == batch_size or batch_bytes >= 4 * 1024 * 1024 or not line):
                if checkpoint is not None:
                    _save_checkpoint(checkpoint, {**acknowledged, "pending": {
                        "byte_offset": stream.tell(), "prefix_sha256": read_digest.hexdigest()}})
                response = client.request("POST", f"/{index}/_bulk", b"".join(encoded for _, encoded in batch))
                items = response.get("items") if isinstance(response, dict) else None
                if not isinstance(items, list) or len(items) != len(batch):
                    raise AnalyticsError("partial_ingestion", "Bulk response omitted per-record acknowledgements; restart from checkpoint.")
                failures = []
                for position, item in enumerate(items):
                    result = item.get("index", {}) if isinstance(item, dict) else {}
                    if not isinstance(result, dict):
                        result = {}
                    status = result.get("status")
                    if (type(status) is not int or not 200 <= status < 300 or result.get("error")
                            or result.get("_id", batch[position][0]) != batch[position][0]
                            or result.get("_index", index) != index):
                        failures.append(position)
                if failures or response.get("errors") is not False:
                    raise AnalyticsError("partial_ingestion", f"Bulk batch failed for {len(failures)} of {len(batch)} records; fix source or index and resume the checkpoint.")
                progress["processed_rows"] += len(batch)
                progress["byte_offset"] = stream.tell()
                progress["prefix_sha256"] = read_digest.hexdigest()
                progress["quality_counts"] = dict(sorted(quality.items()))
                if checkpoint is not None:
                    _save_checkpoint(checkpoint, progress)
                acknowledged = dict(progress)
                batch, batch_bytes = [], 0
            if not line:
                current_stat = source.stat()
                if (read_digest.hexdigest() != fingerprint
                        or (current_stat.st_size, current_stat.st_mtime_ns) != (source_stat.st_size, source_stat.st_mtime_ns)):
                    progress["quarantined"] = True
                    if checkpoint is not None:
                        _save_checkpoint(checkpoint, progress)
                    raise AnalyticsError("source_changed", "Source changed during ingestion; discard the unfinished snapshot and ingest a frozen source file.")
                progress["byte_offset"] = stream.tell()
                progress["prefix_sha256"] = read_digest.hexdigest()
                progress["complete"] = True
                if checkpoint is not None:
                    _save_checkpoint(checkpoint, progress)
                break
    return progress
