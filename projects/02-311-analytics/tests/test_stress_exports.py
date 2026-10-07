import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("stress_exports", ROOT / "tools/stress_exports.py")
stress = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stress)


class ExportStressTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.runs = Path(self.temporary.name)
        self.job_id = "b" * 32

    def export(self, identifiers=None):
        path = self.runs / f"{self.job_id}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["unique_key"])
            writer.writeheader()
            for identifier in identifiers or sorted(stress.EXPECTED_IDS):
                writer.writerow({"unique_key": identifier})
        return {"job_id": self.job_id, "status": "complete", "complete": True,
                "rows_written": 4, "bytes_written": path.stat().st_size, "file": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def failure(self, code, operation):
        with self.assertRaises(stress.TrialFailure) as raised:
            operation()
        self.assertEqual(code, raised.exception.code)
        return raised.exception

    def test_same_count_wrong_cohort_cannot_pass_valid_hash(self):
        job = self.export(["FIX-021", "FIX-022", "FIX-023", "FIX-021"])
        self.failure("csv_cohort_mismatch", lambda: stress.verify_export(job, self.runs))

    def test_modified_csv_or_unreleased_partial_cannot_pass(self):
        job = self.export()
        self.assertTrue(stress.verify_export(job, self.runs)["exact_ids"])
        Path(job["file"]).write_bytes(Path(job["file"]).read_bytes() + b"\r\n")
        self.failure("csv_integrity_mismatch", lambda: stress.verify_export(job, self.runs))
        job = self.export()
        (self.runs / f"{self.job_id}.csv.part").touch()
        self.failure("export_residue", lambda: stress.verify_export(job, self.runs))

    def test_wait_timeout_retains_sanitized_latest_progress(self):
        job = {"job_id": self.job_id, "status": "running", "stage": "writing", "rows_written": 3,
               "bytes_written": 98, "file": "C:/secret/data.csv", "error": {"message": "C:/secret/error"}}
        service = Mock()
        service.get_result.return_value = job
        workers = Mock()
        process = Mock()
        process.poll.return_value = None
        workers.processes = {self.job_id: process}
        with patch.object(stress.time, "monotonic", return_value=10):
            failure = self.failure("harness_timeout", lambda: stress.wait_batch(service, [job], workers, 9))
        self.assertEqual({"status": "running", "stage": "writing", "rows_written": 3, "bytes_written": 98}, failure.details["jobs"][0])
        self.assertNotIn("secret", json.dumps(failure.details))

    def test_complete_worker_observed_after_deadline_cannot_pass(self):
        job = {"job_id": self.job_id, "status": "complete", "complete": True}
        service = Mock()
        service.get_result.return_value = job
        process = Mock()
        process.poll.return_value = 0
        workers = Mock(processes={self.job_id: process})
        with patch.object(stress.time, "monotonic", return_value=10):
            self.failure("harness_timeout", lambda: stress.wait_batch(service, [job], workers, 9))

    def test_cleanup_errors_preserve_primary_failure_receipt(self):
        temporary = Mock(name=str(self.runs))
        temporary.name = str(self.runs)
        temporary.cleanup.side_effect = OSError("C:/private/path")
        with patch.object(stress.tempfile, "TemporaryDirectory", return_value=temporary), \
                patch.object(stress, "AnalyticsService", side_effect=stress.TrialFailure("setup_failed")), \
                patch.object(stress.OwnedWorkers, "stop", side_effect=OSError("C:/private/path")):
            report = stress.run_trial(batches=1)
        self.assertFalse(report["passed"])
        self.assertEqual("setup_failed", report["failure"]["code"])
        self.assertEqual(["worker_cleanup_failed", "temporary_cleanup_failed"], [item["code"] for item in report["cleanup_failures"]])
        self.assertNotIn("private", json.dumps(report))

    def test_recovery_rejects_false_success_and_partial_residue(self):
        service = Mock(runs=self.runs)
        service.get_result.return_value = {"status": "complete", "complete": True}
        report = {"recovered_count": 1, "active_count": 0, "invalid_count": 0,
                  "recovered": [{"job_id": self.job_id, "removed_partial": True}], "released_reservations": [self.job_id]}
        self.failure("recovery_failed", lambda: stress.verify_recovery(service, self.job_id, report))
        service.get_result.return_value = {"status": "failed", "complete": False, "error": {"code": "worker_interrupted"}}
        (self.runs / f"{self.job_id}.export").touch()
        self.failure("recovery_residue", lambda: stress.verify_recovery(service, self.job_id, report))

    def test_bounded_actual_background_workers_and_crash_recovery_outside_checkout(self):
        receipt = self.runs / "receipt.json"
        result = subprocess.run([sys.executable, str(ROOT / "tools/stress_exports.py"), "--batches", "1",
                                 "--concurrency", "2", "--output", str(receipt), "--total-seconds", "40"],
                                cwd=self.runs, capture_output=True, text=True, timeout=50)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr + (receipt.read_text() if receipt.exists() else ""))
        report = json.loads(receipt.read_text())
        self.assertTrue(report["passed"])
        self.assertEqual(7, report["owned_processes_started"])
        self.assertLessEqual(report["peak_owned_processes_alive"], 2)
        self.assertTrue(report["recovery"]["active_worker_preserved"])
        self.assertTrue(report["recovery"]["partial_removed"])
        self.assertTrue(report["recovery"]["worker_abrupt_exit"])
        self.assertEqual(86, report["recovery"]["worker_exit_code"])
        self.assertEqual(3, len(report["batches"]))
        self.assertEqual({"explicit_1", "bundled_default_cwd_change", "after_recovery"}, {b["profile"] for b in report["batches"]})
        self.assertTrue(all(item["exact_ids"] and item["rows"] == 4 for batch in report["batches"] for item in batch["exports"]))
        for batch in report["batches"]:
            for item in batch["exports"]:
                self.assertEqual("complete", item["terminal"]["stage"])
                self.assertIn("last_progress_at", item["terminal"])
                self.assertIn("complete", item["observed_stages"])
        self.assertNotIn(str(self.runs), receipt.read_text())
        self.assertNotIn(str(ROOT), receipt.read_text())


if __name__ == "__main__":
    unittest.main()
