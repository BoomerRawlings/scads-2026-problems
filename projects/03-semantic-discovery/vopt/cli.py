"""Offline command-line workflows. Source processing and discovery are separate commands."""
from __future__ import annotations
import argparse
import importlib.metadata
import importlib.util
import json
import math
from pathlib import Path
import sys
import sqlite3
from .io import read_json, write_json, canonical


def doctor():
    import hashlib
    import sqlite3
    packages = {}
    for name in ("PyMuPDF", "rapidocr-onnxruntime", "onnxruntime", "Pillow"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    spec = importlib.util.find_spec("rapidocr_onnxruntime")
    models = []
    if spec and spec.origin:
        for path in sorted(Path(spec.origin).parent.rglob("*.onnx")):
            models.append({"name": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    with sqlite3.connect(":memory:") as db:
        try:
            db.execute("CREATE VIRTUAL TABLE f USING fts5(text)")
            fts = True
        except sqlite3.OperationalError:
            fts = False
    return {"python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version, "fts5": fts,
            "discovery_ready": fts, "extraction_packages": packages, "local_ocr_models": models,
            "extraction_ready": all(packages.values()) and len(models) >= 3,
            "network_required_at_runtime": False,
            "note": "Preflight checks local assets only; offline execution must still be verified. No assets are downloaded."}


def page_timeout(value):
    seconds = float(value)
    if not math.isfinite(seconds) or not 0 < seconds <= 3600:
        raise argparse.ArgumentTypeError("page timeout must be finite and between 0 and 3600 seconds")
    return seconds


def parser():
    p = argparse.ArgumentParser(prog="vopt", description="Offline technical-metadata extraction, review, release, and discovery")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Inspect local dependencies/model hashes; no downloads")
    i = sub.add_parser("ingest", help="Process a rights-documented local PDF manifest")
    i.add_argument("manifest", type=Path)
    i.add_argument("--workspace", type=Path, required=True)
    i.add_argument("--force-ocr", action="store_true")
    i.add_argument("--max-pages", type=int)
    i.add_argument("--no-resume", action="store_true")
    i.add_argument("--page-timeout-seconds", type=page_timeout, default=120.0, help="Hard native-worker deadline per open/page operation; default 120")
    ls = sub.add_parser("records", help="List private extraction/review progress")
    ls.add_argument("--workspace", type=Path, required=True)
    inspect = sub.add_parser("inspect", help="Read candidates, evidence, fingerprint and current review event tokens")
    inspect.add_argument("doc_id")
    inspect.add_argument("--workspace", type=Path, required=True)
    reextract = sub.add_parser("reextract", help="Re-run current rules on saved pages without loading originals or OCR")
    reextract.add_argument("--workspace", type=Path, required=True)
    reextract.add_argument("--doc-id")
    reocr = sub.add_parser("reocr", help="Raster OCR selected pages when embedded text is unreliable; invalidates prior approvals")
    reocr.add_argument("--workspace", type=Path, required=True)
    reocr.add_argument("--doc-id", required=True)
    reocr.add_argument("--pages", type=int, nargs="+", required=True)
    reocr.add_argument("--page-timeout-seconds", type=page_timeout, default=120.0)
    r = sub.add_parser("review", help="Record an evidence review decision")
    r.add_argument("--workspace", type=Path, required=True)
    r.add_argument("--doc-id", required=True)
    r.add_argument("--assertion-id", required=True)
    r.add_argument("--decision", choices=("accept", "reject", "correct"), required=True)
    r.add_argument("--actor", required=True)
    r.add_argument("--actor-kind", choices=("human", "agent", "fixture"), default="human")
    r.add_argument("--correction", type=Path)
    r.add_argument("--reason", default="")
    r.add_argument("--fingerprint", required=True)
    r.add_argument("--event-id", type=int, default=0, help="Latest assertion review event; zero for first review")
    e = sub.add_parser("export", help="Release reviewed metadata; human reviews required by default")
    e.add_argument("--workspace", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--catalog-id", required=True)
    e.add_argument("--sequence", type=int, required=True)
    e.add_argument("--profile", choices=("coverage", "values"), default="coverage")
    e.add_argument("--policy", type=Path)
    e.add_argument("--review-kind", choices=("human", "agent", "fixture"), default="human")
    e.add_argument("--allow-pending", action="store_true", help="Export only current approved candidates; pending assertions stay private")
    imp = sub.add_parser("import", help="Atomically import a validated metadata-only snapshot")
    imp.add_argument("bundle", type=Path)
    imp.add_argument("--catalog", type=Path, required=True)
    val = sub.add_parser("validate", help="Validate a released bundle")
    val.add_argument("bundle", type=Path)
    s = sub.add_parser("search", help="Search metadata; no workspace/source argument is accepted")
    s.add_argument("query")
    s.add_argument("--catalog", type=Path, required=True)
    s.add_argument("--method", choices=("lexical", "semantic"), default="lexical")
    s.add_argument("--limit", type=int, default=10)
    info = sub.add_parser("info")
    info.add_argument("--catalog", type=Path, required=True)
    rollback = sub.add_parser("rollback", help="Restore only a snapshot allowed by the latest policy")
    rollback.add_argument("--catalog", type=Path, required=True)
    rollback.add_argument("--sequence", type=int, required=True)
    serve = sub.add_parser("serve", help="Local offline review OR discovery interface")
    group = serve.add_mutually_exclusive_group(required=True)
    group.add_argument("--workspace", type=Path)
    group.add_argument("--catalog", type=Path)
    serve.add_argument("--port", type=int, default=8763)
    return p


def run(args):
    command = args.command
    if command == "doctor":
        return doctor()
    if command in ("ingest", "records", "inspect", "reextract", "reocr", "review", "export"):
        from .workspace import Workspace
        ws = Workspace(args.workspace)
        if command == "reocr":
            from .ingest import reocr_pages
            record = ws.record(args.doc_id)
            updated = reocr_pages(record["source_path"], record, args.pages, page_timeout_seconds=args.page_timeout_seconds)
            write_json(ws.record_path(args.doc_id), updated)
            return {"doc_id": args.doc_id, "pages_refreshed": sorted(set(args.pages)), "assertions": len(updated["assertions"]),
                "processing_status": updated["processing_status"], "note": "Targeted OCR changes the private record; prior approvals are stale. Reingesting from a different page cache is a separate new record."}
        if command == "reextract":
            from .extract import reextract_record
            records = [ws.record(args.doc_id)] if args.doc_id else ws.records()
            output = []
            for record in records:
                updated = reextract_record(record)
                write_json(ws.record_path(updated["document"]["doc_id"]), updated)
                output.append({"doc_id": updated["document"]["doc_id"], "assertions": len(updated["assertions"]),
                    "processing_version": updated["processing_version"], "note": "Changed fingerprints invalidate prior approvals."})
            return output
        if command == "ingest":
            if args.max_pages is not None and args.max_pages < 1:
                raise ValueError("max-pages must be positive")
            return {"records": ws.ingest_manifest(args.manifest, args.force_ocr, args.max_pages, not args.no_resume,
                page_timeout_seconds=args.page_timeout_seconds)}
        if command == "records":
            summaries = []
            for r in ws.records():
                items = ws.reviews.status(r)["items"]
                summaries.append({"document": r["document"], "pages": len(r["pages"]), "assertions": len(r["assertions"]),
                    "processing_status": r.get("processing_status"),
                    "reviews": {state: sum(i["review_status"] == state for i in items) for state in ("pending", "stale", "accept", "correct", "reject")}})
            return summaries
        if command == "inspect":
            record = ws.record(args.doc_id)
            return {"document": record["document"], **ws.reviews.status(record)}
        if command == "review":
            record = ws.record(args.doc_id)
            return ws.reviews.decide(record, args.assertion_id, args.decision, args.actor, args.actor_kind,
                                    read_json(args.correction) if args.correction else None, args.reason,
                                    args.fingerprint, expected_event_id=args.event_id)
        from .release import export_bundle
        bundle = export_bundle(ws.records(), ws.reviews, args.catalog_id, args.sequence, args.profile,
                               read_json(args.policy) if args.policy else None, required_kind=args.review_kind,
                               require_all_reviewed=not args.allow_pending)
        write_json(args.out, bundle)
        return {"status": "exported", "path": str(args.out), "profile": args.profile, "review_kind": args.review_kind,
                "documents": len(bundle["documents"]), "assertions": len(bundle["assertions"]), "integrity": bundle["integrity"],
                "note": "Agent/fixture review is not independent human validation." if args.review_kind != "human" else "Human review decisions were recorded; accuracy still requires evaluation."}
    if command == "validate":
        from .schema import validate_bundle
        b = validate_bundle(read_json(args.bundle))
        return {"status": "valid", "profile": b["profile"], "sequence": b["sequence"], "integrity": b["integrity"]}
    if command == "serve":
        from .server import serve
        serve(workspace=args.workspace, catalog=args.catalog, port=args.port)
        return None
    from .catalog import Catalog
    catalog = Catalog(args.catalog, readonly=command in ("search", "info"))
    if command == "import":
        return catalog.import_bundle(read_json(args.bundle))
    if command == "search":
        if not 1 <= args.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        return catalog.search(args.query, args.limit, args.method)
    if command == "rollback":
        return catalog.rollback(args.sequence)
    return catalog.info()


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run(args)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, sqlite3.Error) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
