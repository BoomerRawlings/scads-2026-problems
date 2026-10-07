"""Portable command-line workflow for Organization Atlas."""
import argparse
import json
from pathlib import Path

from .store import Store


def main():
    parser = argparse.ArgumentParser(description="Local organization graph workbench")
    parser.add_argument("--db", default="runs/workspace.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8764)
    demo = sub.add_parser("demo", help="Generate deterministic fictional people and communications")
    demo.add_argument("--people", type=int, default=72, help="Total person entities, including the original 72 (72–100000)")
    demo.add_argument("--replace", action="store_true", help="Switch corpus while retaining earlier database snapshots")
    demo.add_argument("--output", type=Path, help="Also save canonical synthetic input, including separate fixture labels")
    demo.add_argument("--generate-only", action="store_true", help="Write --output without changing a database or running inference")
    ingest = sub.add_parser("import")
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--replace", action="store_true")
    run = sub.add_parser("infer")
    run.add_argument("--threshold", type=float, default=.55)
    run.add_argument("--margin", type=float, default=.08)
    run.add_argument("--as-of")
    sub.add_parser("status")
    export = sub.add_parser("export")
    export.add_argument("path", type=Path)
    export.add_argument("--format", choices=("json", "csv", "report"), default="json")
    export.add_argument("--snapshot")
    args = parser.parse_args()
    if args.command == "demo":
        if not 72 <= args.people <= 100000:
            parser.error("--people must be between 72 and 100000")
        if args.generate_only and not args.output:
            parser.error("--generate-only requires --output")
    if args.command == "serve":
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)
        return
    if args.command == "demo":
        from .demo import demo_dataset
        data = demo_dataset(person_count=args.people)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        if args.generate_only:
            print(json.dumps({"output": str(args.output), "people": args.people, "messages": len(data["messages"]), "labels": len(data["labels"]), "synthetic": True}))
            return
    store = Store(args.db)
    if args.command == "demo":
        outcome = store.import_dataset(data, {"note": "Deterministic fictional corpus; software verification only.", "read": len(data["messages"]), "accepted": len(data["messages"]), "duplicate": 0, "quarantined": 0, "unsupported": 0}, replace=args.replace)
        if not outcome["duplicate"] or store.workspace()["model"].get("id") == "none":
            store.run_inference(base_revision=store.workspace()["revision"])
    elif args.command == "import":
        from .ingest import parse_path
        parsed = parse_path(args.path)
        if parsed.get("package", {}).get("format") == "orggraph-package":
            store.restore_package(parsed["package"])
        else:
            store.import_dataset(parsed["dataset"], parsed["report"], replace=args.replace)
        print(json.dumps(parsed["report"], indent=2))
    elif args.command == "infer":
        store.run_inference(base_revision=store.workspace()["revision"], threshold=args.threshold, margin=args.margin, as_of=args.as_of)
    elif args.command == "export":
        data = json.dumps(store.export_package(args.snapshot), indent=2, ensure_ascii=False) if args.format == "json" else store.export_chart(args.snapshot) if args.format == "csv" else store.export_report(args.snapshot)
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_text(data, encoding="utf-8")
        print(f"Exported {args.format}: {args.path}")
        return
    print(json.dumps(store.workspace(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
