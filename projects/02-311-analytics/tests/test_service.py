"""End-to-end contract checks against independent authored fixture answers."""

import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from analytics311.errors import AnalyticsError
from analytics311.service import AnalyticsService


ROOT = Path(__file__).resolve().parents[1]


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for name in ("requests.jsonl", "manifest.json"):
            shutil.copyfile(ROOT / "fixtures" / name, self.directory / name)
        shutil.copyfile(ROOT / "config" / "catalog.json", self.directory / "catalog.json")
        self.config = {
            "backend": "fixture", "fixture_path": "requests.jsonl", "manifest_path": "manifest.json",
            "catalog_path": "catalog.json", "runs_dir": "runs", "export_inline": True,
            "budgets": {"max_fixture_rows": 100_000, "max_groups": 50_000, "deadline_seconds": 30, "max_export_rows": 100_000},
        }
        self.config_path = self.directory / "config.json"
        self.service = self.reload()

    def reload(self):
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        return AnalyticsService(self.config_path)

    @staticmethod
    def spec(**updates):
        spec = {"schema_version": "1", "dataset_version": "fixture-v1", "operation": "records",
                "as_of": "2026-01-02T12:00:00-05:00", "timezone": "America/New_York",
                "time": {"field": "created_date", "gte": "2025-11-01T00:00:00-04:00", "lt": "2026-01-01T00:00:00-05:00"}}
        spec.update(updates)
        return spec

    def example(self, name):
        return json.loads((ROOT / "examples" / f"{name}.json").read_text(encoding="utf-8"))

    def csv_rows(self, job):
        self.assertEqual(job["status"], "complete", job)
        self.assertTrue(job["complete"])
        with open(job["file"], encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def assert_error(self, code, call, *args, **kwargs):
        with self.assertRaises(AnalyticsError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_record_preview_exports_entire_selection(self):
        result = self.service.run_analysis(self.example("brooklyn-noise"))
        self.assertEqual(result["total"], {"value": 4, "relation": "eq"})
        self.assertEqual(len(result["rows"]), 2)
        self.assertTrue(result["preview_truncated"])
        self.assertTrue(result["execution_complete"])
        self.assertEqual(result["evidence_level"], "fixture_only")
        job = self.service.export_csv(result["result_id"], "records", "all_matching")
        self.assertEqual({row["unique_key"] for row in self.csv_rows(job)}, {"FIX-021", "FIX-022", "FIX-023", "FIX-032"})
        self.assertEqual(job["rows_written"], 4)
        self.assertEqual(job["bytes_written"], Path(job["file"]).stat().st_size)

    def test_default_preview_is_small_but_explicit_requests_totals_and_csv_stay_complete(self):
        request = {"dataset_version": "fixture-v1", "operation": "records"}
        result = self.service.run_analysis(request)
        self.assertNotIn("preview_limit", request)
        self.assertEqual(result["spec"]["preview_limit"], 5)
        self.assertEqual(len(result["rows"]), 5)
        self.assertEqual(result["total"], {"value": 32, "relation": "eq"})
        self.assertTrue(result["preview_truncated"])
        larger = self.service.run_analysis(dict(request, preview_limit=12))
        self.assertEqual(len(larger["rows"]), 12)
        self.assertEqual(larger["total"], result["total"])
        self.assertEqual(larger["rows"][:5], result["rows"])
        full_preview = self.service.run_analysis(dict(request, preview_limit=100))
        self.assertEqual(len(full_preview["rows"]), 32)
        self.assertFalse(full_preview["preview_truncated"])
        job = self.service.export_csv(result["result_id"], "records", "all_matching", columns=["unique_key"])
        exported = self.csv_rows(job)
        self.assertEqual(len(exported), 32)
        self.assertEqual({row["unique_key"] for row in exported}, {f"FIX-{number:03}" for number in range(1, 33)})

    def test_record_export_passes_requested_columns_to_source(self):
        result = self.service.run_analysis(self.example("brooklyn-noise"))
        with patch.object(self.service.backend, "iter_records", wraps=self.service.backend.iter_records) as source:
            job = self.service.export_csv(result["result_id"], "records", "all_matching", columns=["unique_key"])
        self.assertEqual(source.call_args.kwargs["source_fields"], ["unique_key"])
        self.assertEqual(self.csv_rows(job), [{"unique_key": key} for key in ("FIX-021", "FIX-022", "FIX-023", "FIX-032")])
        self.assertEqual(job["planned_rows"], 4)

    def test_export_bytes_fail_closed_independent_of_row_limit(self):
        self.config["budgets"]["max_export_bytes"] = 20
        service = self.reload()
        result = service.run_analysis(self.example("brooklyn-noise"))
        job = service.export_csv(result["result_id"], "records", "all_matching", columns=["unique_key"])
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error"]["code"], "budget_exceeded")
        self.assertFalse(job["complete"])
        self.assertFalse(list(service.runs.glob("*.csv*")))

    def test_export_admission_recovery_and_capacity_release(self):
        from analytics311.jobs import recover_exports
        self.config['export_inline'] = False
        self.config['budgets']['max_concurrent_exports'] = 1
        service = self.reload()
        result = service.run_analysis(self.example('brooklyn-noise'))
        with patch('analytics311.service.subprocess.Popen'):
            job = service.export_csv(result['result_id'], 'records', 'all_matching')
            self.assert_error('budget_exceeded', service.export_csv, result['result_id'], 'records', 'all_matching')
        recovery = recover_exports(service.runs)
        self.assertEqual(recovery['recovered_count'], 1)
        recovered = service.get_result(job['job_id'])
        self.assertEqual(recovered['error']['code'], 'worker_interrupted')
        self.config['export_inline'] = True
        service = self.reload()
        complete = service.export_csv(result['result_id'], 'records', 'all_matching')
        self.assertEqual(complete['status'], 'complete')
        self.assertEqual(list(service.runs.glob('*.export')), [])

    def test_stale_dataset_export_failure_remains_readable(self):
        self.config['export_inline'] = False
        service = self.reload()
        result = service.run_analysis(self.example('brooklyn-noise'))
        with patch('analytics311.service.subprocess.Popen'):
            job = service.export_csv(result['result_id'], 'records', 'all_matching')
        source = self.directory/'requests.jsonl'
        source.write_text(source.read_text()+'\n', encoding='utf-8')
        failed = service.run_export_job(job['job_id'])
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['error']['code'], 'result_expired')
        self.assertEqual(service.get_result(job['job_id'])['status'], 'failed')
        self.assertEqual(list(service.runs.glob('*.export')), [])

    def test_csv_formula_text_escaped_without_changing_numeric_values(self):
        path = self.directory / "requests.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]["descriptor"] = '  =HYPERLINK("http://example.invalid")'
        rows[0]["closure_hours"] = -2  # Numeric output remains numeric, not an Excel formula.
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        result = self.service.run_analysis(self.spec(filters={"field": "unique_key", "op": "eq", "value": "FIX-001"}))
        exported = self.csv_rows(self.service.export_csv(result["result_id"], "records", "all_matching", columns=["descriptor", "closure_hours"]))
        self.assertEqual(exported, [{"descriptor": "'  =HYPERLINK(\"http://example.invalid\")", "closure_hours": "-2"}])

    def test_comparison_counts_exposure_and_null_neighborhoods(self):
        result = self.service.run_analysis(self.example("rodent-trends"))
        self.assertEqual(result["total"]["value"], 17)
        self.assertEqual(sum(row["baseline_count"] for row in result["rows"]), 8)
        self.assertEqual(sum(row["current_count"] for row in result["rows"]), 9)
        groups = {row["group"]["nta2020"]: row for row in result["rows"]}
        self.assertEqual((groups[None]["baseline_count"], groups[None]["current_count"]), (1, 1))
        row = groups["FIXTURE-BK-B"]
        self.assertEqual((row["baseline_count"], row["current_count"], row["absolute_change"], row["relative_change"]), (1, 2, 1, 1))
        self.assertEqual((row["baseline_days"], row["current_days"]), (30, 31))
        self.assertAlmostEqual(row["baseline_daily_rate"], 1 / 30)
        self.assertAlmostEqual(row["current_daily_rate"], 2 / 31)

    def test_zero_baseline_is_nullable_relative_change(self):
        spec = self.example("rodent-trends")
        spec["periods"]["baseline"]["lt"] = "2025-11-03T00:00:00-05:00"
        rows = self.service.run_analysis(spec)["rows"]
        groups = {row["group"]["nta2020"]: row for row in rows}
        row = groups["FIXTURE-QN-A"]
        self.assertEqual((row["baseline_count"], row["current_count"]), (0, 2))
        self.assertIsNone(row["relative_change"])
        self.assertEqual(row["baseline_daily_rate"], 0)

    def test_uncovered_comparisons_fail_and_records_disclose_coverage(self):
        spec = self.example("rodent-trends")
        spec["periods"]["baseline"]["gte"] = "2025-10-01T00:00:00-04:00"
        self.assert_error("coverage_gap", self.service.validate_analysis, spec)
        self.assert_error("coverage_gap", self.service.run_analysis, spec)
        record_spec = self.spec()
        record_spec["time"]["gte"] = "2025-10-01T00:00:00-04:00"
        result = self.service.run_analysis(record_spec)
        self.assertFalse(result["coverage_complete"])
        self.assertTrue(result["warnings"])
        manifest_path = self.directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["coverage"]["complete"] = False
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        service = self.reload()
        self.assert_error("coverage_gap", service.run_analysis, self.example("rodent-trends"))

    def test_calendar_histograms_reject_unobserved_coverage(self):
        for field in ("created_date", "closed_date"):
            with self.subTest(field=field):
                spec = self.spec(operation="aggregate", group_by=[{"field": field, "interval": "day"}])
                spec["time"]["field"] = field
                if field == "created_date":
                    spec["time"]["gte"] = "2025-10-01T00:00:00-04:00"
                self.assert_error("coverage_gap", self.service.run_analysis, spec)

    def test_csv_export_exceeds_search_preview_and_ten_thousand_rows(self):
        path = self.directory / "requests.jsonl"
        template = json.loads(path.read_text().splitlines()[0])
        with path.open("w", encoding="utf-8") as stream:
            for index in range(10_001):
                stream.write(json.dumps({**template, "unique_key": f"GENERATED-{index:05}"}) + "\n")
        manifest_path = self.directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest.update(kind="generated_test_fixture", row_count=10_001)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        service = self.reload()
        result = service.run_analysis(self.spec(preview_limit=2))
        self.assertEqual(result["total"]["value"], 10_001)
        self.assertEqual(len(result["rows"]), 2)
        job = service.export_csv(result["result_id"], "records", "all_matching", columns=["unique_key"])
        rows = self.csv_rows(job)
        self.assertEqual(job["rows_written"], 10_001)
        self.assertEqual(len(rows), 10_001)
        self.assertEqual(len({row["unique_key"] for row in rows}), 10_001)
        self.assertEqual(rows[-1]["unique_key"], "GENERATED-10000")

    def test_expired_execution_budget_publishes_no_result(self):
        self.config["budgets"]["deadline_seconds"] = 1
        service = self.reload()
        # Advance the clock deterministically; scheduler timing is not evidence.
        with patch("analytics311.service.time.monotonic", side_effect=[0] + [2] * 1000):
            self.assert_error("budget_exceeded", service.run_analysis, self.spec())
        self.assertEqual(list((self.directory / "runs").glob("*.json")), [])

    def test_selected_nested_group_exports_only_matching_source_rows(self):
        spec = self.spec(operation="aggregate", group_by=[{"field": "borough"}, {"field": "complaint_type"}], top_n=1)
        result = self.service.run_analysis(spec)
        all_groups = self.service.get_result(result["result_id"], page_size=100)["rows"]
        selected = next(row for row in all_groups if row["group"] == {"borough": "BROOKLYN", "complaint_type": "Rodent"})
        job = self.service.export_csv(result["result_id"], "records", "selected_groups", group_ids=[selected["group_id"]])
        self.assertEqual({row["unique_key"] for row in self.csv_rows(job)}, {"FIX-001", "FIX-002", "FIX-013", "FIX-017", "FIX-018", "FIX-019", "FIX-020"})
        self.assertEqual(job["cohort_scope"], "selected_groups")
        full_table = self.csv_rows(self.service.export_csv(result["result_id"], "aggregates", "all_matching"))
        self.assertEqual(len(full_table), result["group_count"])
        self.assertGreater(len(full_table), len(result["rows"]))

    def test_comparison_export_preserves_union_and_null_group(self):
        spec = self.example("rodent-trends")
        spec["periods"]["baseline"]["lt"] = "2025-11-03T00:00:00-05:00"
        result = self.service.run_analysis(spec)
        job = self.service.export_csv(result["result_id"], "records", "all_matching")
        expected = {f"FIX-{i:03}" for i in [1, 16, 17, 18, 19, 20, 24, 26, 27, 29, 31]}
        self.assertEqual({row["unique_key"] for row in self.csv_rows(job)}, expected)
        null = next(row for row in result["rows"] if row["group"]["nta2020"] is None)
        selected = self.service.export_csv(result["result_id"], "records", "selected_groups", group_ids=[null["group_id"]])
        self.assertEqual({row["unique_key"] for row in self.csv_rows(selected)}, {"FIX-031"})

    def test_weekly_by_borough_zero_fill_observed_domain(self):
        result = self.service.run_analysis(self.example("weekly-noise"))
        rows = result["rows"]
        self.assertEqual(result["group_count"], 10)  # Five Mondays x Brooklyn/Manhattan.
        self.assertEqual(sum(row["count"] for row in rows), 5)
        lookup = {(row["group"]["created_date"], row["group"]["borough"]): row for row in rows}
        self.assertEqual(lookup[("2025-12-15T00:00:00-05:00", "MANHATTAN")]["count"], 0)
        self.assertEqual(lookup[("2025-12-29T00:00:00-05:00", "BROOKLYN")]["count"], 1)
        self.assertTrue(any("observed" in warning for warning in result["warnings"]))

    def test_selected_week_export_uses_local_dst_calendar_end(self):
        path = self.directory / "requests.jsonl"
        source = json.loads(path.read_text().splitlines()[0])
        source.update(unique_key="DST-END", created_date="2025-11-02T23:30:00-05:00")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(source) + "\n")
        spec = self.spec(operation="aggregate", group_by=[{"field": "created_date", "interval": "week"}])
        result = self.service.run_analysis(spec)
        selected = next(row for row in result["rows"] if row["group"]["created_date"] == "2025-10-27T00:00:00-04:00")
        job = self.service.export_csv(result["result_id"], "records", "selected_groups", group_ids=[selected["group_id"]])
        self.assertEqual({row["unique_key"] for row in self.csv_rows(job)}, {"FIX-001", "FIX-015", "FIX-016", "DST-END"})

    def test_id_and_selection_validation(self):
        self.assert_error("invalid_spec", self.service.get_result, "../manifest")
        self.assert_error("result_expired", self.service.get_result, "0" * 32)
        result = self.service.run_analysis(self.spec(operation="aggregate", group_by=[{"field": "borough"}]))
        self.assert_error("invalid_spec", self.service.export_csv, result["result_id"], "records", "selected_groups", group_ids=["missing"])
        self.assert_error("invalid_spec", self.service.export_csv, result["result_id"], "records", "implicit")
        self.assert_error("invalid_spec", self.service.export_csv, result["result_id"], "records", "all_matching", columns=["private_field"])
        self.assert_error("invalid_spec", self.service.get_result, result["result_id"], cursor=123)
        self.assert_error("invalid_spec", self.service.get_result, result["result_id"], page_size=0)

    def test_saved_result_invalidated_after_fixture_mutation(self):
        result = self.service.run_analysis(self.spec())
        with (self.directory / "requests.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("\n")
        self.assert_error("result_expired", self.service.get_result, result["result_id"])
        self.assert_error("result_expired", self.service.export_csv, result["result_id"], "records", "all_matching")

    def test_export_budget_does_not_publish_partial_artifact(self):
        self.config["budgets"]["max_export_rows"] = 2
        service = self.reload()
        result = service.run_analysis(self.example("brooklyn-noise"))
        before = set(service.runs.iterdir())
        with patch.object(service, "_start_export") as start:
            self.assert_error("budget_exceeded", service.export_csv, result["result_id"], "records", "all_matching")
        start.assert_not_called()
        self.assertEqual(set(service.runs.iterdir()), before)
        self.assertEqual(list((self.directory / "runs").glob("*.csv*")), [])

    def test_queued_cancel_removes_partial_output(self):
        self.config["export_inline"] = False
        service = self.reload()
        result = service.run_analysis(self.spec())
        with patch("analytics311.service.subprocess.Popen"):
            job = service.export_csv(result["result_id"], "records", "all_matching")
        self.assertEqual(job["status"], "queued")
        self.assertEqual(service.cancel_export(job["job_id"])["status"], "cancellation_requested")
        cancelled = service.run_export_job(job["job_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertFalse(cancelled["complete"])
        self.assertEqual(list((self.directory / "runs").glob("*.csv*")), [])


if __name__ == "__main__":
    unittest.main()
