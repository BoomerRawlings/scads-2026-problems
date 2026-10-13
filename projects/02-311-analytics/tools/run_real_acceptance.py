"""Run real-corpus acceptance from an existing reconciled capture on a live host.

No source download, service startup or model inference is performed here. Fresh
output and concrete index required. Optional map/performance failures are kept
separate; a valid analytical/oracle baseline can still freeze the agent study.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from analytics311 import cli
from analytics311.elastic import validate_index
from analytics311.errors import AnalyticsError
from analytics311.qualification import comparison_qualification
from analytics311.service import AnalyticsService, atomic_json, canonical, file_hash, read_json
from analytics311.workloads import normalize_file, source_manifest
from tools import agent_evaluation as evaluation
from tools import live_maps, measure_live


def require(condition, message):
    if not condition:
        raise AnalyticsError("acceptance_failed", message)


def build_suite(dataset_version, scope, residential_codes):
    """Fixed prospective families; no result-dependent query tuning."""
    base = {"schema_version": "1", "dataset_version": dataset_version, "timezone": "America/New_York",
            "as_of": "2025-11-15T12:00:00-05:00"}
    current = {"field": "created_date", **scope["current"]}
    begin = datetime.fromisoformat(scope["current"]["gte"])
    day = {"field": "created_date", "gte": begin.isoformat(), "lt": (begin + timedelta(days=1)).isoformat()}
    noise = {"all": [{"field": "borough", "op": "eq", "value": "BROOKLYN"},
                     {"field": "complaint_type", "op": "eq", "value": "Noise - Residential"}]}
    cases = {
        "filter": {**base, "operation": "records", "time": day, "filters": noise, "preview_limit": 5},
        "group": {**base, "operation": "aggregate", "time": current,
                  "group_by": [{"field": "borough"}, {"field": "agency"}], "metrics": ["count", "closed_count", "open_count"]},
        "closure": {**base, "operation": "aggregate", "time": current,
                    "filters": {"field": "complaint_type", "op": "eq", "value": "Rodent"},
                    "group_by": [{"field": "agency"}], "metrics": ["count", "closed_count", "mean_closure_hours"]},
        "geo": {**base, "operation": "aggregate", "time": current,
                "geo": {"type": "radius", "lat": 40.7128, "lon": -74.0060, "distance_m": 1000},
                "group_by": [{"field": "borough"}], "metrics": ["count"]},
        "compare": {**base, "operation": "compare_periods", "periods": {name: scope[name] for name in ("baseline", "current")},
                    "filters": {"all": [{"field": "complaint_type", "op": "eq", "value": "Rodent"},
                                        {"field": "nta2020", "op": "in", "value": list(residential_codes)}]},
                    "group_by": [{"field": "nta2020"}], "metrics": ["count", "mean_closure_hours"],
                    "rank_by": "rate_change", "rank_order": "desc", "minimum_count": 0, "top_n": 10},
    }
    export = copy.deepcopy(cases["filter"])
    export["time"] = copy.deepcopy(current)
    return {"analyses": cases, "export": export}


def compare_result(saved, reference):
    require(saved.get("execution_complete") is True and saved.get("evidence_level") == "elastic_execution",
            "Incomplete real-engine analysis.")
    require(saved.get("total") == {"value": reference["membership"]["count"], "relation": "eq"},
            "Source count differs from independent SQLite reference.")
    if saved["spec"]["operation"] == "records":
        require([row.get("unique_key") for row in saved["all_rows"]] == reference.get("preview_ids"),
                "Record preview membership/order differs from independent reference.")
        return
    actual = {canonical(row["group"]): row for row in saved["all_rows"]}
    expected = {canonical(row["group"]): row for row in reference["rows"]}
    require(len(actual) == len(saved["all_rows"]) and set(actual) == set(expected), "Complete aggregate group membership differs.")
    require(all(evaluation.numeric_equal(actual[group], row) for group, row in expected.items()), "Aggregate values differ from independent reference.")
    require([canonical(row["group"]) for row in saved["all_rows"]] == [canonical(row["group"]) for row in reference["rows"]],
            "Saved aggregate ranking differs from independent reference.")


def query_ids(oracle, spec, limit=live_maps.MAX_POINTS):
    where, parameters = oracle.where(spec)
    rows = []
    for row in oracle.db.execute("SELECT unique_key,latitude,longitude FROM requests WHERE " + where + " ORDER BY unique_key COLLATE BINARY", parameters):
        require(len(rows) < limit, "Map/CSV validation cohort exceeds its fixed bounded scope.")
        rows.append(dict(row))
    require(rows, "Predeclared map/export cohort is empty; retain failure rather than silently change the query.")
    return rows


def export_inline(service, result_id, mode, *, group_ids=None):
    """Same export pipeline in-process; asynchronous recovery measured separately."""
    previous = service.config.get("export_inline", False)
    service.config["export_inline"] = True
    try:
        job = service.export_csv(result_id, mode, "selected_groups" if group_ids is not None else "all_matching",
                                 columns=["unique_key"] if mode == "records" else None, group_ids=group_ids)
    finally:
        service.config["export_inline"] = previous
    require(job.get("status") == "complete" and job.get("complete") is True, "Verification CSV export did not complete.")
    return job


def independent_checks(config, normalized, database, suite, output, residential):
    """Oracle precedes and is independent of service execution/results."""
    metadata = evaluation.build_database(normalized, database)
    service = AnalyticsService(config)
    require(metadata["rows"] == service.manifest["row_count"]
            and metadata["source_sha256"] == service.manifest["ingestion"]["source_sha256"],
            "Oracle projection and frozen-index provenance differ.")
    oracle = evaluation.Oracle(database, service.catalog, residential)
    report = {"schema_version": 1, "passed": False, "reference_kind": "independent_sqlite_normalized_corpus",
              "source": metadata, "checks": {}, "cases": {},
              "limitations": ["Shares normalized records and NTA assignments; capture, normalization and geometry validity remain separate.",
                              "CSV semantic checks run the export pipeline inline; asynchronous resource/recovery tests are separate."]}
    try:
        for name, spec in suite["analyses"].items():
            reference = oracle.evaluate(spec)
            report["cases"][name] = {"spec": spec, "reference": reference, "passed": False}
            # Preserve an oracle generated before the service call, including a failure.
            atomic_json(output / "independent-parity.json", report)
            actual = service.run_analysis(spec)
            saved = service._load(actual["result_id"])
            compare_result(saved, reference)
            report["cases"][name].update(passed=True, result_id=actual["result_id"])
        export_rows = query_ids(oracle, suite["export"], limit=measure_live.MAX_CSV_ROWS)
        oracle_csv = output / "oracle-export-ids.csv"
        with oracle_csv.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["unique_key"])
            writer.writerows([row["unique_key"]] for row in export_rows)
        report["performance_export_oracle"] = {"spec": suite["export"], "rows": len(export_rows),
                                               "sha256": file_hash(oracle_csv), "columns": ["unique_key"],
                                               "export_columns": list(measure_live.EXPORT_COLUMNS)}
        rows = query_ids(oracle, suite["analyses"]["filter"])
        reference = {"kind": report["reference_kind"], "sha256": evaluation.digest(report["cases"]["filter"]["reference"])}
        points = {"dataset_version": service.manifest["dataset_version"], "reference": reference, "source_count": len(rows),
                  "unique_keys": [row["unique_key"] for row in rows],
                  "mapped_unique_keys": [row["unique_key"] for row in rows if row["latitude"] is not None and row["longitude"] is not None]}
        require(points["mapped_unique_keys"], "Predeclared point cohort contains no usable locations.")
        point_csv = export_inline(service, report["cases"]["filter"]["result_id"], "records")
        report["checks"]["points_csv"] = live_maps.inspect_csv(point_csv["file"], "requests", points)
        atomic_json(output / "point-expectation.json", points)
        comparison = report["cases"]["compare"]
        expected_groups = {row["group"]["nta2020"]: {name: row[name] for name in live_maps.METRIC_UNITS}
                           for row in comparison["reference"]["rows"] if row["group"]["nta2020"] is not None}
        require(expected_groups, "Predeclared residential trend cohort is empty.")
        trends = {"dataset_version": service.manifest["dataset_version"], "reference": {
            "kind": report["reference_kind"], "sha256": evaluation.digest(comparison["reference"])},
                  "groups": expected_groups, "excluded_group_count": 0}
        trend_csv = export_inline(service, comparison["result_id"], "aggregates")
        report["checks"]["trends_csv"] = live_maps.inspect_csv(trend_csv["file"], "neighborhood_trends", trends)
        atomic_json(output / "trend-expectation.json", trends)
        selected_codes = [row["group"]["nta2020"] for row in comparison["reference"]["rows"][:3]]
        saved = service._load(comparison["result_id"])
        selected_ids = [row["group_id"] for row in saved["all_rows"] if row["group"]["nta2020"] in selected_codes]
        require(len(selected_ids) == len(selected_codes), "Independent selected neighborhoods do not resolve to saved group IDs.")
        selected = {**trends, "groups": {code: expected_groups[code] for code in selected_codes}}
        selected_csv = export_inline(service, comparison["result_id"], "aggregates", group_ids=selected_ids)
        report["checks"]["selected_trends_csv"] = live_maps.inspect_csv(selected_csv["file"], "neighborhood_trends", selected)
        atomic_json(output / "selected-trend-expectation.json", selected)
        report["artifacts"] = {"point_result_id": report["cases"]["filter"]["result_id"], "trend_result_id": comparison["result_id"],
                               "point_csv_job_id": point_csv["job_id"], "trend_csv_job_id": trend_csv["job_id"],
                               "selected_trend_csv_job_id": selected_csv["job_id"], "selected_group_ids": selected_ids}
        report["passed"] = True
        return report
    finally:
        oracle.close()
        atomic_json(output / "independent-parity.json", report)


def run(raw, boundaries, nta_receipt, output_dir, index, *, capture_manifest=None,
        elastic_url="http://127.0.0.1:9200", kibana_url="http://127.0.0.1:5601",
        questions=evaluation.QUESTIONS, model=None, repeats=5,
        skip_maps=False, skip_performance=False):
    if model is None:
        model = read_json(ROOT / "docs/local-model-runtime.json")["model_alias"]
    output = Path(output_dir).resolve()
    require(not output.exists(), "Choose a new run directory; existing artifacts are never overwritten.")
    index = validate_index(index)
    output.mkdir(parents=True)
    raw, boundaries = Path(raw).resolve(), Path(boundaries).resolve()
    report = {"schema_version": 1, "started_at": datetime.now(timezone.utc).isoformat(), "passed": False,
              "overall_release_verified": False, "stages": {}, "index": index,
              "limitations": ["Observed reconciled corpus is not a transactionally isolated provider snapshot or complete citywide reporting.",
                              "Agent evaluation requires a subsequent actual model run and semantic review; freezing questions is not evaluation.",
                              "A passing finite performance suite does not establish maximum scale or an SLA."]}
    result = {}
    def stage(name, callback, *, required=False):
        begin = time.monotonic()
        item = {"status": "running"}
        report["stages"][name] = item
        atomic_json(output / "acceptance.json", report)
        print(json.dumps({"stage": name, "status": "running"}), flush=True)
        try:
            value = callback()
            if isinstance(value, dict) and value.get("passed") is False:
                raise AnalyticsError("acceptance_failed", "Stage retained a failing evidence receipt.")
            item["status"] = "passed"
            result[name] = value
            return True
        except Exception as exc:
            item.update(status="failed", error_code=exc.code if isinstance(exc, AnalyticsError) else type(exc).__name__)
            if isinstance(exc, AnalyticsError) and exc.code == "acceptance_failed": item["reason"] = exc.message
            if required: report["blocked_after"] = name
            return False
        finally:
            item["elapsed_seconds"] = time.monotonic() - begin
            atomic_json(output / "acceptance.json", report)
            print(json.dumps({"stage": name, **item}), flush=True)

    def preflight():
        captured = source_manifest(raw)
        supplied = read_json(capture_manifest) if capture_manifest else captured
        require(captured == supplied, "Explicit capture manifest differs from the hash-verified adjacent sidecar.")
        require(captured.get("source_kind") == "real_public_records" and captured.get("kind") == "reconciled_public_capture"
                and captured.get("extraction_complete") is True and captured.get("observed_complete") is True,
                "A locally captured reconciled real corpus is required.")
        n = captured.get("row_count")
        require(type(n) is int and n >= 2_000_000 and captured.get("unique_key_count") == n, "At least two million real unique captured rows required.")
        nta, protocol = read_json(nta_receipt), read_json(questions)
        require(file_hash(boundaries) == nta["sha256"], "Boundary bytes differ from official provenance receipt.")
        codes = nta["residential_nta_codes"]
        require(len(codes) == 197 and len(set(codes)) == 197, "Expected official 197 residential NTA codes.")
        a, b = [datetime.fromisoformat(captured["coverage"][key]) for key in ("gte", "lt")]
        require(a <= datetime.fromisoformat(protocol["scope"]["gte"]) < datetime.fromisoformat(protocol["scope"]["lt"]) <= b,
                "Capture does not cover the predeclared benchmark windows.")
        report["capture"] = {key: captured[key] for key in ("row_count", "unique_key_count", "sha256", "bytes", "coverage")}
        report["boundary_sha256"] = nta["sha256"]
        return captured, nta, protocol

    if not stage("capture_preflight", preflight, required=True): return report
    captured, nta, protocol = result["capture_preflight"]
    normalized = output / "normalized.jsonl"
    if not stage("normalize", lambda: normalize_file(raw, normalized, boundaries, max_output_bytes=8 * 1024 ** 3,
                                                     min_free_bytes=2 * 1024 ** 3), required=True): return report
    normal = result["normalize"]
    if not stage("comparison_qualification", lambda: require(comparison_qualification(normal) is not None,
                                                               "Normalized observed-window qualification failed."), required=True): return report
    catalog = read_json(ROOT / "config/catalog.json")
    catalog["residential_nta2020"] = nta["residential_nta_codes"]
    atomic_json(output / "catalog.json", catalog)
    profile = read_json(ROOT / "config/elastic.example.json")
    profile.update(index=index, elastic_url=elastic_url, catalog_path=str(output / "catalog.json"),
                   manifest_path=str(output / "index.manifest.json"), runs_dir=str(output / "runs"))
    profile["kibana"].update(url=kibana_url, result_index=index + "-trends", trend_metric="rate_change")
    profile["budgets"].update(deadline_seconds=120, max_export_rows=50000, export_deadline_seconds=180,
                              max_concurrent_exports=2)
    config = output / "profile.json"
    atomic_json(config, profile)
    def ingest():
        arguments = ["--config", str(config), "ingest", str(normalized), "--normalized-input", "--create-index",
                     "--mapping", str(ROOT / "config/mapping.json"), "--checkpoint", str(output / "ingest.json"),
                     "--batch-size", "500", "--freeze", "--coverage-start", captured["coverage"]["gte"],
                     "--coverage-end", captured["coverage"]["lt"]]
        with (output / "ingest-output.json").open("x", encoding="utf-8") as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            code = cli.main(arguments)
        require(code == 0, "Ingestion failed; inspect retained ingestion output/checkpoint.")
        manifest = read_json(output / "index.manifest.json")
        require(manifest["row_count"] == normal["row_count"] == captured["row_count"]
                and manifest["ingestion"]["processed_rows"] == captured["row_count"]
                and manifest["immutable"] is True and manifest["coverage"]["complete"] is False
                and comparison_qualification(manifest) is not None, "Captured, normalized and frozen index counts or qualification differ.")
        report["snapshot"] = {key: manifest[key] for key in ("dataset_version", "index_uuid", "row_count", "immutable", "coverage", "comparison_qualification")}
        return manifest
    if not stage("ingest_freeze", ingest, required=True): return report
    suite = build_suite(index, protocol["scope"], nta["residential_nta_codes"])
    atomic_json(output / "measurement-suite.json", suite)
    database = output / "oracle.sqlite"
    if not stage("independent_api_csv", lambda: independent_checks(config, normalized, database, suite, output, nta["residential_nta_codes"]), required=True): return report
    artifacts = result["independent_api_csv"]["artifacts"]
    active_config = config
    if not skip_maps:
        provisioned = stage("maps_provision", lambda: live_maps.provision(config, boundaries, index + "-boundaries",
                                                                         output / "maps-profile.json", output / "maps-provision.json"))
        if provisioned:
            active_config = output / "maps-profile.json"
            for name, mode, expectation, result_id, job_id, selected in (
                ("points", "requests", "point-expectation.json", artifacts["point_result_id"], artifacts["point_csv_job_id"], None),
                ("trends", "neighborhood_trends", "trend-expectation.json", artifacts["trend_result_id"], artifacts["trend_csv_job_id"], None),
                ("selected_trends", "neighborhood_trends", "selected-trend-expectation.json", artifacts["trend_result_id"], artifacts["selected_trend_csv_job_id"], artifacts["selected_group_ids"])):
                def render_one(mode=mode, expectation=expectation, result_id=result_id, job_id=job_id, selected=selected, name=name):
                    job = AnalyticsService(active_config).get_result(job_id)
                    return live_maps.render(active_config, result_id, mode, output / expectation, job["file"], output / ("render-" + name), group_ids=selected)
                stage("map_" + name, render_one)
    else:
        report["stages"]["maps_provision"] = {"status": "not_run", "reason": "explicit_skip"}
    if not skip_performance:
        stage("performance_recovery", lambda: measure_live.run_measurements(active_config, output / "measurement-suite.json",
                                                                           output / "measurements.json", output / "measurement-work",
                                                                           output / "oracle-export-ids.csv", repeats=repeats, timeout_seconds=1200))
    else:
        report["stages"]["performance_recovery"] = {"status": "not_run", "reason": "explicit_skip"}
    stage("agent_study_freeze", lambda: evaluation.prepare(active_config, normalized, database, output / "agent-freeze.json",
                                                          model=model, questions=questions, nta_receipt=nta_receipt))
    report["agent_config"] = active_config.name
    report["passed"] = all(item["status"] == "passed" for item in report["stages"].values())
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(output / "acceptance.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("raw", "boundaries", "nta-receipt", "output-dir", "index"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--capture-manifest", help="Defaults to raw JSONL's adjacent .manifest.json; explicit content must match that sidecar")
    parser.add_argument("--elastic-url", default="http://127.0.0.1:9200")
    parser.add_argument("--kibana-url", default="http://127.0.0.1:5601")
    parser.add_argument("--questions", type=Path, default=evaluation.QUESTIONS)
    parser.add_argument("--model", help="Defaults to model_alias in docs/local-model-runtime.json")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--skip-maps", action="store_true")
    parser.add_argument("--skip-performance", action="store_true")
    args = parser.parse_args(argv)
    result = run(**vars(args))
    print(json.dumps({"passed": result["passed"], "overall_release_verified": False, "stages": result["stages"]}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
