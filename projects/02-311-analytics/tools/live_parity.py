"""Opt-in synthetic-fixture parity on a real, separately provisioned Elasticsearch.

Never starts a server. Every invocation creates its own index; existing indices
cannot be selected. Outputs and index are retained unless --cleanup is explicit.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time
import uuid

from analytics311 import __version__
from analytics311.elastic import ElasticClient
from analytics311.errors import AnalyticsError
from analytics311.ingest import freeze_index, ingest_jsonl, normalize_record
from analytics311.resources import asset_path
from analytics311.service import AnalyticsService, atomic_json, canonical, file_hash, read_json


def _require(condition, code="parity_failed"):
    if not condition:
        raise AnalyticsError(code, "Live parity check failed; inspect its bounded evidence report.")


def _ids(*numbers):
    return [f"FIX-{number:03}" for number in numbers]


def cases():
    """Authored membership anchors; never infer these from the live engine."""
    base = {"schema_version": "1", "dataset_version": "live-parity-fixture-v1",
            "operation": "records", "as_of": "2026-01-02T12:00:00-05:00",
            "timezone": "America/New_York", "preview_limit": 2,
            "time": {"field": "created_date", "gte": "2025-11-01T00:00:00-04:00", "lt": "2026-01-01T00:00:00-05:00"}}
    rodent = {"field": "complaint_type", "op": "eq", "value": "Rodent"}
    all_ids = _ids(*range(1, 33))
    brooklyn = _ids(1, 2, 3, 4, 11, 13, 17, 18, 19, 20, 21, 22, 23, 32)
    rodents = _ids(1, 2, 5, 7, 9, 13, 14, 16, 17, 18, 19, 20, 24, 26, 27, 29, 31)
    metrics = ["count", "closed_count", "open_count", "mean_closure_hours"]
    result = []

    def add(name, ids, **changes):
        result.append({"name": name, "expected_ids": ids, "spec": {**copy.deepcopy(base), **changes}})

    add("all-records", all_ids)
    add("noise-last-month", _ids(21, 22, 23, 32), time={"preset": "last_month"},
        filters={"all": [{"field": "borough", "op": "eq", "value": "BROOKLYN"}, {"category_family": "noise"}]})
    add("nested-and-or-not-range", _ids(1, 2, 18, 20, 26), filters={"all": [rodent,
        {"any": [{"field": "borough", "op": "eq", "value": "BROOKLYN"}, {"field": "borough", "op": "eq", "value": "QUEENS"}]},
        {"not": {"field": "status", "op": "eq", "value": "Open"}},
        {"field": "closure_hours", "op": "range", "value": {"gte": 24, "lte": 48}}]})
    add("closed-missing-duration", _ids(13), filters={"all": [rodent,
        {"field": "is_closed", "op": "eq", "value": True}, {"field": "closure_hours", "op": "exists", "value": False}]})
    add("dst-half-open", _ids(15), time={"field": "created_date", "gte": "2025-11-02T01:15:00-04:00", "lt": "2025-11-02T01:45:00-04:00"})
    add("geo-radius", _ids(1, 2, 3, 17, 18, 21, 32), geo={"type": "radius", "lat": 40.68, "lon": -73.95, "distance_m": 1500})
    add("geo-bbox", brooklyn, geo={"type": "bbox", "top_left": {"lat": 40.71, "lon": -73.96}, "bottom_right": {"lat": 40.67, "lon": -73.93}})
    add("geo-polygon", brooklyn, geo={"type": "polygon", "points": [
        {"lat": 40.67, "lon": -73.96}, {"lat": 40.67, "lon": -73.93},
        {"lat": 40.71, "lon": -73.93}, {"lat": 40.71, "lon": -73.96}]})
    add("nested-aggregation", all_ids, operation="aggregate", group_by=[{"field": "borough"}, {"field": "complaint_type"}], metrics=metrics, top_n=2)
    add("calendar-zero-fill", _ids(21, 22, 23, 25, 32), operation="aggregate", time={"preset": "last_month"},
        filters={"category_family": "noise"}, group_by=[{"field": "created_date", "interval": "week"}, {"field": "borough"}], metrics=metrics, top_n=2)
    add("closure-by-agency", all_ids, operation="aggregate", group_by=[{"field": "agency"}], metrics=metrics, top_n=2)
    add("empty-aggregate", [], operation="aggregate", filters={"field": "unique_key", "op": "eq", "value": "ABSENT"}, metrics=metrics)
    periods = {"baseline": {"gte": base["time"]["gte"], "lt": "2025-12-01T00:00:00-05:00"},
               "current": {"gte": "2025-12-01T00:00:00-05:00", "lt": base["time"]["lt"]}}
    add("neighborhood-trends", rodents, operation="compare_periods", filters=rodent,
        group_by=[{"field": "nta2020"}], metrics=metrics, periods=periods, top_n=2)
    result[-1]["spec"].pop("time")
    periods = copy.deepcopy(periods)
    periods["baseline"]["lt"] = "2025-11-03T00:00:00-05:00"
    add("zero-baseline-trends", _ids(1, 16, 17, 18, 19, 20, 24, 26, 27, 29, 31), operation="compare_periods", filters=rodent,
        group_by=[{"field": "nta2020"}], metrics=metrics, periods=periods, top_n=2)
    result[-1]["spec"].pop("time")
    return result


class TrackedClient(ElasticClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.counts = {"pit_open": 0, "pit_close": 0, "record_continuations": 0, "composite_continuations": 0}

    def request(self, method, path, body=None):
        value = super().request(method, path, body)
        if method == "POST" and "/_pit?" in path:
            self.counts["pit_open"] += 1
        elif method == "DELETE" and path == "/_pit":
            self.counts["pit_close"] += 1
        if isinstance(body, dict):
            if "search_after" in body:
                self.counts["record_continuations"] += 1
            if "after" in body.get("aggs", {}).get("groups", {}).get("composite", {}):
                self.counts["composite_continuations"] += 1
        return value


def _owned_identity(client, index, run_id, expected_uuid=None):
    _require(re.fullmatch(r"[0-9a-f]{32}", run_id) and index == f"analytics311-parity-{run_id}-v1", "cleanup_refused")
    settings = client.request("GET", f"/{index}/_settings")
    mappings = client.request("GET", f"/{index}/_mapping")
    _require(set(settings) == {index} and set(mappings) == {index}, "cleanup_refused")
    actual = settings[index].get("settings", {}).get("index", {}).get("uuid")
    token = mappings[index].get("mappings", {}).get("_meta", {}).get("parity_run_id")
    _require(isinstance(actual, str) and bool(actual) and token == run_id, "cleanup_refused")
    _require(expected_uuid is None or actual == expected_uuid, "cleanup_refused")
    return actual


def _cleanup_owned(client, index, run_id, index_uuid, created):
    _require(created is True and isinstance(index_uuid, str) and bool(index_uuid), "cleanup_refused")
    _owned_identity(client, index, run_id, index_uuid)
    response = client.request("DELETE", f"/{index}?expand_wildcards=none&allow_no_indices=false&ignore_unavailable=false")
    _require(response.get("acknowledged") is True, "cleanup_failed")


def _same(expected, observed):
    """Only floats use tolerance; integer counts, keys and nulls remain exact."""
    if isinstance(expected, dict):
        return (isinstance(observed, dict) and set(expected) == set(observed)
                and all(_same(value, observed[key]) for key, value in expected.items()))
    if isinstance(expected, list):
        return isinstance(observed, list) and len(expected) == len(observed) and all(_same(a, b) for a, b in zip(expected, observed))
    if type(expected) is float:
        return type(observed) in (int, float) and math.isfinite(observed) and math.isclose(expected, observed, rel_tol=1e-9, abs_tol=1e-9)
    return type(expected) is type(observed) and expected == observed


def _all_rows(service, result):
    rows, cursors = list(result["rows"]), set()
    while result.get("next_cursor"):
        cursor = result["next_cursor"]
        _require(cursor not in cursors and len(rows) <= 100)
        cursors.add(cursor)
        result = service.get_result(result["result_id"], cursor=cursor, page_size=2)
        rows.extend(result["rows"])
    _require(len(rows) <= 100)
    return rows


def _csv_membership(job, expected_ids):
    _require(job.get("status") == "complete" and job.get("complete") is True and job.get("cohort_scope") == "all_matching")
    path = Path(job["file"])
    before = path.stat()
    _require(before.st_size <= 4096 and job.get("columns") == ["unique_key"])
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        _require(reader.fieldnames == ["unique_key"])
        ids = []
        for row in reader:
            _require(set(row) == {"unique_key"} and isinstance(row["unique_key"], str) and len(ids) < 32)
            ids.append(row["unique_key"])
    digest = file_hash(path)
    after = path.stat()
    _require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns))
    _require(len(ids) == len(set(ids)), "duplicate_export_id")
    _require(sorted(ids) == sorted(expected_ids), "membership_mismatch")
    _require(job.get("rows_written") == len(ids) and digest == job.get("sha256"))
    return {"rows": len(ids), "ids": sorted(ids), "duplicate_ids": 0, "sha256": digest, "bytes": after.st_size}


def _anchors(name, rows):
    """A few hand-calculated values also guard shared postprocessing mistakes."""
    if name == "calendar-zero-fill":
        _require(len(rows) == 10 and sum(row["count"] for row in rows) == 5)
        item = next(row for row in rows if row["group"] == {"created_date": "2025-12-15T00:00:00-05:00", "borough": "MANHATTAN"})
        _require(item["count"] == 0 and item["mean_closure_hours"] is None)
    if name == "neighborhood-trends":
        item = next(row for row in rows if row["group"] == {"nta2020": "FIXTURE-BK-B"})
        _require(item["baseline_count"] == 1 and item["current_count"] == 2 and item["relative_change"] == 1)
        _require(item["baseline_days"] == 30 and item["current_days"] == 31)
        _require(item["baseline_metrics"]["closed_count"] == 1 and item["baseline_metrics"]["mean_closure_hours"] is None)
        _require(item["current_metrics"]["mean_closure_hours"] == 48)
    if name == "zero-baseline-trends":
        item = next(row for row in rows if row["group"] == {"nta2020": "FIXTURE-QN-A"})
        _require(item["baseline_count"] == 0 and item["current_count"] == 2 and item["relative_change"] is None)
    if name == "closure-by-agency":
        item = next(row for row in rows if row["group"] == {"agency": "DOHMH"})
        _require(item["count"] == 17 and item["closed_count"] == 12 and item["open_count"] == 5)
        _require(math.isclose(item["mean_closure_hours"], 457 / 11))
    if name == "empty-aggregate":
        _require(len(rows) == 1 and rows[0]["count"] == 0 and rows[0]["mean_closure_hours"] is None)


def _prepare(directory):
    records = [normalize_record(json.loads(line)) for line in asset_path("fixtures/requests.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    _require(len(records) == 32 and {row["unique_key"] for row in records} == set(_ids(*range(1, 33))))
    # Ordering gives both engines the same explicitly bounded record preview.
    records.sort(key=lambda row: (datetime.fromisoformat(row["created_date"].replace("Z", "+00:00")), row["unique_key"]))
    source = directory / "fixture.jsonl"
    source.write_text("".join(canonical(record) + "\n" for record in records), encoding="utf-8")
    manifest = read_json(asset_path("fixtures/manifest.json"))
    manifest.update(dataset_version="live-parity-fixture-v1", source_kind="authored_synthetic_records", sha256=file_hash(source))
    atomic_json(directory / "fixture-manifest.json", manifest)
    atomic_json(directory / "catalog.json", read_json(asset_path("config/catalog.json")))
    config = {"backend": "fixture", "fixture_path": "fixture.jsonl", "manifest_path": "fixture-manifest.json",
              "catalog_path": "catalog.json", "runs_dir": "reference-runs", "export_inline": True,
              "budgets": {"max_fixture_rows": 32, "max_groups": 100, "page_size": 2, "deadline_seconds": 30,
                          "max_export_rows": 32, "max_export_bytes": 4096, "export_deadline_seconds": 30}}
    atomic_json(directory / "reference.json", config)
    return source, manifest, config


def run_parity(elastic_url, output_dir, *, provision_fixture=False, allow_insecure_local=False, cleanup=False):
    """Create one isolated fixture, run real engine parity, preserve a report.

    No caller-selected index, fake transport or reference-as-live mode exists.
    Unit tests patch transport explicitly; their reports are temporary test data.
    """
    _require(provision_fixture is True, "provisioning_not_authorized")
    _require(type(cleanup) is bool and type(allow_insecure_local) is bool, "invalid_spec")
    client = TrackedClient(elastic_url, allow_insecure_local=allow_insecure_local, timeout=30)
    directory = Path(output_dir)
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise AnalyticsError("invalid_spec", "Evidence directory already exists; choose a new directory.") from None
    run_id = uuid.uuid4().hex
    index = f"analytics311-parity-{run_id}-v1"
    created, index_uuid = False, None
    started = time.monotonic()
    report = {"runner_version": "1", "package_version": __version__, "run_id": run_id,
              "started_at": datetime.now(timezone.utc).isoformat(), "scope": "live_elasticsearch_synthetic_fixture_parity",
              "passed": False, "overall_release_verified": False, "visual_parity_verified": False,
              "real_data_verified": False, "scale_verified": False, "agent_accuracy_verified": False,
              "index": index, "cleanup": {"requested": cleanup, "deleted": False}, "cases": [],
              "limitations": ["32 authored records; not NYC findings or a millions-of-records test.",
                              "Reference execution shares service orchestration; hand-authored membership and selected metric anchors supplement it.",
                              "Approximate percentiles and geographic boundary precision are not certified.",
                              "No Kibana rendering, held-out agent evaluation, throughput or server capacity claim."]}
    stage = "prepare"
    try:
        source, manifest, config = _prepare(directory)
        report["fixture"] = {"kind": manifest["kind"], "row_count": 32, "sha256": manifest["sha256"], "coverage_complete_for_authored_fixture_only": True}
        reference = AnalyticsService(directory / "reference.json")
        expected = []
        # Validate the authored oracle BEFORE any remote mutation.
        for case in cases():
            result = reference.run_analysis(case["spec"])
            rows = _all_rows(reference, result)
            _require(result["total"] == {"value": len(case["expected_ids"]), "relation": "eq"}, "oracle_failed")
            _anchors(case["name"], rows)
            _csv_membership(reference.export_csv(result["result_id"], "records", "all_matching", columns=["unique_key"]), case["expected_ids"])
            expected.append((case, result, rows))
        stage = "server_version"
        server = client.request("GET", "/").get("version", {})
        _require(isinstance(server.get("number"), str) and bool(server["number"]))
        report["elasticsearch"] = {key: server[key] for key in ("number", "build_flavor", "build_type", "lucene_version") if key in server}
        stage = "create_index"
        definition = read_json(asset_path("config/mapping.json"))
        definition["mappings"]["_meta"]["parity_run_id"] = run_id
        definition["settings"].update({"index.default_pipeline": "_none", "index.final_pipeline": "_none"})
        response = client.request("PUT", f"/{index}", definition)
        _require(response.get("acknowledged") is True and response.get("index") == index, "creation_unconfirmed")
        created = True
        index_uuid = _owned_identity(client, index, run_id)
        report["index_uuid"] = index_uuid
        stage = "ingest"
        progress = ingest_jsonl(source, client, index, batch_size=7, checkpoint_path=directory / "ingestion.json", normalized=True)
        _require(progress["complete"] is True and progress["processed_rows"] == 32)
        stage = "freeze"
        frozen = freeze_index(client, index, expected_count=32)
        _require(frozen["index_uuid"] == index_uuid, "snapshot_changed")
        atomic_json(directory / "elastic-manifest.json", {**manifest, **frozen})
        config.update(backend="elastic", index=index, elastic_url=elastic_url, allow_insecure_local=allow_insecure_local,
                      manifest_path="elastic-manifest.json", runs_dir="elastic-runs")
        atomic_json(directory / "elastic.json", config)
        service = AnalyticsService(directory / "elastic.json")
        service.backend.client = client
        for case, baseline, expected_rows in expected:
            stage = "case:" + case["name"]
            item = {"name": case["name"], "passed": False, "spec": case["spec"], "expected_ids": case["expected_ids"]}
            report["cases"].append(item)
            observed = service.run_analysis(case["spec"])
            _require(observed.get("execution_complete") is True and observed.get("evidence_level") == "elastic_execution" and observed.get("approximate") is False)
            item["total"] = observed["total"]
            _require(observed["total"] == baseline["total"] and observed["group_count"] == baseline["group_count"])
            actual_rows = _all_rows(service, observed)
            if case["spec"]["operation"] == "records":
                item["preview_ids"] = [row["unique_key"] for row in actual_rows]
                _require(item["preview_ids"] == [row["unique_key"] for row in expected_rows])
            else:
                item.update(expected_rows=expected_rows, actual_rows=actual_rows)
                _require(_same(expected_rows, actual_rows), "aggregate_mismatch")
                _anchors(case["name"], actual_rows)
            item["csv"] = _csv_membership(service.export_csv(observed["result_id"], "records", "all_matching", columns=["unique_key"]), case["expected_ids"])
            item["passed"] = True
            atomic_json(directory / "report.json", report)
        stage = "pagination"
        _require(client.counts["record_continuations"] > 0 and client.counts["composite_continuations"] > 0)
        _require(client.counts["pit_open"] > 0 and client.counts["pit_open"] == client.counts["pit_close"])
        report["passed"] = True
    except AnalyticsError as exc:
        report["error"] = {"stage": stage, "code": exc.code}
    except (OSError, ValueError, TypeError, KeyError, StopIteration, csv.Error):
        report["error"] = {"stage": stage, "code": "parity_failed"}
    finally:
        report["pagination"] = client.counts
        report["index_creation_confirmed"] = created
        if cleanup and created and index_uuid:
            try:
                _cleanup_owned(client, index, run_id, index_uuid, created)
                report["cleanup"]["deleted"] = True
            except AnalyticsError as exc:
                report["cleanup"]["error_code"] = exc.code
                report["passed"] = False
            except (OSError, ValueError, TypeError, KeyError):
                report["cleanup"]["error_code"] = "cleanup_failed"
                report["passed"] = False
        report["elapsed_seconds"] = round(time.monotonic() - started, 6)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(directory / "report.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elastic-url", required=True, help="Existing Elasticsearch origin; credentials use ELASTIC_API_KEY")
    parser.add_argument("--output-dir", required=True, help="New evidence directory; never overwritten")
    parser.add_argument("--provision-fixture", action="store_true", help="Explicitly authorize creation of a new synthetic index")
    parser.add_argument("--allow-insecure-local", action="store_true", help="Allow unauthenticated HTTP on loopback only")
    parser.add_argument("--cleanup", action="store_true", help="Delete only this invocation's UUID/ownership-verified index; preserve evidence")
    args = parser.parse_args(argv)
    try:
        report = run_parity(args.elastic_url, args.output_dir, provision_fixture=args.provision_fixture,
                            allow_insecure_local=args.allow_insecure_local, cleanup=args.cleanup)
    except AnalyticsError as exc:
        print(json.dumps({"error": {"code": exc.code}}))
        return 2
    print(json.dumps({key: report.get(key) for key in ("passed", "scope", "index", "cleanup", "error")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
