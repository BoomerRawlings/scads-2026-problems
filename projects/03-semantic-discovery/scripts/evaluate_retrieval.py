"""Development retrieval diagnostics and bounded synthetic scaling measurements.

Reference labels are agent/source-inspected and partial. This script never
publishes a reference bundle or records human approval. It uses private in-memory
metadata indexes and compares both rankers on identical frozen authored queries.
"""
from __future__ import annotations

import argparse
from collections import Counter
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import sys
import sysconfig
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vopt.schema import validate_bundle
from vopt.search import build_index, search


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def connection_for(documents, assertions, profile):
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE documents(doc_id TEXT PRIMARY KEY,data TEXT)")
    connection.execute("CREATE TABLE assertions(assertion_id TEXT PRIMARY KEY,doc_id TEXT,model TEXT,attribute TEXT,data TEXT)")
    connection.execute("CREATE TABLE catalog_meta(key TEXT PRIMARY KEY,value TEXT)")
    connection.execute("INSERT INTO catalog_meta VALUES (?,?)", ("profile", json.dumps(profile)))
    connection.execute("INSERT INTO catalog_meta VALUES (?,?)", ("private_evaluation_only", "true"))
    connection.executemany("INSERT INTO documents VALUES (?,?)", [(d["doc_id"], json.dumps(d)) for d in documents])
    connection.executemany("INSERT INTO assertions VALUES (?,?,?,?,?)", [(a["assertion_id"], a["doc_id"], a["model"], a["attribute"], json.dumps(a)) for a in assertions])
    build_index(connection, documents, assertions)
    connection.commit()
    return connection


def synthetic_diagnostics():
    documents = [{"doc_id": "synthetic-" + kind, "title": "Authored synthetic " + kind + " diagnostic", "manufacturer": "Synthetic fixture",
                  "models": ["TEST-" + kind.upper()], "category": "generator", "language": "en", "revision": "1",
                  "request_ref": "fixture:synthetic-" + kind, "processing_status": "complete"} for kind in ("discrete", "rating")]
    facts = []
    for kind, attribute, qualifier, value, unit in [("discrete", "output_voltage", "rated", 125, "V"), ("discrete", "output_voltage", "rated", 250, "V"),
                                                   ("rating", "horsepower", "rated", 1, "hp"), ("rating", "horsepower", "peak", 3, "hp")]:
        facts.append({"assertion_id": f"synthetic-{kind}-{value}", "doc_id": "synthetic-" + kind, "model": "TEST-" + kind.upper(), "variant": None,
                      "attribute": attribute, "qualifier": qualifier, "value": value, "value_max": None, "unit": unit, "status": "reviewed"})
    return documents, facts


