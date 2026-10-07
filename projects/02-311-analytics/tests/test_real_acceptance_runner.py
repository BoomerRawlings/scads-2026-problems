"""Tiny deterministic orchestration checks; no real-data execution claim."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analytics311.contracts import normalize_spec
from analytics311.errors import AnalyticsError
from tools import run_real_acceptance as runner


SCOPE = {"gte": "2025-04-01T00:00:00-04:00", "lt": "2025-11-01T00:00:00-04:00",
         "baseline": {"gte": "2025-06-01T00:00:00-04:00", "lt": "2025-07-01T00:00:00-04:00"},
         "current": {"gte": "2025-10-01T00:00:00-04:00", "lt": "2025-11-01T00:00:00-04:00"}}


class RealAcceptanceRunnerTests(unittest.TestCase):
    def test_five_prospective_specs_valid_and_month_export_separate_from_point_day(self):
        suite = runner.build_suite("nyc311-test-v1", SCOPE, ["BK0101", "BK0102"])
        self.assertEqual(set(suite["analyses"]), {"filter", "group", "closure", "geo", "compare"})
        runner.measure_live.validate_suite(suite)
        for spec in [*suite["analyses"].values(), suite["export"]]:
            normalize_spec(spec, {})
        self.assertEqual(suite["export"]["filters"], suite["analyses"]["filter"]["filters"])
        self.assertEqual(suite["export"]["time"]["lt"], "2025-11-01T00:00:00-04:00")
        self.assertEqual(suite["analyses"]["filter"]["time"]["lt"], "2025-10-02T00:00:00-04:00")
        suite["export"]["filters"]["all"].clear()
        self.assertEqual(len(suite["analyses"]["filter"]["filters"]["all"]), 2)
        self.assertEqual(suite["analyses"]["compare"]["rank_by"], "rate_change")

    def test_oracle_selects_complete_month_and_separate_day_without_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            source, database = temp / "source.jsonl", temp / "oracle.sqlite"
            rows = [{"unique_key": str(number), "created_date": when, "borough": "BROOKLYN",
                     "complaint_type": "Noise - Residential", "location": {"lat": 40.7, "lon": -74.0}}
                    for number, when in enumerate(("2025-09-30T23:59:59-04:00", "2025-10-01T00:00:00-04:00",
                                                   "2025-10-15T12:00:00-04:00", "2025-10-31T23:59:59-04:00",
                                                   "2025-11-01T00:00:00-04:00"))]
            source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            runner.evaluation.build_database(source, database, min_free_bytes=0)
            oracle = runner.evaluation.Oracle(database, {}, [])
            self.addCleanup(oracle.close)
            suite = runner.build_suite("test", SCOPE, ["BK0101"])
            try:
                month = runner.query_ids(oracle, suite["export"], limit=runner.measure_live.MAX_CSV_ROWS)
                day = runner.query_ids(oracle, suite["analyses"]["filter"])
                self.assertEqual([row["unique_key"] for row in month], ["1", "2", "3"])
                self.assertEqual([row["unique_key"] for row in day], ["1"])
                with self.assertRaises(AnalyticsError): runner.query_ids(oracle, suite["export"], limit=2)
            finally:
                oracle.close()

    def test_independent_comparison_rejects_count_group_metric_or_ranking_drift(self):
        rows = [{"group": {"agency": "A"}, "count": 2}, {"group": {"agency": "B"}, "count": 1}]
        expected = {"membership": {"count": 3}, "rows": rows}
        saved = {"execution_complete": True, "evidence_level": "elastic_execution", "total": {"value": 3, "relation": "eq"},
                 "spec": {"operation": "aggregate"}, "all_rows": copy.deepcopy(rows)}
        runner.compare_result(saved, expected)
        for mutate in (lambda value: value["total"].update(value=4),
                       lambda value: value["all_rows"].pop(),
                       lambda value: value["all_rows"][0].update(count=3),
                       lambda value: value["all_rows"].reverse()):
            bad = copy.deepcopy(saved)
            mutate(bad)
            with self.assertRaises(AnalyticsError): runner.compare_result(bad, expected)

    def test_inline_export_restores_background_configuration_on_failure(self):
        class FakeService:
            config = {"export_inline": False}
            def export_csv(self, *args, **kwargs):
                assert self.config["export_inline"] is True
                raise AnalyticsError("budget_exceeded", "test")
        service = FakeService()
        with self.assertRaises(AnalyticsError): runner.export_inline(service, "saved", "records")
        self.assertFalse(service.config["export_inline"])

    def test_record_preview_membership_and_order_are_independent(self):
        expected = {"membership": {"count": 4}, "preview_ids": ["one", "two"]}
        saved = {"execution_complete": True, "evidence_level": "elastic_execution", "total": {"value": 4, "relation": "eq"},
                 "spec": {"operation": "records"}, "all_rows": [{"unique_key": "one"}, {"unique_key": "two"}]}
        runner.compare_result(saved, expected)
        saved["all_rows"].reverse()
        with self.assertRaises(AnalyticsError): runner.compare_result(saved, expected)

    def inputs(self, temp):
        nta = temp / "nta.json"
        nta.write_text(json.dumps({"sha256": "a" * 64, "residential_nta_codes": [f"N{i:03}" for i in range(197)]}))
        questions = temp / "questions.json"
        questions.write_text(json.dumps({"scope": SCOPE}))
        capture = {"source_kind": "real_public_records", "kind": "reconciled_public_capture", "extraction_complete": True,
                   "observed_complete": True, "row_count": 2000000, "unique_key_count": 2000000, "sha256": "b" * 64,
                   "bytes": 10, "coverage": {"gte": SCOPE["gte"], "lt": SCOPE["lt"], "complete": False}}
        return nta, questions, capture

    def test_provider_count_without_actual_capture_manifest_cannot_start_normalization(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            with patch.object(runner, "source_manifest", return_value={"row_count": 3000000}), patch.object(runner, "normalize_file") as normalize, contextlib.redirect_stdout(io.StringIO()):
                result = runner.run(temp / "raw.jsonl", temp / "boundaries", temp / "nta", temp / "new", "nyc311-test-v1")
            self.assertFalse(result["passed"])
            self.assertEqual(result["blocked_after"], "capture_preflight")
            normalize.assert_not_called()
            self.assertEqual(json.loads((temp / "new/acceptance.json").read_text())["stages"]["capture_preflight"]["status"], "failed")

    def test_maps_and_performance_failures_do_not_prevent_agent_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            nta, questions, capture = self.inputs(temp)
            output = temp / "run"
            normalized = {"row_count": 2000000}
            def ingest(arguments):
                runner.atomic_json(output / "index.manifest.json", {
                    "dataset_version": "nyc311-test-v1", "index_uuid": "uuid", "row_count": 2000000,
                    "ingestion": {"processed_rows": 2000000}, "immutable": True, "coverage": {"complete": False},
                    "comparison_qualification": {"scope": "test_fake_only"}})
                return 0
            with contextlib.ExitStack() as stack:
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                stack.enter_context(patch.object(runner, "source_manifest", return_value=capture))
                stack.enter_context(patch.object(runner, "file_hash", return_value="a" * 64))
                stack.enter_context(patch.object(runner, "normalize_file", return_value=normalized))
                stack.enter_context(patch.object(runner, "comparison_qualification", return_value={"scope": "test_fake_only"}))
                stack.enter_context(patch.object(runner.cli, "main", side_effect=ingest))
                stack.enter_context(patch.object(runner, "independent_checks", return_value={"passed": True, "artifacts": {}}))
                maps = stack.enter_context(patch.object(runner.live_maps, "provision", return_value={"passed": False}))
                perf = stack.enter_context(patch.object(runner.measure_live, "run_measurements", return_value={"passed": False}))
                freeze = stack.enter_context(patch.object(runner.evaluation, "prepare", return_value={"frozen": True}))
                result = runner.run(temp / "raw.jsonl", temp / "boundaries", nta, output, "nyc311-test-v1", questions=questions)
            self.assertFalse(result["passed"])
            self.assertFalse(result["overall_release_verified"])
            self.assertEqual(result["stages"]["maps_provision"]["status"], "failed")
            self.assertEqual(result["stages"]["performance_recovery"]["status"], "failed")
            self.assertEqual(result["stages"]["agent_study_freeze"]["status"], "passed")
            maps.assert_called_once()
            perf.assert_called_once()
            freeze.assert_called_once()
            catalog = json.loads((output / "catalog.json").read_text())
            self.assertEqual(catalog["residential_nta2020"], [f"N{i:03}" for i in range(197)])
            profile = json.loads((output / "profile.json").read_text())
            self.assertEqual(profile["budgets"]["max_concurrent_exports"], 2)

    def test_existing_output_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(AnalyticsError):
                runner.run("unused", "unused", "unused", directory, "nyc311-test-v1")


if __name__ == "__main__":
    unittest.main()
