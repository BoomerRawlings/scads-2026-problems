import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from analytics311.errors import AnalyticsError
from tools.live_acceptance import run_acceptance


class LiveHarnessTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.config = self.directory / "config.json"
        self.spec = self.directory / "spec.json"
        self.output = self.directory / "evidence.json"
        self.csv_path = self.directory / "result.csv"
        self.config.write_text(json.dumps({"backend": "elastic", "elastic_url": "https://not-contacted.invalid"}), encoding="utf-8")
        self.spec.write_text(json.dumps({"dataset_version": "test-v1", "operation": "records"}), encoding="utf-8")
        with self.csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(["unique_key", "complaint_type"])
            writer.writerow(["1", "Noise\nmultiline field"])
            writer.writerow(["2", "Rodent"])
        self.service = Mock()
        self.service.manifest = {"kind": "public_sample", "dataset_version": "test-v1", "index": "test-v1",
                                 "row_count": 2, "coverage": {"complete": False},
                                 "source": str(self.directory / "private-local-name.jsonl")}
        self.service.backend.client.request.return_value = {"name": "private-node-name", "cluster_name": "private-cluster",
                                                             "version": {"number": "9.0.0", "lucene_version": "10.1.0"}}
        self.service.validate_analysis.return_value = {"normalized_spec": {"operation": "records", "dataset_version": "test-v1"}, "coverage_complete": False}
        self.service.run_analysis.return_value = {"result_id": "a" * 32, "execution_complete": True,
            "total": {"value": 2, "relation": "eq"}, "evidence_level": "elastic_execution", "approximate": False}
        self.completed = {"job_id": "b" * 32, "status": "complete", "complete": True, "cohort_scope": "all_matching",
                          "file": str(self.csv_path), "columns": ["unique_key", "complaint_type"], "rows_written": 2,
                          "sha256": hashlib.sha256(self.csv_path.read_bytes()).hexdigest()}
        self.service.export_csv.return_value = self.completed
        self.mock_constructor = patch("tools.live_acceptance.AnalyticsService", return_value=self.service)
        self.constructor = self.mock_constructor.start()
        self.addCleanup(self.mock_constructor.stop)

    def run_harness(self, **kwargs):
        return run_acceptance(self.config, self.spec, self.output, **kwargs)

    def test_success_counts_csv_records_not_newlines_and_saves_scope(self):
        evidence = self.run_harness()
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["csv"]["row_count"], 2)
        self.assertTrue(evidence["checks"]["csv_sha256_matches_job"])
        self.assertFalse(evidence["overall_release_verified"])
        self.assertFalse(evidence["visual_parity_verified"])
        self.service.backend.client.request.assert_called_once_with("GET", "/")
        self.service.export_csv.assert_called_once_with("a" * 32, "records", "all_matching")
        saved = self.output.read_text(encoding="utf-8")
        for private in (str(self.directory), "not-contacted.invalid", "private-node-name", "private-cluster"):
            self.assertNotIn(private, saved)

    def test_refuses_fixture_without_instantiating_service(self):
        self.config.write_text('{"backend":"fixture"}', encoding="utf-8")
        with self.assertRaises(AnalyticsError) as caught:
            self.run_harness()
        self.assertEqual(caught.exception.code, "unsupported_operation")
        self.constructor.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_count_or_checksum_mismatch_fails_evidence(self):
        self.completed["sha256"] = "0" * 64
        evidence = self.run_harness()
        self.assertFalse(evidence["passed"])
        self.assertFalse(evidence["checks"]["csv_sha256_matches_job"])
        self.assertEqual(evidence["error"]["stage"], "csv_verification")

    def test_source_cohort_mismatch_fails_even_when_job_matches_csv(self):
        self.service.run_analysis.return_value["total"]["value"] = 3
        evidence = self.run_harness()
        self.assertFalse(evidence["passed"])
        self.assertFalse(evidence["checks"]["csv_count_matches_source_cohort"])

    def test_waits_for_job_completion(self):
        self.service.export_csv.return_value = {"job_id": "b" * 32, "status": "queued", "complete": False}
        self.service.get_result.side_effect = [{"job_id": "b" * 32, "status": "running"}, self.completed]
        with patch("tools.live_acceptance.time.sleep"):
            evidence = self.run_harness()
        self.assertTrue(evidence["passed"])
        self.assertEqual(self.service.get_result.call_count, 2)

    def test_timeout_requests_cancellation_and_does_not_claim_complete(self):
        self.service.export_csv.return_value = {"job_id": "b" * 32, "status": "running", "complete": False}
        with patch("tools.live_acceptance.time.monotonic", side_effect=[0, 0, 121, 121]):
            evidence = self.run_harness()
        self.assertFalse(evidence["passed"])
        self.assertEqual(evidence["error"]["code"], "acceptance_timeout")
        self.service.cancel_export.assert_called_once_with("b" * 32)
        self.assertTrue(evidence["export_cancellation_requested"])

    def test_optional_map_never_upgrades_visual_parity_claim(self):
        self.service.create_map_link.return_value = {"url": "https://kibana.example/goto/abc", "parity_verified": True,
                                                    "source_count": 2, "mapped_count": 1, "missing_location_count": 1}
        evidence = self.run_harness(map_mode="requests")
        self.assertTrue(evidence["passed"])
        self.assertFalse(evidence["map"]["visual_parity_verified"])
        self.assertTrue(evidence["checks"]["map_link_created"])
        self.service.create_map_link.assert_called_once_with("a" * 32, "requests", "all_matching")

    def test_partial_analysis_never_starts_export(self):
        self.service.run_analysis.return_value["execution_complete"] = False
        evidence = self.run_harness()
        self.assertFalse(evidence["passed"])
        self.service.export_csv.assert_not_called()

    def test_api_failure_reports_code_without_sensitive_message(self):
        self.service.backend.client.request.side_effect = AnalyticsError("backend_unavailable", "secret credential at C:/private/place")
        evidence = self.run_harness()
        self.assertEqual(evidence["error"], {"stage": "server_version", "code": "backend_unavailable"})
        self.assertNotIn("secret", self.output.read_text())

    def test_comparison_exports_union_source_count(self):
        self.service.validate_analysis.return_value["normalized_spec"]["operation"] = "compare_periods"
        self.service.run_analysis.return_value["group_count"] = 1
        evidence = self.run_harness()
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["csv"]["row_count"], evidence["analysis"]["total"]["value"])

    def test_evidence_file_is_not_overwritten(self):
        self.output.write_text("existing evidence", encoding="utf-8")
        with self.assertRaises(AnalyticsError):
            self.run_harness()
        self.assertEqual(self.output.read_text(), "existing evidence")
        self.constructor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