def reference_metadata():
    entries = [json.loads(line) for line in (ROOT / "data/corpus-manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = {entry["document"]["doc_id"]: entry for entry in entries if entry["admission_status"] == "admitted"}
    category_evidence = load(ROOT / "data/corpus/model-category-evidence.json")["documents"]
    documents = []
    for doc_id, entry in selected.items():
        doc = {key: value for key, value in entry["document"].items() if key in {"doc_id", "title", "manufacturer", "models", "model_categories", "category", "language", "revision"}}
        doc.update(request_ref=f"private-agent-reference:{doc_id}", processing_status="partial")
        if doc_id in category_evidence:
            evidence = category_evidence[doc_id]
            assert evidence["document_sha256"] == entry["sha256"], "Model-category evidence source changed"
            doc["model_categories"] = evidence["model_categories"]
        documents.append(doc)
    facts = []
    source_leads = load(ROOT / "data/corpus/evidence-leads.json")["leads"]
    for lead in source_leads:
        if lead["admission_status"] != "admitted" or lead["doc_id"] not in selected:
            continue
        assert selected[lead["doc_id"]]["sha256"] == lead["document_sha256"], "Source hash changed; reconcile reference labels before evaluation"
        fact = {key: lead[key] for key in ("doc_id", "model", "attribute", "value", "value_max", "unit", "qualifier")}
        fact.update(assertion_id=lead["lead_id"], variant=lead.get("variant"), status="reviewed")
        if lead.get("conditions"):
            fact["conditions"] = lead["conditions"]
        facts.append(fact)
    return documents, facts


def as_coverage(facts):
    return [{k: v for k, v in fact.items() if k not in {"value", "value_max", "unit", "conditions", "tolerance"}} for fact in facts]


def check_numeric_result(case, result, facts):
    """Independent numeric oracle over the fixed authored canonical predicates.

    It does not call the production parser, interval helpers, or predicate
    evaluator. This diagnoses returned-result constraint violations, not source
    extraction correctness; source reference and actual catalogs are separate.
    """
    failures = []
    conditions = {c.casefold() for c in case.get("conditions", [])}
    for constraint in case.get("constraints", []):
        relevant = [f for f in facts if f["doc_id"] == result["doc_id"] and f["model"] == result["model"]
                    and f.get("variant") in (None, result.get("variant")) and f["attribute"] == constraint["attribute"]
                    and (not constraint.get("qualifier") or f["qualifier"] == constraint["qualifier"])
                    and {c.casefold() for c in f.get("conditions", [])} <= conditions]
        if not relevant:
            failures.append({"attribute": constraint["attribute"], "reason": "No same-model applicable assertion"})
            continue
        intervals = []
        for fact in relevant:
            tolerance = fact.get("tolerance") or {"minus": 0, "plus": 0}
            low = fact["value"] - tolerance["minus"]
            high = (fact["value_max"] if fact["value_max"] is not None else fact["value"]) + tolerance["plus"]
            intervals.append((fact["qualifier"], low, high))
            value = constraint["value"]
            op = constraint["op"]
            okay = {"ge": low >= value - 1e-8, "gt": low > value + 1e-8, "le": high <= value + 1e-8,
                    "lt": high < value - 1e-8, "eq": abs(low-value) <= 1e-8 and abs(high-value) <= 1e-8,
                    "ne": high < value - 1e-8 or low > value + 1e-8,
                    "range": low >= value - 1e-8 and high <= constraint.get("value_max", value) + 1e-8}[op]
            if not okay:
                failures.append({"attribute": constraint["attribute"], "assertion_id": fact["assertion_id"], "reason": "Interval violates authored predicate"})
        for qualifier in {item[0] for item in intervals}:
            values = {(round(low, 8), round(high, 8)) for q, low, high in intervals if q == qualifier}
            if len(values) > 1:
                failures.append({"attribute": constraint["attribute"], "reason": "Conflicting same-qualifier observations were treated as certain"})
    return failures


def evaluate_dataset(name, documents, facts, profile, cases, reference=False):
    connection = connection_for(documents, facts, profile)
    methods = {}
    for method in ("lexical", "semantic"):
        rows = []
        totals = Counter()
        recall5 = []
        recall10 = []
        reciprocal = []
        for case in cases:
            start = time.perf_counter()
            result = search(connection, case["query"], limit=100, method=method)
            elapsed = (time.perf_counter() - start) * 1000
            expected_plan = case.get("plan_status", "ready")
            expected_status = case.get("status", "ready")
            numeric = bool(case.get("constraints"))
            if profile == "coverage" and numeric and expected_plan == "ready":
                expected_status = "unsupported"
            relevant = {tuple(value) for value in case["relevant"]} if expected_status == "ready" else set()
            returned = [(r["doc_id"], r["model"]) for r in result["results"]]
            known_recovered5 = len(set(returned[:5]) & relevant)
            known_recovered10 = len(set(returned[:10]) & relevant)
            first = next((index + 1 for index, key in enumerate(returned[:10]) if key in relevant), None)
            checks = [{"scope": [r["doc_id"], r["model"]], "violations": check_numeric_result(case, r, facts)} for r in result["results"]] if numeric else []
            totals["queries"] += 1
            totals["plan_status_correct"] += result["plan"]["status"] == expected_plan
            totals["runtime_status_matches_reference_expectation"] += result["status"] == expected_status
            totals["returned_numeric_scopes_checked"] += len(checks)
            totals["numeric_scopes_with_violations"] += sum(bool(check["violations"]) for check in checks)
            if relevant:
                totals["positive_query_denominator"] += 1
                totals["known_relevant_scope_denominator"] += len(relevant)
                totals["known_relevant_scopes_recovered_at_5"] += known_recovered5
                totals["known_relevant_scopes_recovered_at_10"] += known_recovered10
                recall5.append(known_recovered5 / len(relevant))
                recall10.append(known_recovered10 / len(relevant))
                reciprocal.append(1 / first if first else 0)
            rows.append({"id": case["id"], "slice": case["slice"], "track": case.get("track", "source-reference"), "query": case["query"],
                         "elapsed_ms": round(elapsed, 3), "status": result["status"], "expected_reference_status": expected_status,
                         "plan_status_matches_authored_expectation": result["plan"]["status"] == expected_plan,
                         "query_plan": result["plan"], "known_relevant_scopes": [list(value) for value in sorted(relevant)],
                         "returned_scopes": [list(value) for value in returned], "returned_scores": [r["score"] for r in result["results"]],
                         "returned_outside_partial_labels": [list(value) for value in returned if value not in relevant],
                         "numeric_constraint_checks": checks, "diagnostics": result["diagnostics"],
                         "known_relevant_recall_at_5": known_recovered5 / len(relevant) if relevant else None,
                         "known_relevant_recall_at_10": known_recovered10 / len(relevant) if relevant else None,
                         "reciprocal_rank_at_10": 1/first if first else (0 if relevant else None)})
        summary = dict(totals)
        for key in ("numeric_scopes_with_violations", "returned_numeric_scopes_checked", "positive_query_denominator", "known_relevant_scope_denominator"):
            summary.setdefault(key, 0)
        summary.update(macro_known_positive_recall_at_5=statistics.mean(recall5) if recall5 else None,
                       macro_known_positive_recall_at_10=statistics.mean(recall10) if recall10 else None,
                       mean_reciprocal_rank_at_10=statistics.mean(reciprocal) if reciprocal else None,
                       median_query_ms=statistics.median(row["elapsed_ms"] for row in rows),
                       interpretation="Authored development diagnostics. Partial labels cannot estimate corpus-wide precision/recall; actual-catalog status differences may reflect missing extraction/review coverage.")
        by_track = {}
        for track in sorted({row["track"] for row in rows}):
            subset = [row for row in rows if row["track"] == track]
            positives = [row for row in subset if row["known_relevant_scopes"]]
            by_track[track] = {"query_denominator": len(subset), "positive_query_denominator": len(positives),
                              "known_relevant_scope_denominator": sum(len(row["known_relevant_scopes"]) for row in positives),
                              "macro_known_positive_recall_at_10": statistics.mean(row["known_relevant_recall_at_10"] for row in positives) if positives else None,
                              "mean_reciprocal_rank_at_10": statistics.mean(row["reciprocal_rank_at_10"] for row in positives) if positives else None,
                              "plan_status_correct": sum(row["plan_status_matches_authored_expectation"] for row in subset),
                              "runtime_status_matches_reference_expectation": sum(row["status"] == row["expected_reference_status"] for row in subset),
                              "returned_numeric_scopes_checked": sum(len(row["numeric_constraint_checks"]) for row in subset),
                              "numeric_scopes_with_violations": sum(bool(check["violations"]) for row in subset for check in row["numeric_constraint_checks"])}
        methods[method] = {"summary": summary, "summary_by_track": by_track, "cases": rows}
    connection.close()
    return {"dataset": name, "profile": profile, "document_count": len(documents), "assertion_count": len(facts),
            "reference_only": reference, "synthetic_documents_added": 2, "methods": methods}


def peak_rss():
    if os.name == "nt":
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
                ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return counters.PeakWorkingSetSize
        return None
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


def scale_worker(size):
    docs, facts = [], []
    for index in range(size):
        doc_id, model = f"synthetic-{index:06}", f"SYN-{index:06}"
        docs.append({"doc_id": doc_id, "title": "Synthetic drill operating manual", "manufacturer": "Synthetic fixture", "models": [model],
                     "category": "drill", "language": "en", "revision": "1", "request_ref": "fixture:" + doc_id, "processing_status": "complete"})
        for attribute, value, unit in (("input_voltage", 120 if index % 2 else 230, "V"), ("weight", 1+index%10, "kg"), ("speed", 1000+index%5000, "rpm")):
            facts.append({"assertion_id": doc_id+"-"+attribute, "doc_id": doc_id, "model": model, "variant": None, "attribute": attribute,
                          "qualifier": "rated", "status": "reviewed", "value": value, "value_max": None, "unit": unit})
    start = time.perf_counter()
    connection = connection_for(docs, facts, "values")
    build_seconds = time.perf_counter()-start
    queries = [f"model SYN-{size//2:06}", "drills with input voltage >= 120 V and weight <= 5 kg", "speed", "weight below 3 kg or weight above 8 kg"]
    expected_counts = dict(zip(queries, [1, sum(1+index%10 <= 5 for index in range(size)), size,
                                        sum(1+index%10 < 3 or 1+index%10 > 8 for index in range(size))]))
    results = {}
    for method in ("lexical", "semantic"):
        samples = []
        for repeat in range(2):
            for query in queries:
                start = time.perf_counter()
                result = search(connection, query, limit=10, method=method)
                elapsed = time.perf_counter()-start
                assert result["status"] == "ready" and result["total_matches"] == expected_counts[query], "Scaling fixture constraint/count regression"
                samples.append({"query": query, "repeat": repeat, "seconds": round(elapsed, 6), "status": result["status"], "total_matches": result.get("total_matches", 0),
                                "expected_total_matches": expected_counts[query], "count_correct": True})
        times = sorted(item["seconds"] for item in samples)
        results[method] = {"samples": samples, "sample_count": len(samples), "median_seconds": statistics.median(times),
                           "p95_seconds_nearest_rank": times[math.ceil(.95*len(times))-1], "max_seconds": max(times)}
    database_bytes = connection.execute("PRAGMA page_count").fetchone()[0] * connection.execute("PRAGMA page_size").fetchone()[0]
    return {"document_count": size, "model_scopes": size, "assertion_count": len(facts), "build_seconds": round(build_seconds, 6),
            "in_memory_sqlite_bytes": database_bytes, "process_peak_resident_bytes": peak_rss(), "rankers": results,
            "fixture": "Entirely synthetic, one model/document, three assertions/model, no source PDF processing"}


def scaling():
    runs = []
    for size in (1000, 10000):
        result = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve()), "--scale-worker", str(size)], capture_output=True, text=True, timeout=300)
        if result.returncode:
            raise RuntimeError(result.stderr[-3000:])
        runs.append(json.loads(result.stdout))
    return {"label": "Synthetic local development scale measurements, not real-corpus coverage, throughput SLO, or production capacity",
            "implementation_hashes": {path: file_hash(ROOT/path) for path in ("vopt/search.py", "vopt/query.py", "vopt/ontology.py", "scripts/evaluate_retrieval.py")},
            "system": {"python": platform.python_version(), "interpreter_platform": sysconfig.get_platform(), "host_machine": platform.machine(),
                       "os": platform.system(), "logical_cpus": os.cpu_count(), "sqlite": sqlite3.sqlite_version},
            "measurement": "One fresh subprocess per size; wall time and process peak working set. Shared host load uncontrolled; two runs/query/ranker; no confidence interval.",
            "runs": runs}


