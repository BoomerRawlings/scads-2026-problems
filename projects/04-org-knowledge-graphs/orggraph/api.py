"""Same-origin local HTTP interface; no external model service required."""
from pathlib import Path
import os
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .intake import IntakeManager, UPLOAD_LIMIT
from .store import Conflict, Store, dumps


class RunRequest(BaseModel):
    base_revision: int
    threshold: float = Field(default=.55, ge=0, le=1)
    margin: float = Field(default=.08, ge=0, le=1)
    as_of: str | None = None


class DemoRequest(BaseModel):
    people: int = Field(default=72, ge=72, le=100000, strict=True)
    replace: bool = False
    base_revision: int | None = None


class IntakeSyntheticRequest(BaseModel):
    people: int = Field(default=10000, ge=72, le=100000, strict=True)
    request_key: str | None = Field(default=None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class IntakeBuildRequest(BaseModel):
    base_revision: int = Field(ge=0, strict=True)
    replace: bool = False


class ReviewRequest(BaseModel):
    base_revision: int
    subject: str
    action: str
    assertion_id: str | None = None
    object: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    reason: str = Field(min_length=1, max_length=2000)
    event_id: str | None = None
    idempotency_key: str | None = None


def create_app(db_path=None):
    store = Store(db_path or os.environ.get("ORGGRAPH_DB", "runs/workspace.sqlite3"))
    app = FastAPI(title="Organization Atlas", version=__version__, docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.state.store = store
    intake = IntakeManager(store)
    app.state.intake = intake
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
            parsed = urlsplit(origin)
            if (parsed.scheme, parsed.netloc) != (request.url.scheme, request.url.netloc):
                return JSONResponse({"detail": "Cross-origin writes are not permitted."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def value_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(KeyError)
    async def missing_handler(request, exc):
        return JSONResponse({"detail": str(exc.args[0])}, status_code=404)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/workspace")
    def workspace():
        return store.workspace()

    @app.post("/api/intake/synthetic", status_code=202)
    def intake_synthetic(body: IntakeSyntheticRequest | None = None):
        request = body or IntakeSyntheticRequest()
        return intake.synthetic(request.people, request_key=request.request_key)

    @app.post("/api/intake/import", status_code=202)
    async def intake_import(file: UploadFile = File(...), request_key: str | None = Form(default=None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")):
        data = await file.read(UPLOAD_LIMIT + 1)
        if len(data) > UPLOAD_LIMIT:
            raise HTTPException(413, "Upload limit is 100 MiB. Use the CLI for larger archives.")
        return intake.upload(data, file.filename or "upload.json", request_key=request_key)

    @app.get("/api/intake/request/{request_key}")
    def intake_request(request_key: str):
        return intake.get_request(request_key)

    @app.get("/api/intake/{intake_id}")
    def intake_status(intake_id: str):
        return intake.get(intake_id)

    @app.post("/api/intake/{intake_id}/build", status_code=202)
    def intake_build(intake_id: str, body: IntakeBuildRequest):
        return intake.build(intake_id, **body.model_dump())

    @app.delete("/api/intake/{intake_id}")
    def intake_cancel(intake_id: str):
        return intake.cancel(intake_id)

    @app.post("/api/demo")
    def demo(body: DemoRequest | None = None):
        from .demo import demo_dataset
        body = body or DemoRequest()
        if body.replace and body.base_revision is None:
            raise ValueError("base_revision is required when replacing a populated demo workspace.")
        data = demo_dataset(person_count=body.people)
        outcome = store.import_dataset(data, {"read": len(data["messages"]), "accepted": len(data["messages"]), "duplicate": 0, "quarantined": 0, "unsupported": 0, "issues": [], "note": "Deterministic fictional corpus; not real-world validation."}, replace=body.replace, base_revision=body.base_revision)
        ws = store.workspace()
        if not outcome["duplicate"] or ws["model"].get("id") == "none":
            return store.run_inference(base_revision=ws["revision"])["workspace"]
        return ws

    @app.post("/api/import")
    async def import_file(file: UploadFile = File(...), replace: bool = Form(False)):
        from .ingest import parse_bytes
        data = await file.read(100 * 1024 * 1024 + 1)
        if len(data) > 100 * 1024 * 1024:
            raise HTTPException(413, "Upload limit is 100 MiB. Use the CLI for larger archives.")
        parsed = parse_bytes(data, file.filename or "upload.json")
        if not parsed["dataset"].get("entities"):
            raise ValueError("No usable entities found. Check the import format and required fields.")
        if parsed.get("package", {}).get("format") == "orggraph-package":
            ws = store.restore_package(parsed["package"])
        else:
            store.import_dataset(parsed["dataset"], parsed["report"], replace=replace)
            ws = store.workspace()
        return {"report": parsed["report"], "workspace": ws}

    @app.post("/api/infer")
    def inference(body: RunRequest):
        return store.run_inference(**body.model_dump())

    @app.get("/api/entities")
    def entities(q: str = "", type: str | None = "person", status: str = "all", offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), snapshot: str | None = None):
        return store.entities(q=q[:200], type=type, status=status, offset=offset, limit=limit, snapshot=snapshot)

    @app.get("/api/entities/{entity_id}")
    def detail(entity_id: str, snapshot: str | None = None):
        return store.detail(entity_id, snapshot)

    @app.get("/api/children")
    def children(parent: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), snapshot: str | None = None):
        return store.entities(parent=parent, type="person", offset=offset, limit=limit, snapshot=snapshot)

    @app.get("/api/graph")
    def graph(focus: str | None = None, limit: int = Query(80, ge=1, le=200), snapshot: str | None = None):
        return store.graph(focus=focus, limit=limit, snapshot=snapshot)

    @app.get("/api/groups")
    def groups(snapshot: str | None = None):
        return store.groups(snapshot)

    @app.get("/api/chart")
    def chart(lens: str = "formal", scope: str | None = None, person: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(60, ge=1, le=200), snapshot: str | None = None):
        return store.chart(lens=lens, scope=scope, person=person, offset=offset, limit=limit, snapshot=snapshot)

    @app.post("/api/reviews")
    def review(body: ReviewRequest):
        result = store.review(body.model_dump(exclude_unset=True))
        result.setdefault("workspace", store.workspace())
        return result

    @app.get("/api/compare")
    def compare(before: str, after: str):
        return store.compare(before, after)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        return store.cancel_job(job_id)

    @app.post("/api/jobs/{job_id}/retry")
    def retry(job_id: str, body: RunRequest):
        return store.retry_job(job_id, body.base_revision)

    @app.post("/api/sources/withdraw")
    def withdraw(body: dict):
        return store.withdraw_source(body.get("source_ref", ""), body.get("reason", ""), body.get("base_revision"))

    @app.get("/api/export")
    def export(format: str = "json", snapshot: str | None = None):
        if format == "json":
            data, mime, suffix = dumps(store.export_package(snapshot)), "application/json", "json"
        elif format == "csv":
            data, mime, suffix = store.export_chart(snapshot), "text/csv", "csv"
        elif format == "report":
            data, mime, suffix = store.export_report(snapshot), "text/markdown", "md"
        else:
            raise ValueError("Export format must be json, csv, or report.")
        return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="organization-atlas.{suffix}"'})

    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        @app.get("/")
        def not_built():
            return {"status": "API ready", "next": "Build the frontend with npm run build in frontend/, then restart this server."}
    return app
