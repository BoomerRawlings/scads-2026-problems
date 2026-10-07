"""Repeatable local source-hierarchy storage/query benchmark.

Run: python scripts/benchmark.py --output docs/benchmark-results.json
These synthetic records benchmark software, never model accuracy or calibration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import tempfile
import time

from orggraph.store import Store


def source_hierarchy(count: int, shape: str) -> dict:
    entities = [{"id": f"p-{index:06d}", "name": f"Person {index:06d}", "type": "person", "aliases": []} for index in range(count)]
    assertions = []
    for index in range(1, count):
        if shape == "mixed" and index % 997 == 0:
            continue
        parent = 0 if shape == "wide" or (shape == "mixed" and index <= 2500) else index - 1 if shape == "deep" else (index - 1) // 8
        assertions.append({"id": f"source-{index:06d}", "subject": f"p-{index:06d}", "object": f"p-{parent:06d}", "relation": "reports_to", "origin": "source", "reporting_type": "primary", "valid_from": "2026-01-01", "valid_to": None, "raw_score": None, "candidate_probability": None, "selected_probability": None, "calibration_status": "unavailable", "review_status": "unreviewed", "evidence_ids": ["synthetic-directory"]})
    return {"schema_version": 1, "corpus": {"id": f"benchmark-{shape}-{count}", "name": f"Synthetic {shape} hierarchy ({count})", "synthetic": True, "description": "Generated hierarchy only; no communication traffic or model accuracy evidence."}, "entities": entities, "messages": [], "assertions": assertions, "evidence": [{"id": "synthetic-directory", "kind": "source_assertion", "source_ref": "synthetic:benchmark-directory", "available": True, "text": "Fictional generated hierarchy for storage/query measurements."}], "labels": []}


def timed_reads(operation, repetitions: int):
    start = time.perf_counter()
    first_result = operation()
    first_ms = (time.perf_counter() - start) * 1000
    timings = []
    for _ in range(repetitions):
        start = time.perf_counter()
        result = operation()
        timings.append((time.perf_counter() - start) * 1000)
        assert result["snapshot"] == first_result["snapshot"]
    ordered = sorted(timings)
    return {"first_call_ms": round(first_ms, 3), "warm_median_ms": round(statistics.median(timings), 3), "warm_p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 3), "warm_max_ms": round(max(timings), 3), "repetitions": repetitions}, first_result


def benchmark_case(count: int, shape: str, repetitions: int, workspace: Path) -> dict:
    data = source_hierarchy(count, shape)
    with tempfile.TemporaryDirectory(prefix=f"{shape}-{count}-", dir=workspace) as temporary:
        # TemporaryDirectory recursively removes its newly created directory on
        # exit. Verify the resolved target is within this explicit task location.
        run_path = Path(temporary).resolve()
        if not run_path.is_relative_to(workspace):
            raise RuntimeError("Temporary benchmark directory escaped its workspace")
        db_path = run_path / "workspace.sqlite3"
        store = Store(db_path)
        start = time.perf_counter()
        imported = store.import_dataset(data, {"read": count, "accepted": count, "duplicate": 0, "quarantined": 0, "unsupported": 0, "issues": []})
        import_seconds = time.perf_counter() - start
        snapshot = imported["snapshot"]
        ws = store.workspace()
        assert ws["counts"]["people"] == count
        assert ws["counts"]["selected"] == len(data["assertions"])
        list_timing, page = timed_reads(lambda: store.entities(type="person", offset=0, limit=50, snapshot=snapshot), repetitions)
        assert len(page["items"]) == 50 and page["total"] == count
        second = store.entities(type="person", offset=50, limit=50, snapshot=snapshot)
        assert [item["id"] for item in page["items"] + second["items"]] == [f"p-{index:06d}" for index in range(100)]
        last = store.entities(type="person", offset=count - 50, limit=50, snapshot=snapshot)
        assert [item["id"] for item in last["items"]] == [f"p-{index:06d}" for index in range(count - 50, count)]
        search_timing, search = timed_reads(lambda: store.entities(q="Person 000", type="person", limit=50, snapshot=snapshot), repetitions)
        expected_search = sum("Person 000" in entity["name"] for entity in data["entities"])
        assert search["total"] == expected_search
        focus = f"p-{count - 1:06d}" if shape == "deep" else "p-000000"
        graph_timing, graph = timed_reads(lambda: store.graph(focus=focus, limit=200, snapshot=snapshot), repetitions)
        node_ids = {node["id"] for node in graph["nodes"]}
        assert focus in node_ids and len(node_ids) == graph["returned_nodes"] <= 200
        assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in graph["edges"])
        assert graph["omitted_nodes"] + graph["returned_nodes"] == count
        child_timing, children = timed_reads(lambda: store.entities(parent="p-000000", type="person", limit=200, snapshot=snapshot), repetitions)
        root_children = sorted(a["subject"] for a in data["assertions"] if a["object"] == "p-000000")
        seen_children = []
        for offset in range(0, children["total"], 200):
            sibling_page = store.entities(parent="p-000000", type="person", offset=offset, limit=200, snapshot=snapshot)
            assert sibling_page["snapshot"] == snapshot and sibling_page["total"] == len(root_children)
            seen_children.extend(item["id"] for item in sibling_page["items"])
        assert seen_children == root_children
        result = {"profile": shape, "people": count, "source_reporting_assertions": len(data["assertions"]), "communication_messages": 0, "import_seconds": round(import_seconds, 3), "database_mib": round(sum(path.stat().st_size for path in run_path.iterdir() if path.is_file()) / 1024 ** 2, 3), "list_page_50": list_timing, "substring_search_page_50": {**search_timing, "query": "Person 000", "matched": search["total"]}, "focus_graph_budget_200": {**graph_timing, "returned_nodes": graph["returned_nodes"], "returned_edges": len(graph["edges"]), "omitted_nodes": graph["omitted_nodes"]}, "children_page_200": {**child_timing, "root_children": len(root_children)}, "checks": {"population_and_selected_counts": "passed", "first_second_last_entity_pages": "passed", "all_root_sibling_pages_no_duplicates_or_skips": "passed", "snapshot_consistency": "passed", "bounded_graph_and_edge_closure": "passed"}}
        if shape == "deep":
            detail = store.detail(focus, snapshot)
            assert detail["ancestors_truncated"] is True and len(detail["ancestors"]) == 40
            result["checks"]["deep_ancestry_explicitly_truncated"] = "passed"
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/benchmark-results.json"))
    parser.add_argument("--repetitions", type=int, default=7)
    args = parser.parse_args()
    if args.repetitions < 2:
        parser.error("Use at least two repetitions")
    workspace = (Path(__file__).resolve().parent.parent / "runs" / "benchmark-tmp").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "environment": {"os": platform.system(), "os_release": platform.release(), "machine": platform.machine(), "processor": platform.processor(), "logical_cpus": os.cpu_count(), "python": platform.python_version(), "sqlite": sqlite3.sqlite_version}, "method": {"storage": "SQLite local temporary file; fresh database per profile", "read_path": "Python Store methods; excludes HTTP/browser/network/rendering", "warm_repetitions": args.repetitions, "cache_policy": "OS caches not flushed; first call follows import and is not a cold-cache measurement", "p95": "Nearest-rank percentile across warm repetitions; small descriptive sample", "graph_budget": 200, "source_dates": "2026-01-01", "view": "undated exploration"}, "limitations": ["Synthetic source hierarchy only; no communication-density, inference-accuracy, calibration, or unlabeled-transfer measurement.", "No browser frame-time, accessibility, network, multi-user concurrency, or end-to-end UI latency measurement.", "Pagination checks cover first/second/last entity pages and complete root-child pages, not every possible search/page sequence.", "Durations describe this local run; no universal scale claim."], "cases": []}
    for count, shape in [(10000, "mixed"), (100000, "mixed"), (10000, "wide"), (1000, "deep")]:
        result = benchmark_case(count, shape, args.repetitions, workspace)
        report["cases"].append(result)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"people": count, "profile": shape, "import_seconds": result["import_seconds"], "list_p95_ms": result["list_page_50"]["warm_p95_ms"], "search_p95_ms": result["substring_search_page_50"]["warm_p95_ms"], "graph_p95_ms": result["focus_graph_budget_200"]["warm_p95_ms"], "checks": "passed"}), flush=True)


if __name__ == "__main__":
    main()
