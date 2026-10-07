"""Dependency-free JSON command line interface for the discovery service."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from .records import DomainError


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise DomainError("invalid_arguments", message, {})


def _positive(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValueError(f"non-finite number is not valid JSON: {value}")


def _decode(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_nonfinite)


def read_json(path: str | Path) -> Any:
    """Read strict UTF-8 JSON without duplicate keys or NaN/Infinity."""
    try:
        return _decode(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise DomainError("invalid_json", str(exc), {"path": str(path)}) from exc


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Validate the complete batch before any call to the ingestion engine."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DomainError("invalid_jsonl", str(exc), {"path": str(path)}) from exc
    records = []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    for number, line in enumerate(lines, start=1):
        try:
            if not line.strip():
                raise ValueError("blank lines are not allowed")
            record = _decode(line)
            if not isinstance(record, dict):
                raise ValueError("each line must contain a JSON object")
        except (ValueError, RecursionError) as exc:
            raise DomainError(
                "invalid_jsonl", str(exc), {"path": str(path), "line": number}
            ) from exc
        records.append(record)
    if not records:
        raise DomainError("invalid_jsonl", "input batch is empty", {"path": str(path)})
    return records


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DomainError("invalid_input", f"{name} must be a JSON object", {})
    return value


def _corpus(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--corpus", required=True)


def _snapshot(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--snapshot", default="latest")
    parser.add_argument("--knowledge-cutoff")


def _budget(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--budget", help="JSON budget object; service caps still apply")
    group.add_argument("--budget-file", help="UTF-8 JSON budget object")


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        prog="graphrag-discovery", description="Local, source-grounded discovery prototype"
    )
    parser.add_argument("--db", default="runs/graphrag.sqlite3", help="SQLite path")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="initialize a local database")
    commands.add_parser("doctor", help="check local database integrity and schema")
    commands.add_parser("corpora", help="list local corpora")
    backup = commands.add_parser("backup", help="create a consistent new SQLite backup")
    backup.add_argument("--output", required=True)
    serve = commands.add_parser("serve", help="open the local browser analyst workspace")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=_positive, default=8765)
    for name in ("model-check", "extract", "index-vectors"):
        local = commands.add_parser(name, help="use an explicitly configured local llama.cpp model")
        local.add_argument("--endpoint", required=True)
        local.add_argument("--model", required=True)
        local.add_argument("--model-revision")
        local.add_argument("--model-sha256")
        local.add_argument("--timeout", type=_positive, default=120)
        if name == "extract":
            local.add_argument("--job", required=True)
        if name == "index-vectors":
            _corpus(local)
            local.add_argument("--snapshot", default="latest")
        if name != "model-check":
            local.add_argument("--max-calls", type=_positive, default=100)
            local.add_argument("--max-seconds", type=_positive, default=600)
    vectors = commands.add_parser("vectors", help="list immutable exact-vector artifacts")
    _corpus(vectors)
    vector_import = commands.add_parser("import-vectors", help="import complete supplied vectors bound to exact source hashes")
    _corpus(vector_import)
    vector_import.add_argument("--snapshot", default="latest")
    vector_import.add_argument("--file", required=True)
    status = commands.add_parser("status", help="report corpus capabilities and coverage")
    _corpus(status)
    ingest = commands.add_parser("ingest", help="stage a strict JSONL document batch")
    _corpus(ingest)
    ingest.add_argument("--file", required=True)
    ingest.add_argument("--idempotency-key", "--key", required=True)
    assertions = commands.add_parser("assertions", help="stage authored assertion JSON")
    assertions.add_argument("--job", required=True)
    assertions.add_argument("--file", required=True, help="JSON array of assertion objects")
    publish = commands.add_parser("publish", help="activate a validated immutable snapshot")
    publish.add_argument("--job", required=True)
    publish.add_argument("--label")
    publish.add_argument("--allow-exclusions", action="store_true")
    for name in ("job", "cancel"):
        command = commands.add_parser(name)
        command.add_argument("--job", required=True)
    snapshots = commands.add_parser("snapshots")
    _corpus(snapshots)
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("--id", required=True)
    search = commands.add_parser("search", help="query a pinned snapshot")
    _corpus(search)
    _snapshot(search)
    _budget(search)
    search.add_argument("--query", required=True)
    search.add_argument("--valid-time")
    search.add_argument("--mode", choices=("lexical", "dense", "hybrid", "graphrag"), default="lexical")
    search.add_argument("--vector-index")
    search.add_argument("--query-vector", help="JSON {vector, profile}; otherwise embed locally using the index profile")
    search.add_argument("--limit", type=_positive, default=20)
    search.add_argument("--page-size", type=_positive, default=10)
    evidence = commands.add_parser("evidence", help="open exact source-version evidence")
    _corpus(evidence)
    _snapshot(evidence)
    target = evidence.add_mutually_exclusive_group(required=True)
    target.add_argument("--chunk")
    target.add_argument("--assertion")
    evidence.add_argument("--history", action="store_true")
    run = commands.add_parser("run", help="retrieve a saved run")
    run.add_argument("--id", required=True)
    page = commands.add_parser("page", help="resume a saved result page without rerunning search")
    page.add_argument("--cursor", required=True)
    baseline = commands.add_parser("baseline")
    baseline_actions = baseline.add_subparsers(dest="action", required=True)
    baseline_save = baseline_actions.add_parser("save")
    baseline_save.add_argument("--run", required=True)
    baseline_save.add_argument(
        "--kind", choices=("saved_findings", "entity_neighborhood"), default="saved_findings"
    )
    baseline_save.add_argument("--finding-id", action="append")
    baseline_save.add_argument("--entity-id", action="append")
    baseline_save.add_argument("--hops", type=_positive, default=1)
    baseline_get = baseline_actions.add_parser("get")
    baseline_get.add_argument("--id", required=True)
    baseline_list = baseline_actions.add_parser("list")
    _corpus(baseline_list)
    compare = commands.add_parser("compare")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--target-snapshot")
    compare.add_argument(
        "--mode", choices=("knowledge_change", "source_change", "world_state_change"),
        default="knowledge_change",
    )
    compare.add_argument("--knowledge-cutoff")
    compare.add_argument("--valid-from")
    compare.add_argument("--valid-to")
    _budget(compare)
    investigation = commands.add_parser("investigation")
    investigation_actions = investigation.add_subparsers(dest="action", required=True)
    investigation_save = investigation_actions.add_parser("save")
    investigation_save.add_argument("--file", required=True, help="investigation JSON object")
    investigation_save.add_argument("--expected-version", type=_positive)
    investigation_get = investigation_actions.add_parser("get")
    investigation_get.add_argument("--id", required=True)
    investigation_list = investigation_actions.add_parser("list")
    _corpus(investigation_list)
    export = commands.add_parser("export", help="create a local evidence bundle")
    export.add_argument("--run", required=True)
    export.add_argument("--output", required=True)
    demo = commands.add_parser("demo", help="run authored fixtures with simulated UTC time")
    demo.add_argument("--output", default="runs/demo")
    return parser


def _prepare(args: argparse.Namespace) -> dict[str, Any]:
    """Parse user inputs before constructing the database service."""
    prepared: dict[str, Any] = {}
    if args.command == "ingest":
        prepared["records"] = read_jsonl(args.file)
    elif args.command == "assertions":
        value = read_json(args.file)
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise DomainError("invalid_input", "assertions must be a JSON array of objects", {})
        prepared["assertions"] = value
    elif args.command == "investigation" and args.action == "save":
        prepared["investigation"] = _object(read_json(args.file), "investigation")
    elif args.command == "import-vectors":
        prepared["vectors"] = _object(read_json(args.file), "vectors")
    if getattr(args, "query_vector", None):
        prepared["query_vector"] = _object(read_json(args.query_vector), "query_vector")
    if getattr(args, "budget_file", None):
        prepared["budget"] = _object(read_json(args.budget_file), "budget")
    elif getattr(args, "budget", None):
        try:
            prepared["budget"] = _object(_decode(args.budget), "budget")
        except ValueError as exc:
            raise DomainError("invalid_input", str(exc), {"field": "budget"}) from exc
    return prepared


def _dispatch(engine: Any, args: argparse.Namespace, prepared: dict[str, Any]) -> Any:
    command = args.command
    if command == "init":
        return {"initialized": True, "database": str(Path(args.db).resolve())}
    if command == "doctor":
        return engine.doctor()
    if command == "corpora":
        return engine.list_corpora()
    if command == "backup":
        return engine.backup(args.output)
    if command in {"model-check", "extract", "index-vectors"}:
        from .local_models import LocalModelClient
        client = LocalModelClient(args.endpoint, args.model, timeout=args.timeout,
                                  model_revision=args.model_revision, model_sha256=args.model_sha256)
        if command == "model-check":
            return client.preflight()
        if command == "extract":
            return engine.extract_job(args.job, client, max_calls=args.max_calls, max_wall_seconds=args.max_seconds)
        return engine.build_vector_index(args.corpus, client, args.snapshot, max_calls=args.max_calls, max_wall_seconds=args.max_seconds)
    if command == "vectors":
        return engine.list_vector_indexes(args.corpus)
    if command == "import-vectors":
        data = prepared["vectors"]
        if set(data) != {"profile", "entries"}:
            raise DomainError("invalid_input", "Vector import requires exactly profile and entries")
        return engine.import_vectors(args.corpus, args.snapshot, data["profile"], data["entries"])
    if command == "status":
        return engine.get_corpus_status(args.corpus)
    if command == "ingest":
        return engine.ingest(args.corpus, prepared["records"], args.idempotency_key)
    if command == "assertions":
        return engine.stage_assertions(args.job, prepared["assertions"])
    if command == "publish":
        return engine.publish_snapshot(args.job, label=args.label, allow_exclusions=args.allow_exclusions)
    if command == "job":
        return engine.get_job(args.job)
    if command == "cancel":
        return engine.cancel_job(args.job)
    if command == "snapshots":
        return engine.list_snapshots(args.corpus)
    if command == "snapshot":
        return engine.get_snapshot(args.id)
    if command == "search":
        extra = {}
        if args.vector_index or args.query_vector:
            if args.query_vector:
                value = prepared["query_vector"]
                if set(value) != {"vector", "profile"}:
                    raise DomainError("invalid_input", "Query embedding requires exactly vector and profile")
                extra = {"vector_index_id": args.vector_index, "query_vector": value["vector"], "embedding_profile": value["profile"]}
            else:
                return engine.search_local(args.corpus, args.query, vector_index_id=args.vector_index,
                    snapshot_id=args.snapshot, knowledge_cutoff=args.knowledge_cutoff, valid_time=args.valid_time,
                    mode=args.mode, limit=args.limit, page_size=args.page_size, budget=prepared.get("budget"))
        return engine.search(
            args.corpus, args.query, snapshot_id=args.snapshot,
            knowledge_cutoff=args.knowledge_cutoff, valid_time=args.valid_time,
            mode=args.mode, limit=args.limit, page_size=args.page_size,
            budget=prepared.get("budget"), **extra,
        )
    if command == "evidence":
        return engine.get_evidence(
            args.corpus, args.snapshot, chunk_id=args.chunk, assertion_id=args.assertion,
            knowledge_cutoff=args.knowledge_cutoff, history=args.history,
        )
    if command == "run":
        return engine.get_run(args.id)
    if command == "page":
        return engine.page(args.cursor)
    if command == "baseline":
        if args.action == "save":
            return engine.save_baseline(
                args.run, kind=args.kind, finding_ids=args.finding_id,
                seed_entity_ids=args.entity_id, hops=args.hops,
            )
        if args.action == "get":
            return engine.get_baseline(args.id)
        return engine.list_baselines(args.corpus)
    if command == "compare":
        return engine.compare(
            args.baseline, target_snapshot_id=args.target_snapshot, mode=args.mode,
            knowledge_cutoff=args.knowledge_cutoff,
            valid_from_time=args.valid_from, valid_to_time=args.valid_to,
            budget=prepared.get("budget"),
        )
    if command == "investigation":
        if args.action == "save":
            return engine.save_investigation(
                prepared["investigation"], expected_version=args.expected_version
            )
        if args.action == "get":
            return engine.get_investigation(args.id)
        return engine.list_investigations(args.corpus)
    if command == "export":
        return engine.export_evidence(args.run, args.output)
    raise DomainError("invalid_arguments", f"unknown operation: {command}", {})


def main(argv: Sequence[str] | None = None, *, engine_factory: Callable | None = None) -> int:
    engine = None
    try:
        args = build_parser().parse_args(argv)
        prepared = _prepare(args)
        if args.command == "demo":
            from .demo import run_demo
            result = run_demo(args.db, args.output)
        elif args.command == "serve":
            from .web import serve
            serve(args.db, host=args.host, port=args.port)
            return 0
        else:
            if engine_factory is None:
                from .engine import Engine
                engine_factory = Engine
            engine = engine_factory(args.db)
            result = _dispatch(engine, args, prepared)
        print(json.dumps({"ok": True, "operation": args.command, "data": result}, ensure_ascii=True, sort_keys=True))
        return 0
    except DomainError as exc:
        print(json.dumps({"ok": False, "error": exc.to_dict()}, ensure_ascii=True, sort_keys=True))
        return 2
    except (OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": {"code": "io_error", "message": str(exc), "details": {}}}, ensure_ascii=True))
        return 2
    except sqlite3.Error as exc:
        print(json.dumps({"ok": False, "error": {"code": "storage_error", "message": str(exc), "details": {}}}, ensure_ascii=True))
        return 2
    finally:
        if engine is not None:
            close = getattr(engine, "close", None)
            if close is not None:
                close()


if __name__ == "__main__":
    sys.exit(main())
