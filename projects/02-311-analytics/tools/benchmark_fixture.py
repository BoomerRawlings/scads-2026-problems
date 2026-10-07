"""Bounded reference-engine regression measurement; never an Elastic scale claim."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import time
import tracemalloc

from analytics311.fixture import FixtureBackend
from analytics311.workloads import generate


def scenarios():
    common = {"operation": "aggregate", "group_by": [{"field": "borough"}]}
    dates = [f"2025-06-{day:02}T00:00:00+00:00" for day in range(1, 29)]
    return {
        "count_only": dict(common, metrics=["count"]),
        "date_membership": dict(common, filters={"field": "created_date", "op": "in", "value": dates}),
        "date_range": dict(common, filters={"field": "created_date", "op": "range", "value": {
            "gte": "2025-04-01T00:00:00+00:00", "lt": "2025-10-01T00:00:00+00:00"}}),
        "polygon": dict(common, geo={"type": "polygon", "points": [
            {"lat": 40.68, "lon": -74.02}, {"lat": 40.8, "lon": -74.02},
            {"lat": 40.8, "lon": -73.9}, {"lat": 40.68, "lon": -73.9}]}),
        "closure_statistics": dict(common, metrics=["closed_count", "open_count", "mean_closure_hours",
                                                       "median_closure_hours", "p90_closure_hours"]),
    }


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def measure(path, backend_class, repeats):
    backend = backend_class({"fixture_path": str(path), "budgets": {"deadline_seconds": 120}}, {}, {})
    measurements = {}
    for name, spec in scenarios().items():
        expected = backend.execute(spec)  # Warm the filesystem cache; no query result cache.
        elapsed = []
        for _ in range(repeats):
            gc.collect()
            started = time.perf_counter()
            actual = backend.execute(spec)
            elapsed.append(time.perf_counter() - started)
            if actual != expected:
                raise RuntimeError("A repeated execution changed its answer")
        gc.collect()
        tracemalloc.start()
        actual = backend.execute(spec)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if actual != expected:
            raise RuntimeError("Memory measurement changed its answer")
        measurements[name] = {"spec": spec, "answer_sha256": digest(expected), "total": expected["total"],
                              "groups": len(expected["rows"]), "seconds": elapsed,
                              "median_seconds": statistics.median(elapsed), "python_peak_bytes": peak}
    return measurements


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--records", type=int, default=10000, choices=range(1, 100001), metavar="1..100000")
    parser.add_argument("--repeats", type=int, default=5, choices=range(1, 11), metavar="1..10")
    parser.add_argument("--backend-file", type=Path, help="Optional prior fixture.py source for a reproducible baseline")
    parser.add_argument("--compare", type=Path, help="Prior receipt; all answer hashes must agree")
    args = parser.parse_args()
    if not args.data.exists():
        generate(args.data, records=args.records, seed=7)
    sidecar = json.loads(args.data.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    data_hash = file_digest(args.data)
    if sidecar.get("row_count") != args.records or sidecar.get("seed") != 7 or sidecar.get("sha256") != data_hash:
        raise RuntimeError("Input must be the hash-verified seed7 generated corpus at the requested row count")
    backend_class = FixtureBackend
    if args.backend_file:
        module_spec = importlib.util.spec_from_file_location("analytics311._benchmark_backend", args.backend_file)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        backend_class = module.FixtureBackend
    source = args.backend_file or Path(__import__("analytics311.fixture", fromlist=["__file__"]).__file__)
    measurements = measure(args.data, backend_class, args.repeats)
    receipt = {"evidence_level": "measured_bounded_reference_only", "python": platform.python_version(),
               "platform": platform.system(), "records": args.records, "seed": 7, "repeats": args.repeats,
               "dataset_sha256": data_hash, "backend_source_sha256": file_digest(source),
               "recorded_at": datetime.now(timezone.utc).isoformat(),
               "measurements": measurements,
               "limits": ["Generated input; no NYC findings or Elasticsearch throughput measured.",
                          f"Warm filesystem cache; concurrent desktop load uncontrolled; {args.repeats} runs do not establish tail latency.",
                          "Tracemalloc measures Python allocations in a separate execution, not process RSS.",
                          "No large-dataset or multi-node extrapolation."]}
    if args.compare:
        prior = json.loads(args.compare.read_text(encoding="utf-8"))
        if prior["dataset_sha256"] != data_hash:
            raise RuntimeError("Comparison dataset differs")
        comparison = {}
        for name, measured in measurements.items():
            previous = prior["measurements"][name]
            if previous["spec"] != measured["spec"] or previous["answer_sha256"] != measured["answer_sha256"]:
                raise RuntimeError(f"Reference answer changed: {name}")
            comparison[name] = {"identical_answer": True,
                                "median_speedup": previous["median_seconds"] / measured["median_seconds"],
                                "python_peak_ratio_after_before": measured["python_peak_bytes"] / previous["python_peak_bytes"]}
        receipt["comparison"] = comparison
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"records": args.records, "cases": len(measurements), "comparison": receipt.get("comparison")}))


if __name__ == "__main__":
    main()