def render_report(report):
    lines = ["# Retrieval development evaluation", "", "Agent-authored queries and partial agent/source-inspected references. No human accuracy, untouched generalization, or labor-savings claim.", "",
             "Both rankers execute the same hard-predicate compiler. The semantic comparator is ontology-normalized TF-IDF, not pretrained embeddings. Similar scores here do not establish semantic-model superiority.", "",
             "The table below excludes synthetic diagnostics; it covers the 33 source-reference query cases only.", "",
             "| Dataset | Profile | Ranker | Known positive queries | Known scopes | Recall@10 | MRR@10 | Plan statuses | Numeric violations / returned scopes checked |",
             "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for dataset in report["datasets"]:
        for method, result in dataset["methods"].items():
            m = result["summary_by_track"]["source-reference"]
            recall = f"{m['macro_known_positive_recall_at_10']:.3f}" if m['macro_known_positive_recall_at_10'] is not None else "n/a"
            mrr = f"{m['mean_reciprocal_rank_at_10']:.3f}" if m['mean_reciprocal_rank_at_10'] is not None else "n/a"
            lines.append(f"| {dataset['dataset']} | {dataset['profile']} | {method} | {m['positive_query_denominator']} | {m['known_relevant_scope_denominator']} | {recall} | {mrr} | {m['plan_status_correct']}/{m['query_denominator']} | {m['numeric_scopes_with_violations']}/{m['returned_numeric_scopes_checked']} |")
    lines += ["", "Recall and reciprocal rank include only queries with explicit known-positive scope labels. Unknown, negative, unsupported, and clarify cases remain in the status/plan denominator, never counted as automatically successful recall. Results rank document/model scopes; repeated documents with different models remain separate.", "",
              "Numeric violations are checked by a separate authored-predicate oracle against each evaluated catalog's same-model, same-variant observations. This is a retrieval-safety check, not evidence that extracted values match the originals. Unjudged returned scopes are recorded separately; partial labels do not justify corpus-wide precision.", "",
              "Source reference records live only in private in-memory evaluation indexes. They bypass release solely to diagnose retrieval with agent-reference values and are never saved as an approved bundle. Three synthetic discrete-value/rating queries are explicitly tagged and reported separately in `summary_by_track`; they are excluded from the table above.", "",
              "The actual development catalog contains selected agent-reviewed/corrected extractions. Its retrieval results must not be presented as automatic extraction precision. The separate complete original-M18 candidate audit (`data/corpus/m18-candidate-audit-v1.json`) records 17/17 numeric transcriptions supported but only 5/17 candidates with essential factual scope, including two duplicates. Nine needed scope repair and three had wrong entities. That one-version, one-document agent audit provides no recall or held-out accuracy estimate.", "",
              "Model-scoped categories were added after a development diagnosis: the workshop compendium's document category hid its compressors. Q23 is a repaired development case, not an untouched test. Discrete voltage alternatives still produce explicit conflict; they are not interpreted as a continuous range.", "", "## Status and recall differences", ""]
    for dataset in report["datasets"]:
        for method, result in dataset["methods"].items():
            differences = [row for row in result["cases"] if row["status"] != row["expected_reference_status"] or row["known_relevant_recall_at_10"] not in (None, 1.0)]
            lines.append(f"- {dataset['dataset']} / {dataset['profile']} / {method}: " + (", ".join(f"{row['id']} ({row['status']}; recall {row['known_relevant_recall_at_10']})" for row in differences) if differences else "all authored status and known-positive expectations met."))
    if report["pending_inputs"]:
        lines += ["", "Pending actual-catalog inputs: " + ", ".join(report["pending_inputs"]) + "."]
    lines += ["", "Inputs and query fixture hashes, inspectable plans, per-slice case outcomes, ranks, missing coverage, and exact denominators are in `retrieval-development.json`. Synthetic 1k/10k timings and process-memory observations are in `scaling.json`; they do not establish OCR or representative-corpus performance.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale-worker", type=int)
    parser.add_argument("--skip-scale", action="store_true")
    args = parser.parse_args()
    if args.scale_worker:
        print(json.dumps(scale_worker(args.scale_worker)))
        return
    cases = load(ROOT / "data/queries-development.json")["cases"]
    documents, facts = reference_metadata()
    synthetic_docs, synthetic_facts = synthetic_diagnostics()
    report = {"schema_version": 1, "label_kind": "Development diagnostics; agent-reference labels, no independent human gold", "datasets": [], "pending_inputs": [],
              "source_hashes": {path: file_hash(ROOT/path) for path in ("data/queries-development.json", "data/corpus/evidence-leads.json", "data/corpus-manifest.jsonl", "data/corpus/model-category-evidence.json")},
              "implementation_hashes": {path: file_hash(ROOT/path) for path in ("vopt/search.py", "vopt/query.py", "vopt/ontology.py", "scripts/evaluate_retrieval.py")},
              "reference_scope": {"admitted_documents": len(documents), "source_inspected_assertions": len(facts), "synthetic_documents": len(synthetic_docs), "synthetic_assertions": len(synthetic_facts)},
              "reference_adapter_note": "Internal search status='reviewed' is an adapter requirement only; in-memory records are agent-reference labels, never a released or human-approved catalog."}
    raw_audit = ROOT / "data/corpus/m18-candidate-audit-v1.json"
    if raw_audit.exists():
        audit = load(raw_audit)
        report["source_hashes"]["data/corpus/m18-candidate-audit-v1.json"] = file_hash(raw_audit)
        report["separate_raw_extraction_audit"] = {key: audit[key] for key in ("reviewer_kind", "human_gold", "scope", "processing_version", "counts", "important_limit")}
    for profile in ("values", "coverage"):
        profile_facts = facts+synthetic_facts if profile == "values" else as_coverage(facts+synthetic_facts)
        report["datasets"].append(evaluate_dataset("private_agent_reference", documents+synthetic_docs, profile_facts, profile, cases, reference=True))
        actual_path = ROOT / f"runs/development-{profile}.json"
        if actual_path.exists():
            actual = validate_bundle(load(actual_path))
            report["source_hashes"][f"runs/development-{profile}.json"] = file_hash(actual_path)
            additions = synthetic_facts if profile == "values" else as_coverage(synthetic_facts)
            report["datasets"].append(evaluate_dataset("agent_reviewed_extraction", actual["documents"]+synthetic_docs, actual["assertions"]+additions, profile, cases))
        else:
            report["pending_inputs"].append(f"runs/development-{profile}.json")
    save(ROOT / "reports/retrieval-development.json", report)
    (ROOT / "reports/retrieval-development.md").write_text(render_report(report), encoding="utf-8")
    if not args.skip_scale:
        save(ROOT / "reports/scaling.json", scaling())
    print(json.dumps({"datasets": len(report["datasets"]), "queries_per_ranker": len(cases), "pending_inputs": report["pending_inputs"], "reports": "reports/retrieval-development.json/.md and reports/scaling.json"}))


if __name__ == "__main__":
    main()
