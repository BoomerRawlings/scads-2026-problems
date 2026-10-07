"""Export status snapshots and cleanup failures through the public job interface."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analytics311.errors import AnalyticsError
from analytics311.resources import asset_path
from analytics311.service import AnalyticsService, atomic_json


class RowsWithBadClose:
    def __init__(self, rows, error=None):
        self.rows = iter(rows)
        self.error = error
        self.close_calls = 0

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self.rows)
        except StopIteration:
            if self.error:
                raise self.error
            raise

    def close(self):
        self.close_calls += 1
        raise RuntimeError("Private backend diagnostic must not appear in job metadata")


class ExportProgressTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.config = root / "config.json"
        self.config.write_text(json.dumps({
            "backend": "fixture", "fixture_path": str(asset_path("fixtures/requests.jsonl")),
            "manifest_path": str(asset_path("fixtures/manifest.json")),
            "catalog_path": str(asset_path("config/catalog.json")), "runs_dir": str(root / "runs"),
            "budgets": {"export_deadline_seconds": 10},
        }), encoding="utf-8")
        self.service = AnalyticsService(self.config)
        self.result = self.service.run_analysis({"dataset_version": "fixture-v1", "operation": "records"})

    def queue(self):
        with patch("analytics311.service.subprocess.Popen"):
            job = self.service.export_csv(self.result["result_id"], "records", "all_matching")
        self.assertEqual("queued", job["status"])
        self.assertEqual("queued", job["stage"])
        self.assertEqual(job["queued_at"], job["last_progress_at"])
        self.assertEqual(0, job["bytes_written"])
        return job["job_id"]

    def assert_clean_failure(self, job, code):
        self.assertFalse(job["complete"])
        self.assertEqual(code, job["error"]["code"])
        self.assertEqual(job["status"], job["stage"])
        self.assertIn("finished_at", job)
        self.assertNotIn("file", job)
        self.assertFalse(list(self.service.runs.glob("*.csv*")))
        self.assertFalse(list(self.service.runs.glob("*.export")))
        self.assertFalse(list(self.service.runs.glob("*.cancel")))
        self.assertNotIn("Private backend", json.dumps(job))

    def test_current_stage_and_throttled_counters_are_readable_during_work(self):
        job_id = self.queue()
        clock, observed, stages = [0.0], [], []
        original_load = self.service._load

        def load(result_id, check_identity=True):
            if result_id == job_id and check_identity:
                active = original_load(job_id, check_identity=False)
                self.assertEqual("running", active["status"])
                self.assertEqual("validating", active["stage"])
                self.assertIn("deadline_at", active)
            return original_load(result_id, check_identity)

        def source(*args, **kwargs):
            self.assertEqual("streaming", self.service.get_result(job_id)["stage"])
            for number, instant in enumerate((.1, .5, 1.1, 1.2, 2.2), start=1):
                clock[0] = instant
                yield {"unique_key": str(number)}
                current = self.service.get_result(job_id)
                observed.append(current["rows_written"])
                self.assertNotIn("request", current)
                self.assertNotIn("dataset_identity", current)

        def persist(path, job):
            stages.append(job["stage"])
            return atomic_json(path, job)

        with patch("analytics311.service.time.monotonic", side_effect=lambda: clock[0]), \
             patch.object(self.service, "_load", side_effect=load), \
             patch.object(self.service.backend, "iter_records", side_effect=source), \
             patch("analytics311.service.atomic_json", side_effect=persist):
            job = self.service.run_export_job(job_id)
        self.assertEqual([0, 0, 3, 3, 5], observed)
        self.assertEqual(["validating", "streaming", "streaming", "streaming", "closing_source", "verifying", "publishing", "complete"], stages)
        self.assertEqual("complete", job["status"])
        self.assertEqual(5, job["rows_written"])
        self.assertEqual(2.2, job["elapsed_seconds"])
        self.assertEqual(Path(job["file"]).stat().st_size, job["bytes_written"])
        self.assertFalse(list(self.service.runs.glob("*.export")))

    def test_close_failure_prevents_artifact_and_releases_capacity(self):
        job_id = self.queue()
        source = RowsWithBadClose([{"unique_key": "one"}])
        with patch.object(self.service.backend, "iter_records", return_value=source):
            job = self.service.run_export_job(job_id)
        self.assert_clean_failure(job, "export_cleanup_failed")
        self.assertEqual("closing_source", job["stopped_stage"])
        self.assertEqual(1, source.close_calls)

    def test_row_budget_error_survives_close_failure(self):
        job_id = self.queue()
        self.service.budgets["max_export_rows"] = 1
        source = RowsWithBadClose([{"unique_key": "one"}, {"unique_key": "two"}])
        with patch.object(self.service.backend, "iter_records", return_value=source):
            job = self.service.run_export_job(job_id)
        self.assert_clean_failure(job, "budget_exceeded")
        self.assertEqual("streaming", job["stopped_stage"])
        self.assertEqual("export_cleanup_failed", job["cleanup_error"]["code"])
        self.assertEqual(1, job["rows_written"])
        self.assertEqual(1, source.close_calls)

    def test_backend_error_survives_close_failure(self):
        job_id = self.queue()
        source = RowsWithBadClose([], AnalyticsError("partial_execution", "Source scan failed"))
        with patch.object(self.service.backend, "iter_records", return_value=source):
            job = self.service.run_export_job(job_id)
        self.assert_clean_failure(job, "partial_execution")
        self.assertEqual("streaming", job["stopped_stage"])
        self.assertEqual("export_cleanup_failed", job["cleanup_error"]["code"])
        self.assertEqual(1, source.close_calls)

    def test_cancellation_survives_close_failure(self):
        job_id = self.queue()
        service = self.service

        class CancelledRows(RowsWithBadClose):
            def __next__(self):
                service.cancel_export(job_id)
                return super().__next__()

        source = CancelledRows([{"unique_key": "one"}])
        with patch.object(service.backend, "iter_records", return_value=source):
            job = service.run_export_job(job_id)
        self.assert_clean_failure(job, "cancelled")
        self.assertEqual("cancelled", job["status"])
        self.assertEqual("streaming", job["stopped_stage"])
        self.assertEqual("export_cleanup_failed", job["cleanup_error"]["code"])
        self.assertEqual(1, source.close_calls)

    def test_identity_change_is_reported_at_verification(self):
        job_id = self.queue()
        original = self.service._identity

        def identity():
            if self.service.get_result(job_id)["stage"] == "verifying":
                return "changed"
            return original()

        with patch.object(self.service, "_identity", side_effect=identity):
            job = self.service.run_export_job(job_id)
        self.assert_clean_failure(job, "partial_execution")
        self.assertEqual("verifying", job["stopped_stage"])

    def test_cancel_or_deadline_during_publication_checkpoint_prevents_csv(self):
        for cancellation in (False, True):
            with self.subTest(cancellation=cancellation):
                job_id, clock = self.queue(), [0.0]

                def persist(path, job):
                    atomic_json(path, job)
                    if job["stage"] == "publishing":
                        if cancellation:
                            self.service.cancel_export(job_id)
                        else:
                            clock[0] = 11

                with patch("analytics311.service.atomic_json", side_effect=persist), \
                     patch("analytics311.service.time.monotonic", side_effect=lambda: clock[0]):
                    job = self.service.run_export_job(job_id)
                self.assert_clean_failure(job, "cancelled" if cancellation else "budget_exceeded")
                self.assertEqual("publishing", job["stopped_stage"])

    def test_launch_failure_has_terminal_metadata_and_no_reservation(self):
        with patch("analytics311.service.subprocess.Popen", side_effect=OSError("Private launch diagnostic")), \
             self.assertRaises(AnalyticsError) as caught:
            self.service.export_csv(self.result["result_id"], "records", "all_matching")
        self.assertEqual("backend_unavailable", caught.exception.code)
        jobs = [json.loads(path.read_text(encoding="utf-8")) for path in self.service.runs.glob("*.json")]
        job = next(job for job in jobs if job["kind"] == "export")
        self.assert_clean_failure(job, "backend_unavailable")
        self.assertEqual("queued", job["stopped_stage"])
        self.assertNotIn("Private launch", json.dumps(job))


if __name__ == "__main__":
    unittest.main()
