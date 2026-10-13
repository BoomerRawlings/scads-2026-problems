"""JSON-first CLI. Analysis and administrative ingestion remain separate commands."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import sys

from .errors import AnalyticsError
from .service import AnalyticsService, DEFAULT_CONFIG, atomic_json, read_json
from .resources import load_profile
from . import __version__


def json_input(value):
    try:
        return json.load(sys.stdin) if value == "-" else read_json(value)
    except ValueError as exc:
        raise AnalyticsError("invalid_spec", "Input is not valid JSON") from exc


def doctor(config_path):
    from .capacity import inventory
    config_path = Path(config_path).resolve()
    _, config = load_profile(config_path)
    storage = Path(config.get("runs_dir", config_path.parent))
    while not storage.exists() and storage != storage.parent:
        storage = storage.parent
    observed = inventory(storage)
    output = {"version": __version__, "python": platform.python_version(), "platform": platform.system(), "logical_cpus": observed["cpu"]["logical_count"],
              "free_disk_bytes": observed["disk"]["free_bytes"], "docker_on_path": bool(shutil.which("docker")),
              "output_parent_writable": os.access(storage, os.W_OK),
              "config_exists": config_path.is_file(),
              "total_memory_bytes": observed["memory"]["total_bytes"],
              "available_memory_bytes": observed["memory"]["available_bytes"],
              "inventory": observed,
              "note": "Inventory only. No services started; no dataset capacity inferred. Development profile needs no Elasticsearch."}
    return output


def parser():
    root = argparse.ArgumentParser(description="Local-first NYC 311 analytical tools")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--config", default=os.environ.get("ANALYTICS311_CONFIG", str(DEFAULT_CONFIG)))
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    command = commands.add_parser("plan-capacity", help="Model explicit dataset and host requirements; no services, config changes or measured capacity claim")
    command.add_argument("--profile", choices=["development", "local-integration", "full-demo", "scale-lab"], default="development")
    command.add_argument("--target-rows", type=int, required=True)
    command.add_argument("--storage", default=".", help="Probe the filesystem that will hold data; Docker storage may be elsewhere")
    command.add_argument("--inventory", help="Optional saved inventory JSON instead of probing this host")
    command.add_argument("--assumptions", help="Optional explicit sizing-assumption JSON")
    commands.add_parser("describe")
    commands.add_parser("recover-exports", help="Mark abandoned exports failed and reclaim their local capacity; active workers are skipped")
    for name in ("validate", "run"):
        command = commands.add_parser(name)
        command.add_argument("spec", help="JSON file or - for stdin")
    command = commands.add_parser("result")
    command.add_argument("result_id")
    command.add_argument("--cursor")
    command.add_argument("--page-size", type=int)
    for name in ("export", "map"):
        command = commands.add_parser(name)
        command.add_argument("result_id")
        command.add_argument("--mode", choices=["records", "aggregates"] if name == "export" else ["requests", "neighborhood_trends"], required=True)
        command.add_argument("--cohort", choices=["all_matching", "selected_groups"], required=True)
        command.add_argument("--group-id", action="append", dest="group_ids")
        if name == "export":
            command.add_argument("--column", action="append", dest="columns")
    for name in ("cancel", "_export-job"):
        command = commands.add_parser(name)
        command.add_argument("job_id")
    commands.add_parser("mcp")
    command = commands.add_parser("ingest")
    command.add_argument("source")
    command.add_argument("--create-index", action="store_true")
    command.add_argument("--mapping", help="Optional explicit index settings/mapping JSON for --create-index")
    command.add_argument("--checkpoint")
    command.add_argument("--batch-size", type=int, default=500)
    command.add_argument("--freeze", action="store_true")
    command.add_argument("--coverage-start")
    command.add_argument("--coverage-end")
    command.add_argument("--complete-coverage", action="store_true", help="Assert reconciled complete source capture, never a sampled download")
    command.add_argument("--normalized-input", action="store_true", help="Input already normalized/enriched by this package; validate without losing provenance")
    commands.add_parser("init-map-results", help="Administrative creation of the dedicated trend-result index")
    command = commands.add_parser("fetch")
    command.add_argument("--start", required=True)
    command.add_argument("--end", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--max-records", type=int, default=1000)
    command = commands.add_parser("capture", help="Resumable bounded-window acquisition; observed reconciliation is not a transactional source snapshot")
    command.add_argument("--start", required=True)
    command.add_argument("--end", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--source-id", choices=["erm2-nwe9"], default="erm2-nwe9")
    command.add_argument("--page-size", type=int, default=1000)
    command.add_argument("--max-rows", type=int, default=10000000)
    command.add_argument("--max-bytes", type=int, default=2000000000)
    command.add_argument("--max-storage-bytes", type=int, default=4500000000)
    command.add_argument("--max-pages", type=int, default=20000)
    command.add_argument("--max-seconds", type=int, default=3600)
    command.add_argument("--min-free-bytes", type=int, default=1000000000)
    command.add_argument("--retries", type=int, default=3)
    command.add_argument("--request-timeout-seconds", type=int, default=30, help="Per-source-request timeout (1–180), capped by remaining invocation budget")
    command = commands.add_parser("capture-status", help="Read persisted capture progress without network access")
    command.add_argument("output")
    command = commands.add_parser("generate")
    command.add_argument("--output", required=True)
    command.add_argument("--records", type=int, default=10000)
    command.add_argument("--seed", type=int, default=7)
    command = commands.add_parser("normalize")
    command.add_argument("source")
    command.add_argument("--output", required=True)
    command.add_argument("--boundaries", help="Optional local official NTA GeoJSON")
    command.add_argument("--max-output-bytes", type=int, default=8 * 1024 ** 3,
                         help="Maximum normalized JSONL bytes; default 8 GiB, no rows silently omitted")
    command.add_argument("--min-free-bytes", type=int, default=1000000000,
                         help="Observed output-filesystem free-space reserve; default 1 GB")
    command = commands.add_parser("benchmark")
    command.add_argument("spec")
    command.add_argument("--repeats", type=int, default=3)
    command.add_argument("--output")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "mcp":
            from .mcp_server import serve
            serve(args.config)
            return 0
        if args.command == "doctor":
            output = doctor(args.config)
        elif args.command == "plan-capacity":
            from .capacity import inventory, plan_capacity
            observed = json_input(args.inventory) if args.inventory else inventory(args.storage)
            assumptions = json_input(args.assumptions) if args.assumptions else None
            output = plan_capacity(args.profile, args.target_rows, inventory=observed, assumptions=assumptions)
        elif args.command == "recover-exports":
            from .jobs import recover_exports
            _, config = load_profile(args.config)
            if not config.get("runs_dir"):
                raise AnalyticsError("invalid_configuration", "Recovery requires runs_dir")
            output = recover_exports(config["runs_dir"])
        elif args.command in ("capture", "capture-status"):
            from .capture import capture_window, capture_status
            if args.command == "capture-status":
                output = capture_status(args.output)
            else:
                output = capture_window(args.start, args.end, args.output, source_id=args.source_id,
                    page_size=args.page_size, max_rows=args.max_rows, max_bytes=args.max_bytes,
                    max_storage_bytes=args.max_storage_bytes, max_pages=args.max_pages,
                    max_seconds=args.max_seconds, min_free_bytes=args.min_free_bytes, retries=args.retries,
                    request_timeout_seconds=args.request_timeout_seconds)
        elif args.command in ("fetch", "generate", "benchmark", "normalize"):
            from .workloads import fetch_sample, generate, benchmark, normalize_file
            if args.command == "fetch":
                output = fetch_sample(args.start, args.end, args.output, args.max_records)
            elif args.command == "generate":
                output = generate(args.output, args.records, args.seed)
            elif args.command == "normalize":
                output = normalize_file(args.source, args.output, args.boundaries,
                                        max_output_bytes=args.max_output_bytes, min_free_bytes=args.min_free_bytes)
            else:
                output = benchmark(args.config, json_input(args.spec), args.repeats)
                if args.output:
                    atomic_json(args.output, output)
        elif args.command == "init-map-results":
            from .elastic import ElasticClient, validate_index
            from .trend_maps import RESULT_MAPPING
            config = read_json(args.config)
            index = validate_index(config.get("kibana", {}).get("result_index"))
            if index == config.get("index"):
                raise AnalyticsError("invalid_configuration", "Result index must differ from source index")
            client = ElasticClient(config["elastic_url"], allow_insecure_local=config.get("allow_insecure_local", False))
            response = client.request("PUT", "/" + index, RESULT_MAPPING)
            if response.get("acknowledged") is not True:
                raise AnalyticsError("partial_execution", "Result index creation was not acknowledged")
            output = {"index": index, "created": True, "role": "trend-results"}
        elif args.command == "ingest":
            from .ingest import ingestion_lease
            with ingestion_lease(args.checkpoint) as checkpoint:
                from .elastic import ElasticClient
                from .ingest import create_index, freeze_index, _ingest_jsonl_unlocked
                from .contracts import normalize_spec
                from .service import instant
                from .workloads import source_manifest
                config_path = Path(args.config).resolve()
                config = read_json(config_path)
                if config.get("backend") != "elastic":
                    raise AnalyticsError("invalid_configuration", "Ingestion requires an elastic profile")
                if args.freeze and (not args.coverage_start or not args.coverage_end):
                    raise AnalyticsError("invalid_spec", "Freeze requires explicit coverage-start and coverage-end")
                staged = source_manifest(args.source)
                from .qualification import comparison_qualification
                qualified = comparison_qualification(staged)
                if qualified and (qualified["stage"] != "normalized" or not args.normalized_input):
                    raise AnalyticsError("qualification_failed", "Qualified staged input requires its normalized artifact and --normalized-input")
                coverage = None
                if args.freeze:
                    coverage = normalize_spec({"dataset_version": config["index"], "operation": "records",
                        "time": {"gte": args.coverage_start, "lt": args.coverage_end}}, {})["time"]
                    coverage.pop("field")
                    coverage["complete"] = args.complete_coverage
                    if args.complete_coverage:
                        original = staged.get("coverage", {})
                        try:
                            valid = original.get("complete") is True and instant(original["gte"]) <= instant(coverage["gte"]) < instant(coverage["lt"]) <= instant(original["lt"])
                        except (KeyError, TypeError, ValueError):
                            valid = False
                        if not valid:
                            raise AnalyticsError("coverage_gap", "Complete coverage requires a hash-matched reconciled source manifest covering these bounds; samples cannot qualify")
                    if qualified and (coverage["complete"] or not instant(qualified["gte"]) <= instant(coverage["gte"]) < instant(coverage["lt"]) <= instant(qualified["lt"])):
                        raise AnalyticsError("qualification_failed", "Freeze bounds must stay inside the qualified observation and keep complete=false")
                client = ElasticClient(config["elastic_url"], allow_insecure_local=config.get("allow_insecure_local", False))
                if args.create_index:
                    create_index(client, config["index"], args.mapping)
                output = _ingest_jsonl_unlocked(args.source, client, config["index"], args.batch_size, checkpoint, normalized=args.normalized_input)
                if args.freeze:
                    if staged and staged["sha256"] != output["source_sha256"]:
                        raise AnalyticsError("source_changed", "Source changed after provenance validation; index not frozen")
                    expected = staged.get("row_count") if staged else None
                    if staged and (type(expected) is not int or expected < 0 or expected != output["processed_rows"]):
                        raise AnalyticsError("source_count_mismatch", "Source and processed counts must reconcile before any snapshot is frozen")
                    if args.complete_coverage and any(output.get("quality_counts", {}).get(f"{flag}_created_date", 0) for flag in ("missing", "invalid", "ambiguous", "nonexistent")):
                        raise AnalyticsError("coverage_gap", "Unusable creation timestamps prevent complete temporal coverage; inspect ingestion quality counts")
                    snapshot = freeze_index(client, config["index"], expected_count=expected)
                    manifest = {"dataset_version": config["index"], "kind": staged.get("kind", "indexed_snapshot"), "source": Path(args.source).name,
                                "extracted_at": datetime.now(timezone.utc).isoformat(), "ingestion": output,
                                "coverage": coverage, **snapshot}
                    if staged:
                        manifest["provenance"] = staged
                        manifest["warnings"] = staged.get("warnings", [])
                        if args.normalized_input and staged.get("geography"):
                            manifest["geography"] = staged["geography"]
                        if staged.get("comparison_qualification") is not None:
                            from .qualification import qualify_frozen_index
                            manifest["comparison_qualification"] = qualify_frozen_index(staged, output, snapshot, coverage)
                    target = (config_path.parent / config["manifest_path"]).resolve()
                    atomic_json(target, manifest)
                    output = {"ingestion": output, "snapshot": snapshot, "manifest": str(target)}
        else:
            service = AnalyticsService(args.config)
            if args.command == "describe":
                output = service.describe_dataset()
            elif args.command == "validate":
                output = service.validate_analysis(json_input(args.spec))
            elif args.command == "run":
                output = service.run_analysis(json_input(args.spec))
            elif args.command == "result":
                output = service.get_result(args.result_id, args.cursor, args.page_size)
            elif args.command == "export":
                output = service.export_csv(args.result_id, args.mode, args.cohort, args.columns, args.group_ids)
            elif args.command == "map":
                output = service.create_map_link(args.result_id, args.mode, args.cohort, args.group_ids)
            elif args.command == "cancel":
                output = service.cancel_export(args.job_id)
            else:
                output = service.run_export_job(args.job_id)
        print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except AnalyticsError as exc:
        print(json.dumps({"error": exc.as_dict()}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('{"error":{"code":"cancelled","message":"Interrupted"}}', file=sys.stderr)
        return 130
    except OSError:
        print('{"error":{"code":"io_error","message":"Cannot access an input or output; check paths, permissions and free disk"}}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
