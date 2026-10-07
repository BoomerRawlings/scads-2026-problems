"""Loopback-only analyst workspace over the same Engine used by the CLI."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import io
import json
import re
import secrets
import socket
import sqlite3
import tempfile
import time
from urllib.parse import unquote, urlsplit
import zipfile

from .engine import Engine
from .records import DomainError
from .resources import read_bytes


MAX_REQUEST_BYTES = 1_048_576
MAX_EXPORT_BYTES = 32 * 1_048_576
BODY_TIMEOUT_SECONDS = 15
STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}

# Explicit method and field allowlists: the browser cannot select arbitrary methods.
OPERATIONS = {
    "status": ("get_corpus_status", {"corpus_id"}, set()),
    "snapshots": ("list_snapshots", {"corpus_id"}, set()),
    "overview": ("overview", {"corpus_id"}, {"snapshot_id", "knowledge_cutoff"}),
    "preview": ("preview", {"corpus_id", "query"}, {"snapshot_id", "knowledge_cutoff", "valid_time", "mode"}),
    "search": ("search", {"corpus_id", "query"}, {"snapshot_id", "knowledge_cutoff", "valid_time", "mode", "limit", "page_size", "budget"}),
    "search_local": ("search_local", {"corpus_id", "query", "vector_index_id"}, {"snapshot_id", "knowledge_cutoff", "valid_time", "mode", "limit", "page_size", "budget"}),
    "page": ("page", {"cursor"}, {"scope"}),
    "run_get": ("get_run", {"run_id"}, set()),
    "evidence": ("get_evidence", {"corpus_id"}, {"snapshot_id", "assertion_id", "chunk_id", "knowledge_cutoff", "history"}),
    "baseline_save": ("save_baseline", {"run_id"}, {"kind", "finding_ids", "seed_entity_ids", "hops"}),
    "baseline_get": ("get_baseline", {"baseline_id"}, set()),
    "baselines": ("list_baselines", {"corpus_id"}, set()),
    "compare": ("compare", {"baseline_id"}, {"target_snapshot_id", "mode", "knowledge_cutoff", "valid_from_time", "valid_to_time", "budget"}),
    "investigation_save": ("save_investigation", {"data"}, {"expected_version"}),
    "investigation_get": ("get_investigation", {"investigation_id"}, set()),
    "investigations": ("list_investigations", {"corpus_id"}, set()),
    "assertions": ("stage_assertions", {"job_id", "assertions"}, set()),
    "publish": ("publish_snapshot", {"job_id"}, {"label", "allow_exclusions"}),
    "job": ("get_job", {"job_id"}, set()),
    "cancel": ("cancel_job", {"job_id"}, set()),
}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(_):
    raise ValueError("Non-finite JSON number")


def _json(text):
    return json.loads(text, object_pairs_hook=_unique, parse_constant=_constant)


def _fields(body, required, optional):
    if not isinstance(body, dict) or not required <= body.keys() or body.keys() - required - optional:
        raise DomainError("invalid_request", "Missing or unsupported request fields")


def _wire_values(body, prefix=""):
    """Reject coercible JSON types before they become SQL values or user consent."""
    identifiers = {"corpus_id", "snapshot_id", "target_snapshot_id", "run_id", "baseline_id",
                   "investigation_id", "job_id", "vector_index_id", "cursor", "assertion_id", "chunk_id"}
    nullable = {"target_snapshot_id", "assertion_id", "chunk_id", "knowledge_cutoff", "valid_time",
                "valid_from_time", "valid_to_time", "label", "expected_version", "budget", "scope",
                "finding_ids", "seed_entity_ids"}

    def invalid(field, message):
        raise DomainError("invalid_request", message, {"field": prefix + field})

    def identifier(value):
        return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) is not None

    for field, value in body.items():
        if value is None and field in nullable:
            continue
        if field in identifiers and not identifier(value):
            invalid(field, "Expected a bounded identifier string")
        if field in {"history", "allow_exclusions"} and type(value) is not bool:
            invalid(field, "Expected true or false, not a string or number")
        if field in {"limit", "page_size", "hops", "expected_version"} and (type(value) is not int or value < 1):
            invalid(field, "Expected a positive integer")
        if field in {"knowledge_cutoff", "valid_time", "valid_from_time", "valid_to_time"} and not isinstance(value, str):
            invalid(field, "Expected a timezone-aware timestamp string or null")
        if field in {"budget", "scope", "data"} and type(value) is not dict:
            invalid(field, "Expected a JSON object")
        if field == "assertions" and type(value) is not list:
            invalid(field, "Expected an array of assertions")
        if field in {"finding_ids", "seed_entity_ids", "run_ids", "baseline_ids"}:
            if type(value) is not list or len(value) > 1000 or any(not identifier(item) for item in value):
                invalid(field, "Expected an array of at most 1000 identifier strings")
        string_limits = {"query": 4000, "mode": 32, "kind": 32, "label": 512, "idempotency_key": 200}
        if field in string_limits and (not isinstance(value, str) or not value.strip() or len(value) > string_limits[field]):
            invalid(field, "Expected nonblank text within the field limit")
        if field == "data":
            _wire_values(value, prefix="data.")


def _jsonl(text):
    if not isinstance(text, str):
        raise DomainError("invalid_jsonl", "records_jsonl must be a string")
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    records = []
    for number, line in enumerate(lines, 1):
        try:
            record = _json(line)
            if not isinstance(record, dict):
                raise ValueError("Expected an object")
        except (ValueError, RecursionError) as exc:
            raise DomainError("invalid_jsonl", "Every line must be a valid JSON object", {"line": number}) from exc
        records.append(record)
    if not records:
        raise DomainError("invalid_jsonl", "Input batch is empty")
    return records


class WorkspaceServer(ThreadingHTTPServer):
    # ThreadingMixIn joins only non-daemon handlers. A completed HTTP body may
    # precede the handler's Engine.__exit__, so shutdown must wait for DB close.
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, db_path, host="127.0.0.1", port=8765):
        if host != "127.0.0.1":
            raise DomainError("invalid_host", "The workspace binds only to 127.0.0.1")
        if type(port) is not int or not 0 <= port <= 65535:
            raise DomainError("invalid_port", "Expected a port between 0 and 65535")
        if str(db_path) == ":memory:":
            raise DomainError("invalid_database", "The workspace requires a persistent database file")
        self.db_path = str(Path(db_path).resolve())
        self.csrf_token = secrets.token_urlsafe(32)
        with Engine(self.db_path):
            pass
        super().__init__((host, port), WorkspaceHandler)
        self.expected_host = f"127.0.0.1:{self.server_address[1]}"
        self.origin = f"http://{self.expected_host}"


class WorkspaceHandler(BaseHTTPRequestHandler):
    server_version = "GraphRAGWorkspace/1"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)
        self._body_consumed = False

    def log_message(self, *_):
        # Source text, queries, and bootstrap tokens do not enter request logs.
        pass

    def _reply(self, status, content, content_type="application/json; charset=utf-8", *, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content)

    def _result(self, data, status=200):
        self._reply(status, json.dumps({"ok": True, "data": data}, ensure_ascii=True).encode("utf-8"))

    def _error(self, status, code, message, details=None):
        self._discard_rejected_body()
        self._reply(status, json.dumps({"ok": False, "error": {"code": code, "message": message, "details": details or {}}}, ensure_ascii=True).encode("utf-8"))

    def _discard_rejected_body(self):
        # Closing with unread bytes can reset the socket on Windows, hiding the
        # typed error. Discard only a bounded, unambiguous body, without parsing
        # it or accessing the database; do not wait on a stalled sender.
        if self.command != "POST" or self._body_consumed:
            return
        self._body_consumed = True
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or self.headers.get("Transfer-Encoding"):
            return
        try:
            remaining = int(lengths[0])
        except ValueError:
            return
        if not 0 < remaining <= MAX_REQUEST_BYTES + 1:
            return
        previous_timeout = self.connection.gettimeout()
        deadline = time.monotonic() + 1
        try:
            while remaining:
                budget = deadline - time.monotonic()
                if budget <= 0:
                    return
                self.connection.settimeout(budget)
                chunk = self.rfile.read1(min(remaining, 65536))
                if not chunk:
                    return
                remaining -= len(chunk)
        except OSError:
            pass
        finally:
            self.connection.settimeout(previous_timeout)

    def _check_origin(self, *, write=False):
        hosts = self.headers.get_all("Host", [])
        if hosts != [self.server.expected_host]:
            raise DomainError("host_rejected", "Use the exact loopback workspace URL")
        origins = self.headers.get_all("Origin", [])
        if origins and origins != [self.server.origin]:
            raise DomainError("origin_rejected", "Cross-origin requests are not accepted")
        if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            raise DomainError("origin_rejected", "Cross-origin requests are not accepted")
        if write:
            tokens = self.headers.get_all("X-CSRF-Token", [])
            if len(tokens) != 1 or not secrets.compare_digest(tokens[0], self.server.csrf_token):
                raise DomainError("csrf_rejected", "Reload the workspace to obtain its request token")

    def _path(self):
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.fragment:
            raise DomainError("invalid_route", "Only local origin-form routes are supported")
        return unquote(parsed.path)

    def do_GET(self):
        try:
            self._check_origin()
            path = self._path()
            if path in STATIC_ROUTES:
                name, content_type = STATIC_ROUTES[path]
                self._reply(200, read_bytes("static", name), content_type)
            elif path == "/api/bootstrap":
                with Engine(self.server.db_path) as engine:
                    corpora = engine.list_corpora()
                self._result({
                    "csrf_token": self.server.csrf_token, "corpora": corpora,
                    "limits": {"request_bytes": MAX_REQUEST_BYTES, "export_bytes": MAX_EXPORT_BYTES},
                    "notice": "Local reference workspace. Model operations, when configured, remain separate from authored assertions.",
                })
            else:
                self._error(404, "not_found", "Unknown route")
        except DomainError as exc:
            self._error(403 if exc.code.endswith("rejected") else 400, exc.code, exc.message, exc.details)
        except (OSError, sqlite3.Error):
            self._error(500, "service_error", "The local service could not complete this request")

    def _body(self):
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
            raise DomainError("invalid_length", "One Content-Length header is required")
        try:
            length = int(lengths[0])
        except ValueError as exc:
            raise DomainError("invalid_length", "Invalid Content-Length") from exc
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise DomainError("request_too_large", "Request body must be between 1 byte and 1 MiB")
        content_types = self.headers.get_all("Content-Type", [])
        if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
            raise DomainError("unsupported_media_type", "Use application/json")
        # read1 returns after available bytes, so trickling traffic cannot reset
        # the entire body allowance inside one buffered read(length).
        deadline, chunks, remaining = time.monotonic() + BODY_TIMEOUT_SECONDS, [], length
        self._body_consumed = True
        previous_timeout = self.connection.gettimeout()
        try:
            while remaining:
                allowance = deadline - time.monotonic()
                if allowance <= 0:
                    raise TimeoutError
                self.connection.settimeout(allowance)
                chunk = self.rfile.read1(min(remaining, 65536))
                if not chunk:
                    raise DomainError("invalid_json", "Incomplete request body")
                chunks.append(chunk)
                remaining -= len(chunk)
        except TimeoutError:
            raise DomainError("request_timeout", "Request body did not arrive within its time allowance") from None
        finally:
            self.connection.settimeout(previous_timeout)
        raw = b"".join(chunks)
        try:
            body = _json(raw.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise DomainError("invalid_json", "Expected strict UTF-8 JSON") from exc
        if not isinstance(body, dict):
            raise DomainError("invalid_json", "Request body must be a JSON object")
        return body

    def do_POST(self):
        try:
            self._check_origin(write=True)
            path = self._path()
            if not path.startswith("/api/"):
                self._error(404, "not_found", "Unknown route")
                return
            operation = path.removeprefix("/api/")
            if operation not in OPERATIONS and operation not in {"ingest", "export"}:
                self._error(404, "not_found", "Unknown operation")
                return
            body = self._body()
            if operation in {"ingest", "export"}:
                required = {"corpus_id", "records_jsonl", "idempotency_key"} if operation == "ingest" else {"run_id"}
                _fields(body, required, set())
            else:
                _, required, optional = OPERATIONS[operation]
                _fields(body, required, optional)
            _wire_values(body)
            with Engine(self.server.db_path) as engine:
                if operation == "ingest":
                    result = engine.ingest(body["corpus_id"], _jsonl(body["records_jsonl"]), body["idempotency_key"])
                elif operation == "export":
                    self._export(engine, body["run_id"])
                    return
                else:
                    method, _, _ = OPERATIONS[operation]
                    result = getattr(engine, method)(**body)
            self._result(result)
        except DomainError as exc:
            status = 403 if exc.code.endswith("rejected") else 408 if exc.code == "request_timeout" else 413 if exc.code == "request_too_large" else 415 if exc.code == "unsupported_media_type" else 409 if exc.code in {"version_conflict", "idempotency_conflict", "export_exists"} else 400
            self._error(status, exc.code, exc.message, exc.details)
        except (TypeError, KeyError, AttributeError, ValueError):
            self._error(400, "invalid_request", "Request fields have invalid types or values")
        except (OSError, sqlite3.Error):
            self._error(500, "service_error", "The local service could not complete this request")

    def _export(self, engine, run_id):
        # Clients choose no server filesystem paths. The temporary bundle is removed after download.
        with tempfile.TemporaryDirectory(prefix="graphrag-export-") as directory:
            result = engine.export_evidence(run_id, Path(directory) / "bundle")
            folder = Path(result["destination"])
            names = ("manifest.json", "run.json", "evidence.json", "report.md")
            if sum((folder / name).stat().st_size for name in names) > MAX_EXPORT_BYTES:
                raise DomainError("export_too_large", "Evidence bundle exceeds the browser download limit")
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name in names:
                    archive.write(folder / name, arcname=name)
            self._reply(200, output.getvalue(), "application/zip", filename="graphrag-evidence.zip")

    def do_OPTIONS(self):
        self._error(405, "method_not_allowed", "Cross-origin access is not enabled")


def create_server(db_path, host="127.0.0.1", port=8765):
    """Create without blocking; useful for managed startup and HTTP integration tests."""
    return WorkspaceServer(db_path, host, port)


def serve(db_path, host="127.0.0.1", port=8765):
    """Run until interrupted. Never bind beyond loopback or launch a browser implicitly."""
    with create_server(db_path, host, port) as server:
        print(f"GraphRAG workspace: {server.origin}", flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
