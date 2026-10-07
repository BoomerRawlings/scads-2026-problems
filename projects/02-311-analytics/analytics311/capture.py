"""Resumable, disk-backed capture of a complete observed NYC 311 time window.

Source observations can reconcile without establishing transactional isolation.
Successful captures therefore retain coverage.complete=False.
"""

from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from .errors import AnalyticsError


BASE_URL = "https://data.cityofnewyork.us"
SOURCE_IDS = {"erm2-nwe9"}
FIELD_TYPES = {
    "unique_key": "text", "created_date": "calendar_date", "closed_date": "calendar_date",
    "complaint_type": "text", "descriptor": "text", "agency": "text", "agency_name": "text",
    "status": "text", "borough": "text", "incident_zip": "text", "community_board": "text",
    "council_district": "text", "police_precinct": "text", "latitude": "number", "longitude": "number", "location": "point",
}
SELECT = ",".join(FIELD_TYPES) + ",:id as source_row_id,:updated_at as source_updated_at"
COUNT_SELECT = "count(*) as row_count,count(distinct unique_key) as unique_count,max(:updated_at) as max_updated_at"
QUARANTINE_CODES = {"source_changed", "source_count_mismatch", "source_keys_not_unique", "invalid_source_record",
                    "source_order_error", "duplicate_source_record", "invalid_capture_state", "source_schema_changed"}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _sha(path, requests=None):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            if requests is not None:
                requests.check_time()
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path, value):
    partial = path.with_name(path.name + ".part")
    with partial.open("w", encoding="utf-8") as stream:
        stream.write(_json(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    partial.replace(path)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AnalyticsError("source_http_error", "Source redirects are disabled; the official endpoint must respond directly.")


class SocrataClient:
    """Fixed public origin; optional app token only in its dedicated header."""

    def __init__(self, opener=None):
        self.opener = opener or build_opener(_NoRedirect())

    def get_json(self, path, params=None, *, timeout=30, max_bytes=16 * 1024 * 1024):
        if not re.fullmatch(r"/(?:api/views|resource)/erm2-nwe9\.json", path):
            raise AnalyticsError("invalid_config", "Capture can read only the official NYC 311 endpoints.")
        headers = {"Accept": "application/json", "User-Agent": "analytics311-capture/1",
                   "Cache-Control": "no-cache", "Pragma": "no-cache"}
        token = os.environ.get("SOCRATA_APP_TOKEN")
        if token:
            headers["X-App-Token"] = token
        url = BASE_URL + path + ("?" + urlencode(params) if params else "")
        with self.opener.open(Request(url, headers=headers), timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            response_headers = {key.lower(): value for key, value in response.headers.items()}
        if len(raw) > max_bytes:
            raise AnalyticsError("budget_exceeded", "Source response exceeded its page byte budget.")
        try:
            return json.loads(raw), response_headers
        except (ValueError, UnicodeError):
            raise AnalyticsError("source_http_error", "Source response is not valid JSON.") from None


class _Requests:
    def __init__(self, client, deadline, retries, request_timeout_seconds=30):
        self.client, self.deadline, self.retries = client, deadline, retries
        self.request_timeout_seconds = request_timeout_seconds

    def check_time(self):
        if time.monotonic() >= self.deadline:
            raise AnalyticsError("budget_exceeded", "Capture invocation time budget exhausted; resume the same output to continue.")

    def get(self, path, params=None, max_bytes=16 * 1024 * 1024):
        for attempt in range(self.retries + 1):
            self.check_time()
            retry_after = None
            failure = None
            try:
                result = self.client.get_json(path, params, timeout=max(.001, min(self.request_timeout_seconds, self.deadline - time.monotonic())), max_bytes=max_bytes)
                self.check_time()
                return result
            except HTTPError as exc:
                failure = f"HTTP {exc.code}"
                if exc.code not in {408, 425, 429, 500, 502, 503, 504}:
                    raise AnalyticsError("source_http_error", f"Official source returned HTTP {exc.code}; no partial capture published.") from None
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
            except (URLError, TimeoutError, ConnectionError, OSError) as exc:
                failure = type(exc.reason).__name__ if isinstance(exc, URLError) else type(exc).__name__
            if attempt >= self.retries:
                phase = "metadata" if params is None else ("count reconciliation" if str(params.get("$select", "")).startswith("count(") else "record page")
                raise AnalyticsError("source_unavailable", f"Transient source errors exhausted bounded retries during {phase} ({failure}; request timeout {self.request_timeout_seconds}s); checkpoint retained, resume later.") from None
            delay = min(2 ** attempt, 10)
            if retry_after is not None:
                try:
                    delay = min(10, max(delay, float(retry_after)))
                except ValueError:
                    pass
            if time.monotonic() + delay >= self.deadline:
                raise AnalyticsError("budget_exceeded", "No time remains for a bounded source retry; resume later.")
            time.sleep(delay)


@contextmanager
def _job_lock(path):
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        locked = False
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            raise AnalyticsError("capture_busy", "Another process owns this capture; choose a different output or wait.") from None
        try:
            yield
        finally:
            if locked:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _save(db, state):
    db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES ('state',?)", (_json(state),))


def _load(db):
    row = db.execute("SELECT value FROM metadata WHERE key='state'").fetchone()
    if not row:
        raise AnalyticsError("invalid_capture_state", "Capture checkpoint is missing; retain it for inspection and choose a new output.")
    try:
        state = json.loads(row[0])
        if not isinstance(state, dict) or not isinstance(state.get("identity"), dict):
            raise ValueError()
        if any(type(state.get(key)) is not int or state[key] < 0 for key in ("rows", "bytes", "pages")):
            raise ValueError()
        if state.get("status") not in {"initializing", "capturing", "paused", "quarantined", "ready", "publishing", "complete"}:
            raise ValueError()
        return state
    except ValueError:
        raise AnalyticsError("invalid_capture_state", "Capture checkpoint is unreadable.") from None


def _staged_totals(db, requests):
    """Interrupt large resume reconciliations at the invocation deadline."""
    requests.check_time()
    expired = False

    def progress():
        nonlocal expired
        expired = time.monotonic() >= requests.deadline
        return int(expired)

    db.set_progress_handler(progress, 1000)
    try:
        stats = db.execute("SELECT count(*),coalesce(sum(json_bytes),0),max(unique_key),max(updated_at) FROM records").fetchone()
    except sqlite3.OperationalError:
        if expired:
            raise AnalyticsError("budget_exceeded", "Capture checkpoint reconciliation exceeded the time budget; resume with more time.") from None
        raise
    finally:
        db.set_progress_handler(None, 0)
    requests.check_time()
    return stats


def _paths(output):
    output = Path(output).resolve()
    return output, output.with_name(output.name + ".capture.sqlite3"), output.with_name(output.name + ".part"), output.with_suffix(".manifest.json")


def capture_status(output):
    """Inspect progress without contacting the provider or loading source rows."""
    output, stage, _, manifest = _paths(output)
    if not stage.is_file():
        raise AnalyticsError("capture_not_found", "No capture checkpoint exists for this output.")
    try:
        with closing(sqlite3.connect(stage.as_uri() + "?mode=ro", uri=True)) as db:
            state = _load(db)
        return {"status": state["status"], "rows": state["rows"], "bytes": state["bytes"], "pages": state["pages"],
                "source_id": state["identity"]["source_id"], "window": state["identity"]["window"],
                "observed_complete": state.get("observed_complete", False), "error": state.get("error"),
                "file": str(output) if state["status"] == "complete" else None,
                "manifest": str(manifest) if state["status"] == "complete" else None}
    except sqlite3.Error:
        raise AnalyticsError("invalid_capture_state", "Capture staging database could not be read.") from None


def _revision(headers):
    headers = {key.lower(): value for key, value in headers.items()}
    if str(headers.get("x-soda2-data-out-of-date", "false")).lower() == "true":
        raise AnalyticsError("source_stale", "Provider marked this query response out of date; resume when a current replica is available.")
    values = {}
    for key in ("x-soda2-truth-last-modified", "x-soda2-secondary-last-modified"):
        try:
            timestamp = parsedate_to_datetime(headers[key])
            if timestamp.tzinfo is None:
                raise ValueError()
            values[key] = timestamp.astimezone(timezone.utc).isoformat()
        except (KeyError, TypeError, ValueError, OverflowError):
            raise AnalyticsError("source_revision_unavailable", "Source omitted usable truth/replica revision observations; no full capture can be reconciled.") from None
    if len(set(values.values())) != 1:
        raise AnalyticsError("source_stale", "Source truth and replica revision observations disagree; resume later.")
    return values


def _metadata(requests, source_id):
    data, _ = requests.get(f"/api/views/{source_id}.json", max_bytes=4 * 1024 * 1024)
    if not isinstance(data, dict) or data.get("id") != source_id:
        raise AnalyticsError("source_schema_changed", "Official metadata identifies an unexpected dataset.")
    if not isinstance(data.get("columns"), list):
        raise AnalyticsError("source_schema_changed", "Official metadata omitted column definitions.")
    columns = {column.get("fieldName"): column.get("dataTypeName") for column in data["columns"] if isinstance(column, dict)}
    expected = dict(FIELD_TYPES)
    if any(columns.get(field) != dtype for field, dtype in expected.items()):
        raise AnalyticsError("source_schema_changed", "NYC 311 field names/types differ from the verified capture schema.")
    if any(type(data.get(field)) is not int for field in ("rowsUpdatedAt", "viewLastModified")):
        raise AnalyticsError("source_revision_unavailable", "Dataset metadata omitted update observations.")
    return {"id": source_id, "rowsUpdatedAt": data["rowsUpdatedAt"], "viewLastModified": data["viewLastModified"],
            "schema": expected, "schema_sha256": hashlib.sha256(_json(expected).encode()).hexdigest()}


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (AttributeError, ValueError, TypeError, OverflowError):
        raise AnalyticsError("invalid_source_record", "Source row update time is not a valid fixed timestamp.") from None


def _count(requests, source_id, where):
    rows, headers = requests.get(f"/resource/{source_id}.json", {"$select": COUNT_SELECT, "$where": where}, max_bytes=65536)
    revision = _revision(headers)
    try:
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError()
        row = rows[0]
        if any(not re.fullmatch(r"[0-9]+", str(row.get(key, ""))) for key in ("row_count", "unique_count")):
            raise ValueError()
        count, unique = int(row["row_count"]), int(row["unique_count"])
    except (ValueError, TypeError, KeyError, AttributeError):
        raise AnalyticsError("source_count_mismatch", "Provider count response is malformed.") from None
    if count != unique:
        raise AnalyticsError("source_keys_not_unique", "Source row count differs from distinct nonnull service-request keys.")
    updated = _timestamp(row["max_updated_at"]) if row.get("max_updated_at") else None
    if count and updated is None:
        raise AnalyticsError("source_revision_unavailable", "Nonempty source window omitted its maximum row update time.")
    return {"row_count": count, "unique_count": unique, "max_updated_at": updated, "revision_headers": revision}


def _disk_guard(output, stage, partial, state, options, extra_bytes=0, extra_rows=0):
    owned = [stage, Path(str(stage) + "-journal"), Path(str(stage) + "-wal"), Path(str(stage) + "-shm"), partial, output]
    storage = sum(path.stat().st_size for path in owned if path.exists())
    partial_bytes = partial.stat().st_size if partial.exists() else 0
    output_bytes = output.stat().st_size if output.exists() else 0
    # SQLite pages/keys/journal plus a SECOND copy for eventual JSONL output.
    growth = 2 * extra_bytes + 1024 * extra_rows + 65536
    remaining_output = max(0, state["bytes"] + extra_bytes - partial_bytes - output_bytes)
    if storage + growth + remaining_output > options["max_storage_bytes"]:
        raise AnalyticsError("budget_exceeded", "Capture staging plus final JSONL exceeds max_storage_bytes; raise the explicit budget on suitable storage and resume.")
    if shutil.disk_usage(output.parent).free - growth - remaining_output < options["min_free_bytes"]:
        raise AnalyticsError("budget_exceeded", "Capture would consume the reserved free disk or final-output space; resume on suitable storage.")


def _record(row, start, end, cursor, allowed):
    if not isinstance(row, dict) or set(row) - allowed:
        raise AnalyticsError("invalid_source_record", "Source record includes unexpected columns or is not an object.")
    key = row.get("unique_key")
    # Live NYC keys are decimal TEXT: lexicographic SoQL order equals SQLite
    # binary/Python string order. Do not guess a different collation for new IDs.
    if not isinstance(key, str) or not re.fullmatch(r"[0-9]{1,512}", key):
        raise AnalyticsError("invalid_source_record", "NYC service-request keys must be nonempty decimal text.")
    if cursor is not None and key <= cursor:
        code = "duplicate_source_record" if key == cursor else "source_order_error"
        raise AnalyticsError(code, "Source page did not advance in strict unique-key order.")
    try:
        created = datetime.fromisoformat(row["created_date"])
        if created.tzinfo is not None or not start <= created < end:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise AnalyticsError("invalid_source_record", "Source created_date falls outside the requested floating-time window.") from None
    if not isinstance(row.get("source_row_id"), str) or not row["source_row_id"]:
        raise AnalyticsError("invalid_source_record", "Source record omitted its internal row identifier.")
    updated = _timestamp(row.get("source_updated_at"))
    try:
        payload = _json(row)
        size = len(payload.encode("utf-8")) + 1
    except (ValueError, TypeError):
        raise AnalyticsError("invalid_source_record", "Source record is not finite JSON data.") from None
    if size > 1024 * 1024:
        raise AnalyticsError("budget_exceeded", "A source record exceeds the 1 MiB record budget.")
    return key, payload, size, updated


def _publish(db, state, output, stage, partial, manifest_path, requests, options):
    if output.exists():
        if state.get("artifact_sha256") != _sha(output, requests):
            raise AnalyticsError("output_conflict", "Existing JSONL differs from the checkpoint; it will not be overwritten.")
    else:
        digest, rows, size = hashlib.sha256(), 0, 0
        _disk_guard(output, stage, partial, state, options)
        with partial.open("wb") as stream:
            for (payload,) in db.execute("SELECT payload FROM records ORDER BY unique_key"):
                if rows % 500 == 0:
                    requests.check_time()
                    _disk_guard(output, stage, partial, state, options)
                encoded = payload.encode("utf-8") + b"\n"
                stream.write(encoded)
                digest.update(encoded)
                size += len(encoded)
                rows += 1
            stream.flush()
            os.fsync(stream.fileno())
        requests.check_time()
        if rows != state["rows"] or size != state["bytes"]:
            raise AnalyticsError("invalid_capture_state", "Staged records no longer match checkpoint totals.")
        state.update(status="publishing", artifact_sha256=digest.hexdigest())
        with db:
            _save(db, state)
        partial.replace(output)
    zone = ZoneInfo("America/New_York")
    bounds = {key: datetime.fromisoformat(state["identity"]["window"][key]).replace(tzinfo=zone).isoformat() for key in ("gte", "lt")}
    identifier = hashlib.sha256(_json({"identity": state["identity"], "sha256": state["artifact_sha256"]}).encode()).hexdigest()[:20]
    manifest = {
        "dataset_version": "capture-" + identifier, "kind": "reconciled_public_capture", "source_kind": "real_public_records",
        "source_dataset": state["identity"]["source_id"], "source": BASE_URL + "/resource/" + state["identity"]["source_id"] + ".json",
        "selected_fields": state["identity"]["fields"], "source_date_bounds": state["identity"]["window"],
        "row_count": state["rows"], "unique_key_count": state["rows"], "bytes": state["bytes"], "sha256": state["artifact_sha256"],
        "capture_started_at": state["started_at"], "reconciled_at": state["reconciled_at"],
        "observed_complete": True, "extraction_complete": True, "transactional_source_snapshot": False,
        "coverage": {**bounds, "complete": False, "observed_complete": True,
                     "reason": "Observed counts/revisions reconcile; provider point-in-time isolation is not established."},
        "reconciliation": {"initial_count": state["initial_count"], "final_count": state["final_count"],
                           "initial_metadata": state["initial_metadata"], "final_metadata": state["final_metadata"],
                           "captured_max_updated_at": state["max_updated_at"], "pages": state["pages"]},
        "warnings": ["Complete observed enumeration is not a transactional source snapshot or certified citywide temporal coverage.",
                     "No operator flag can turn this capture into complete analysis coverage.",
                     "Keep provenance and pass the separate coverage-certification gate before comparative population claims."],
    }
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            raise AnalyticsError("output_conflict", "Existing manifest is not the checkpoint's published manifest.") from None
        if existing != manifest:
            raise AnalyticsError("output_conflict", "Existing manifest differs from this capture and will not be overwritten.")
    else:
        _atomic_json(manifest_path, manifest)
    state.update(status="complete", observed_complete=True)
    state.pop("error", None)
    with db:
        _save(db, state)
    return {"status": "complete", "file": str(output), "manifest": str(manifest_path), "staging_db": str(stage),
            "rows": state["rows"], "bytes": state["bytes"], "sha256": state["artifact_sha256"],
            "observed_complete": True, "coverage_complete": False, "transactional_source_snapshot": False}


def capture_window(start, end, output, *, page_size=1000, max_rows=10_000_000,
                   max_bytes=2_000_000_000, max_storage_bytes=4_500_000_000,
                   max_pages=20000, max_seconds=3600, min_free_bytes=1_000_000_000,
                   retries=3, request_timeout_seconds=30, source_id="erm2-nwe9", client=None):
    """Capture/resume an explicit [start,end) NYC-local calendar-date window.

    Resource exhaustion pauses a job and raises AnalyticsError. Same-identity
    resume may increase budgets; source drift quarantines the job permanently.
    Only completed, reconciled captures publish JSONL and a final manifest.
    """
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError):
        raise AnalyticsError("invalid_spec", "Capture requires YYYY-MM-DD start/end dates.") from None
    if source_id not in SOURCE_IDS or a >= b:
        raise AnalyticsError("invalid_spec", "Use an official NYC 311 source and a positive date window.")
    if a < date(2020, 1, 1):
        raise AnalyticsError("invalid_spec", "This verified capture adapter supports the 2020-present NYC dataset only.")
    options = {"page_size": page_size, "max_rows": max_rows, "max_bytes": max_bytes, "max_storage_bytes": max_storage_bytes,
               "max_pages": max_pages, "max_seconds": max_seconds, "min_free_bytes": min_free_bytes, "retries": retries,
               "request_timeout_seconds": request_timeout_seconds}
    bounds = {"page_size": (1, 5000), "max_rows": (1, 10 ** 12), "max_bytes": (1, 10 ** 15),
              "max_storage_bytes": (1, 10 ** 15), "max_pages": (1, 10 ** 9), "max_seconds": (1, 86400),
              "min_free_bytes": (0, 10 ** 15), "retries": (0, 5), "request_timeout_seconds": (1, 180)}
    for key, value in options.items():
        if type(value) is not int or not bounds[key][0] <= value <= bounds[key][1]:
            raise AnalyticsError("invalid_spec", f"Capture budget {key} must be an integer in {bounds[key]}.")
    output, stage, partial, manifest_path = _paths(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(FIELD_TYPES)
    identity = {"capture_version": 1, "source_id": source_id, "fields": fields + ["source_row_id", "source_updated_at"],
                "order": "unique_key ASC", "window": {"gte": a.isoformat() + "T00:00:00", "lt": b.isoformat() + "T00:00:00"}}
    where = f"created_date >= '{identity['window']['gte']}' AND created_date < '{identity['window']['lt']}'"
    selection = ",".join(fields) + ",:id as source_row_id,:updated_at as source_updated_at"
    requests = _Requests(client or SocrataClient(), time.monotonic() + max_seconds, retries, request_timeout_seconds)
    with _job_lock(stage.with_name(stage.name + ".lock")):
        existed = stage.exists()
        if not existed and (output.exists() or partial.exists() or manifest_path.exists()):
            raise AnalyticsError("output_conflict", "Output/partial/manifest already exists without a matching capture checkpoint.")
        try:
            db = sqlite3.connect(stage, timeout=5)
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA cache_size=-2048")
            db.execute("PRAGMA temp_store=FILE")
            if not existed:
                with db:
                    db.execute("CREATE TABLE records(unique_key TEXT PRIMARY KEY COLLATE BINARY,payload TEXT NOT NULL,json_bytes INTEGER NOT NULL,updated_at TEXT NOT NULL) WITHOUT ROWID")
                    db.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID")
                    _save(db, {"identity": identity, "status": "initializing", "started_at": _utc_now(), "rows": 0,
                               "bytes": 0, "pages": 0, "cursor": None, "max_updated_at": None, "observed_complete": False})
            state = _load(db)
            if state.get("identity") != identity:
                raise AnalyticsError("capture_identity_mismatch", "Resume window/source/schema differs from the existing checkpoint; choose another output.")
            if state["status"] == "quarantined":
                raise AnalyticsError("capture_quarantined", "Source drift or invalid records quarantined this capture; retain its checkpoint and start a new output.")
            stats = _staged_totals(db, requests)
            if tuple(stats) != (state["rows"], state["bytes"], state["cursor"], state["max_updated_at"]):
                raise AnalyticsError("invalid_capture_state", "SQLite record totals/cursor disagree with the capture checkpoint.")
            if state["rows"] > max_rows or state["bytes"] > max_bytes:
                raise AnalyticsError("budget_exceeded", "Existing capture exceeds the supplied row/byte budgets.")
            if state["status"] in {"ready", "publishing", "complete"}:
                return _publish(db, state, output, stage, partial, manifest_path, requests, options)
            _disk_guard(output, stage, partial, state, options)
            metadata = _metadata(requests, source_id)
            count = _count(requests, source_id, where)
            if "initial_metadata" in state:
                if metadata != state["initial_metadata"] or count != state["initial_count"]:
                    raise AnalyticsError("source_changed", "Source metadata/count/revision changed since this capture began.")
            else:
                state.update(initial_metadata=metadata, initial_count=count)
            if count["row_count"] > max_rows:
                raise AnalyticsError("budget_exceeded", "Source window exceeds max_rows; increase the explicit budget or choose a new smaller window.")
            state.update(status="capturing")
            state.pop("error", None)
            with db:
                _save(db, state)
            allowed = set(identity["fields"])
            start_dt, end_dt = datetime.combine(a, datetime.min.time()), datetime.combine(b, datetime.min.time())
            while True:
                requests.check_time()
                if state["pages"] >= max_pages:
                    raise AnalyticsError("budget_exceeded", "Capture page budget exhausted; increase it and resume.")
                _disk_guard(output, stage, partial, state, options)
                page_where = where + (f" AND unique_key > '{state['cursor']}'" if state["cursor"] is not None else "")
                rows, headers = requests.get(f"/resource/{source_id}.json", {"$select": selection, "$where": page_where,
                                            "$order": "unique_key ASC", "$limit": page_size})
                if _revision(headers) != state["initial_count"]["revision_headers"]:
                    raise AnalyticsError("source_changed", "Source revision changed during pagination.")
                if not isinstance(rows, list) or len(rows) > page_size:
                    raise AnalyticsError("invalid_source_record", "Source response is not a bounded page of records.")
                converted, cursor, added_bytes, max_updated = [], state["cursor"], 0, state["max_updated_at"]
                for row in rows:
                    converted_row = _record(row, start_dt, end_dt, cursor, allowed)
                    converted.append(converted_row)
                    cursor, _, size, updated = converted_row
                    added_bytes += size
                    max_updated = max(max_updated, updated) if max_updated else updated
                if state["rows"] + len(rows) > state["initial_count"]["row_count"]:
                    raise AnalyticsError("source_count_mismatch", "Pagination returned more unique records than the observed source count.")
                if state["rows"] + len(rows) > max_rows or state["bytes"] + added_bytes > max_bytes:
                    raise AnalyticsError("budget_exceeded", "Capture row/JSONL-byte budget exhausted; increase it and resume.")
                _disk_guard(output, stage, partial, state, options, added_bytes, len(rows))
                with db:
                    try:
                        db.executemany("INSERT INTO records(unique_key,payload,json_bytes,updated_at) VALUES (?,?,?,?)", converted)
                    except sqlite3.IntegrityError:
                        raise AnalyticsError("duplicate_source_record", "Source returned duplicate service-request keys; capture quarantined.") from None
                    state.update(rows=state["rows"] + len(rows), bytes=state["bytes"] + added_bytes,
                                 pages=state["pages"] + 1, cursor=cursor, max_updated_at=max_updated)
                    _save(db, state)
                if not rows:
                    break
            final_count = _count(requests, source_id, where)
            final_metadata = _metadata(requests, source_id)
            if final_count != state["initial_count"] or final_metadata != state["initial_metadata"]:
                raise AnalyticsError("source_changed", "Final source count/update observations differ from initial observations.")
            if state["rows"] != final_count["unique_count"] or state["max_updated_at"] != final_count["max_updated_at"]:
                raise AnalyticsError("source_count_mismatch", "Captured unique keys/update maximum do not reconcile with the full source window.")
            state.update(status="ready", final_count=final_count, final_metadata=final_metadata,
                         reconciled_at=_utc_now(), observed_complete=True)
            with db:
                _save(db, state)
            return _publish(db, state, output, stage, partial, manifest_path, requests, options)
        except (AnalyticsError, KeyboardInterrupt, sqlite3.Error, OSError) as exc:
            if "db" in locals() and "state" in locals() and state.get("identity") == identity and state.get("status") != "quarantined":
                db.rollback()
                # Reload committed progress, never checkpoint an uncommitted page.
                state = _load(db)
                code = exc.code if isinstance(exc, AnalyticsError) else "interrupted" if isinstance(exc, KeyboardInterrupt) else "capture_storage_error"
                if code not in {"capture_identity_mismatch", "capture_quarantined", "output_conflict"}:
                    if code in QUARANTINE_CODES:
                        state["status"] = "quarantined"
                    elif state["status"] not in {"ready", "publishing", "complete"}:
                        state["status"] = "paused"
                    state["error"] = {"code": code, "at": _utc_now()}
                    with db:
                        _save(db, state)
            if isinstance(exc, (AnalyticsError, KeyboardInterrupt)):
                raise
            raise AnalyticsError("capture_storage_error", "Capture storage failed; retain staging files and resume after resolving storage availability.") from None
        finally:
            if "db" in locals():
                db.close()
