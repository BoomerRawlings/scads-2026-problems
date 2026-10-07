"""Loopback-only offline interfaces. Discovery has no source/workspace routes."""
from __future__ import annotations
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import parse_qs, unquote, urlsplit
from .io import canonical
from .schema import require

ASSETS = Path(__file__).parent / "web"


def make_server(*, workspace=None, catalog=None, port=8763):
    require((workspace is None) != (catalog is None), "Select exactly one of workspace or catalog")
    require(type(port) is int and 0 <= port <= 65535, "Invalid port")
    mode = "review" if workspace is not None else "discovery"
    ws = cat = None
    if mode == "review":
        from .workspace import Workspace
        ws = Workspace(workspace)
    else:
        from .catalog import Catalog
        cat = Catalog(catalog, readonly=True)
        require(bool(cat.info().get("catalog_id")), "Import a metadata bundle before serving discovery")
    csrf = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        server_version = "VOPT/0.1"

        def log_message(self, format, *args):
            pass  # Query text and private evidence are not written into server logs.

        def valid_host(self):
            return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def respond(self, payload, status=200, content_type="application/json; charset=utf-8"):
            if not isinstance(payload, bytes):
                payload = canonical(payload)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if not self.valid_host():
                return self.respond({"error": "Unrecognized local host"}, 403)
            try:
                url = urlsplit(self.path)
                path, query = unquote(url.path), parse_qs(url.query)
                if path in ("/", "/app.js", "/guide.js", "/style.css"):
                    name, mime = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/guide.js": ("guide.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
                    return self.respond((ASSETS / name).read_bytes(), content_type=mime)
                if path == "/api/info":
                    data = {"mode": mode, "offline": True}
                    if cat:
                        data["catalog"] = cat.info()
                    else:
                        data["csrf"] = csrf
                    return self.respond(data)
                if cat and path == "/api/search":
                    return self.respond(cat.search(query.get("q", [""])[0], limit=20, method=query.get("method", ["lexical"])[0]))
                if cat and path == "/api/options":
                    return self.respond(cat.options())
                if ws and path == "/api/records":
                    records = []
                    for record in ws.records():
                        states = ws.reviews.status(record)["items"]
                        records.append({"document": record["document"], "processing_status": record.get("processing_status"),
                            "pages": len(record["pages"]), "assertions": len(record["assertions"]),
                            "pending": sum(item["review_status"] in ("pending", "stale") for item in states)})
                    return self.respond(records)
                if ws and path.startswith("/api/record/"):
                    record = ws.record(path.removeprefix("/api/record/"))
                    return self.respond({"document": record["document"], "processing_status": record.get("processing_status"),
                        "coverage": record.get("coverage"), "warnings": record.get("warnings", []),
                        "pages": [{k: p.get(k) for k in ("page_number", "status", "engine", "error")} for p in record["pages"]],
                        **ws.reviews.status(record)})
                if ws and path.startswith("/api/page/"):
                    import pymupdf
                    record = ws.record(path.removeprefix("/api/page/"))
                    source = Path(record["source_path"])
                    # Render the exact bytes whose hash was checked. A separate
                    # pathname open or stat cache can race a replaced source.
                    source_bytes = source.read_bytes()
                    require(hashlib.sha256(source_bytes).hexdigest() == record["sha256"], "Source changed; ingest again before reviewing")
                    page_num = int(query.get("page", ["1"])[0])
                    with pymupdf.open(stream=source_bytes, filetype="pdf") as pdf:
                        require(1 <= page_num <= len(pdf), "Page out of range")
                        page = pdf[page_num - 1]
                        require(page.rect.width * page.rect.height * (120 / 72) ** 2 <= 24000000, "Review raster exceeds 24 million pixel limit")
                        selected_id = query.get("assertion", [None])[0]
                        if selected_id:
                            assertion = next((a for a in record["assertions"] if a["assertion_id"] == selected_id), None)
                            require(assertion is not None, "Unknown assertion")
                            boxes = [b for b in [assertion["evidence"], *assertion["evidence"].get("context", [])] if b.get("page") == page_num]
                            require(bool(boxes), "Evidence does not belong to requested page")
                            for box in boxes:
                                rect = pymupdf.Rect(box["bbox"]) * page.derotation_matrix
                                page.draw_rect(rect, color=(0.85, 0.3, 0), width=1.5, overlay=True)
                        # Rasterization happens only in review mode. Originals are never served.
                        image = page.get_pixmap(dpi=120, alpha=False).tobytes("png")
                    return self.respond(image, content_type="image/png")
                return self.respond({"error": "Route unavailable in this mode"}, 404)
            except (ValueError, OSError, KeyError, RuntimeError, sqlite3.Error) as exc:
                return self.respond({"error": str(exc)}, 400)

        def do_POST(self):
            if not self.valid_host():
                return self.respond({"error": "Unrecognized local host"}, 403)
            if not ws or urlsplit(self.path).path != "/api/review":
                return self.respond({"error": "Route unavailable in this mode"}, 404)
            allowed_origins = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            if self.headers.get("Origin") not in allowed_origins or not secrets.compare_digest(self.headers.get("X-VOPT-Token", ""), csrf):
                return self.respond({"error": "Review must originate from this local interface"}, 403)
            try:
                require(self.headers.get("Content-Type", "").split(";")[0] == "application/json", "JSON body required")
                length = int(self.headers.get("Content-Length", "0"))
                require(0 < length <= 32768, "Invalid request size")
                body = json.loads(self.rfile.read(length), parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON")))
                require(isinstance(body, dict), "JSON object required")
                record = ws.record(body["doc_id"])
                result = ws.reviews.decide(record, body["assertion_id"], body["decision"], body["actor"], actor_kind="human",
                    correction=body.get("correction"), reason=body.get("reason", ""), expected_fingerprint=body["fingerprint"], expected_event_id=body["event_id"])
                return self.respond(result)
            except (ValueError, OSError, KeyError, RuntimeError, sqlite3.Error) as exc:
                return self.respond({"error": str(exc)}, 400)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def serve(*, workspace=None, catalog=None, port=8763):
    server = make_server(workspace=workspace, catalog=catalog, port=port)
    print(f"VOPT {'review' if workspace is not None else 'discovery'}: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
