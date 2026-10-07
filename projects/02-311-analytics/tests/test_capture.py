import copy
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from analytics311.capture import FIELD_TYPES, SocrataClient, capture_status, capture_window
from analytics311 import capture as capture_module
from analytics311.errors import AnalyticsError


REVISION = "Tue, 06 Oct 2026 02:00:00 GMT"
HEADERS = {"x-soda2-truth-last-modified": REVISION, "x-soda2-secondary-last-modified": REVISION}
UPDATED = "2026-10-05T01:00:00Z"


def record(number):
    return {"unique_key": f"{number:08}", "created_date": "2025-01-01T12:00:00.000",
            "complaint_type": "Rodent", "source_row_id": f"row-{number}", "source_updated_at": UPDATED}


class Source:
    def __init__(self, rows=None):
        self.rows = [record(i) for i in range(1, 6)] if rows is None else rows
        self.calls = []
        self.page_calls = 0
        self.count_calls = 0
        self.metadata_calls = 0
        self.fail_page = None
        self.failure = KeyboardInterrupt()
        self.count_adjustment = 0
        self.final_count_adjustment = 0
        self.stale = False
        self.drift_page = None
        self.metadata_drift = False
        self.duplicate_page = False
        self.omit_last = False

    def get_json(self, path, params=None, **kwargs):
        self.calls.append((path, copy.deepcopy(params)))
        if path.startswith("/api/views"):
            self.metadata_calls += 1
            return {"id": "erm2-nwe9", "rowsUpdatedAt": 123 + (self.metadata_drift and self.metadata_calls > 1),
                    "viewLastModified": 456, "columns": [{"fieldName": k, "dataTypeName": v} for k, v in FIELD_TYPES.items()]}, {}
        headers = dict(HEADERS)
        if self.stale:
            headers["x-soda2-data-out-of-date"] = "true"
        if params["$select"].startswith("count("):
            self.count_calls += 1
            count = len(self.rows) + self.count_adjustment + (self.final_count_adjustment if self.count_calls > 1 else 0)
            result = {"row_count": str(count), "unique_count": str(count)}
            if count:
                result["max_updated_at"] = UPDATED
            return [result], headers
        self.page_calls += 1
        if self.page_calls == self.fail_page:
            raise self.failure
        if self.page_calls == self.drift_page:
            headers = {key: "Wed, 07 Oct 2026 02:00:00 GMT" for key in HEADERS}
        cursor = re.search(r"unique_key > '([^']+)'", params["$where"])
        value = cursor.group(1) if cursor else ""
        available = self.rows[:-1] if self.omit_last else self.rows
        rows = [row for row in available if row["unique_key"] > value][:params["$limit"]]
        if self.duplicate_page and rows:
            rows = [rows[0], rows[0]]
        return copy.deepcopy(rows), headers


class CaptureTests(unittest.TestCase):
    def test_large_resume_reconciliation_obeys_deadline_and_keeps_database_usable(self):
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE TABLE records(unique_key TEXT,json_bytes INTEGER,updated_at TEXT)")
            db.executemany("INSERT INTO records VALUES (?,100,?)", ((str(i), UPDATED) for i in range(1000)))
            requests = capture_module._Requests(None, deadline=1, retries=0)
            # The initial check fits; the SQLite VM crosses the deadline.
            with patch("analytics311.capture.time.monotonic", side_effect=[0, 2]):
                with self.assertRaises(AnalyticsError) as error:
                    capture_module._staged_totals(db, requests)
            self.assertEqual("budget_exceeded", error.exception.code)
            # The temporary interrupt handler must not poison recovery writes.
            db.execute("INSERT INTO records VALUES ('last',100,?)", (UPDATED,))
            self.assertEqual(1001, db.execute("SELECT count(*) FROM records").fetchone()[0])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.output = self.directory / "capture.jsonl"
        self.source = Source()

    def capture(self, **kwargs):
        args = {"page_size": 2, "max_rows": 1000, "max_bytes": 5_000_000, "max_storage_bytes": 20_000_000,
                "max_pages": 100, "max_seconds": 30, "min_free_bytes": 0, "retries": 0, "client": self.source}
        args.update(kwargs)
        return capture_window("2025-01-01", "2025-01-02", self.output, **args)

    def test_complete_capture_hash_count_and_conservative_coverage(self):
        result = self.capture()
        data = [json.loads(line) for line in self.output.read_text(encoding="utf-8").splitlines()]
        manifest = json.loads(self.output.with_suffix(".manifest.json").read_text())
        self.assertEqual(len(data), 5)
        self.assertEqual(len({row["unique_key"] for row in data}), 5)
        self.assertEqual(result["sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertEqual(manifest["bytes"], self.output.stat().st_size)
        self.assertTrue(manifest["observed_complete"])
        self.assertFalse(manifest["coverage"]["complete"])
        self.assertFalse(manifest["transactional_source_snapshot"])
        self.assertEqual(manifest["kind"], "reconciled_public_capture")
        self.assertEqual(manifest["coverage"]["gte"], "2025-01-01T00:00:00-05:00")
        self.assertEqual(capture_status(self.output)["status"], "complete")

    def test_interruption_resumes_committed_cursor_without_duplicates(self):
        self.source.fail_page = 2
        with self.assertRaises(KeyboardInterrupt):
            self.capture()
        progress = capture_status(self.output)
        self.assertEqual((progress["status"], progress["rows"]), ("paused", 2))
        self.assertFalse(self.output.exists())
        self.source.fail_page = None
        self.capture()
        rows = [json.loads(line) for line in self.output.read_text().splitlines()]
        self.assertEqual([row["unique_key"] for row in rows], [f"{n:08}" for n in range(1, 6)])
        pages = [params for _, params in self.source.calls if params and "$order" in params]
        self.assertIn("unique_key > '00000002'", pages[2]["$where"])

    def test_drift_quarantines_and_cannot_resume_into_changed_source(self):
        self.source.drift_page = 2
        with self.assertRaises(AnalyticsError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, "source_changed")
        self.assertEqual(capture_status(self.output)["status"], "quarantined")
        self.assertFalse(self.output.exists())
        calls = len(self.source.calls)
        self.source.drift_page = None
        with self.assertRaises(AnalyticsError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, "capture_quarantined")
        self.assertEqual(len(self.source.calls), calls)

    def test_final_count_change_never_publishes_jsonl(self):
        self.source.final_count_adjustment = 1
        with self.assertRaises(AnalyticsError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, "source_changed")
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.with_suffix(".manifest.json").exists())

    def test_omitted_record_detected_by_independent_source_count(self):
        self.source.omit_last = True
        with self.assertRaises(AnalyticsError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, "source_count_mismatch")
        self.assertEqual(capture_status(self.output)["status"], "quarantined")

    def test_duplicate_page_fails_before_commit(self):
        self.source.duplicate_page = True
        with self.assertRaises(AnalyticsError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, "duplicate_source_record")
        self.assertEqual(capture_status(self.output)["rows"], 0)

    def test_changed_metadata_rejects_finalization(self):
        self.source.metadata_drift = True
        with self.assertRaises(AnalyticsError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, "source_changed")
        self.assertFalse(self.output.exists())

    def test_stale_replica_pauses_before_any_records_and_can_retry(self):
        self.source.stale = True
        with self.assertRaises(AnalyticsError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, "source_stale")
        self.assertEqual(self.source.page_calls, 0)
        self.assertEqual(capture_status(self.output)["status"], "paused")
        self.source.stale = False
        self.assertEqual(self.capture()["rows"], 5)

    def test_row_budget_does_not_turn_capture_into_published_sample(self):
        with self.assertRaises(AnalyticsError) as caught:
            self.capture(max_rows=3)
        self.assertEqual(caught.exception.code, "budget_exceeded")
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.page_calls, 0)
        self.assertEqual(self.capture(max_rows=10)["rows"], 5)

    def test_page_budget_can_increase_on_resume(self):
        with self.assertRaises(AnalyticsError):
            self.capture(max_pages=1)
        self.assertEqual(capture_status(self.output)["rows"], 2)
        self.assertEqual(self.capture(max_pages=10)["rows"], 5)

    def test_output_byte_budget_pauses_before_overbudget_page(self):
        with self.assertRaises(AnalyticsError) as caught:
            self.capture(max_bytes=1)
        self.assertEqual(caught.exception.code, "budget_exceeded")
        self.assertEqual(capture_status(self.output)["rows"], 0)
        self.assertFalse(self.output.exists())

    def test_storage_budget_accounts_for_staging_and_final_copy(self):
        with self.assertRaises(AnalyticsError) as caught:
            self.capture(max_storage_bytes=100)
        self.assertEqual(caught.exception.code, "budget_exceeded")
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.page_calls, 0)

    def test_minimum_free_disk_enforced(self):
        with patch("analytics311.capture.shutil.disk_usage", return_value=type("Disk", (), {"free": 5})()):
            with self.assertRaises(AnalyticsError) as caught:
                self.capture(min_free_bytes=100)
        self.assertEqual(caught.exception.code, "budget_exceeded")

    def test_matching_job_identity_required_to_resume(self):
        self.source.fail_page = 2
        with self.assertRaises(KeyboardInterrupt):
            self.capture()
        with self.assertRaises(AnalyticsError) as caught:
            capture_window("2025-01-01", "2025-01-03", self.output, client=self.source)
        self.assertEqual(caught.exception.code, "capture_identity_mismatch")
        self.assertEqual(capture_status(self.output)["rows"], 2)

    def test_complete_resume_needs_no_network_and_detects_tampered_output(self):
        result = self.capture()
        calls = len(self.source.calls)
        self.assertEqual(self.capture(), result)
        self.assertEqual(len(self.source.calls), calls)
        self.output.write_text("tampered", encoding="utf-8")
        with self.assertRaises(AnalyticsError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, "output_conflict")

    def test_empty_window_reconciles_without_inventing_coverage(self):
        self.source = Source([])
        result = self.capture()
        self.assertEqual(result["rows"], 0)
        self.assertEqual(self.output.read_bytes(), b"")
        self.assertFalse(result["coverage_complete"])

    def test_retry_transient_errors_is_bounded_and_no_duplicate_commit(self):
        original = self.source.get_json
        calls = 0
        def flaky(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise URLError("temporary")
            return original(*args, **kwargs)
        self.source.get_json = flaky
        with patch("analytics311.capture.time.sleep") as sleeper:
            self.assertEqual(self.capture(retries=1)["rows"], 5)
        sleeper.assert_called_once_with(1)

    def test_retry_exhaustion_retains_paused_checkpoint(self):
        self.source.get_json = lambda *args, **kwargs: (_ for _ in ()).throw(URLError("do not print secret url"))
        with patch("analytics311.capture.time.sleep") as sleeper:
            with self.assertRaises(AnalyticsError) as caught:
                self.capture(retries=2)
        self.assertEqual(caught.exception.code, "source_unavailable")
        self.assertEqual(sleeper.call_count, 2)
        self.assertEqual(capture_status(self.output)["status"], "paused")
        self.assertNotIn("secret", caught.exception.message)

    def test_permanent_http_error_not_retried(self):
        self.source.get_json = lambda *args, **kwargs: (_ for _ in ()).throw(HTTPError("https://private.invalid", 403, "no", {}, None))
        with patch("analytics311.capture.time.sleep") as sleeper:
            with self.assertRaises(AnalyticsError) as caught:
                self.capture(retries=3)
        self.assertEqual(caught.exception.code, "source_http_error")
        sleeper.assert_not_called()

    def test_changed_local_checkpoint_totals_quarantine(self):
        self.source.fail_page = 2
        with self.assertRaises(KeyboardInterrupt):
            self.capture()
        with closing(sqlite3.connect(str(self.output) + ".capture.sqlite3")) as db:
            with db:
                db.execute("DELETE FROM records WHERE unique_key='00000001'")
        with self.assertRaises(AnalyticsError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, "invalid_capture_state")
        self.assertEqual(capture_status(self.output)["status"], "quarantined")

    def test_interruption_during_page_transaction_rolls_back_records_and_cursor(self):
        original = capture_module._save
        failed = False
        def interrupted_save(db, state):
            nonlocal failed
            original(db, state)
            if state["rows"] and not failed:
                failed = True
                raise KeyboardInterrupt()
        with patch("analytics311.capture._save", side_effect=interrupted_save):
            with self.assertRaises(KeyboardInterrupt):
                self.capture()
        self.assertEqual(capture_status(self.output)["rows"], 0)
        self.assertEqual(self.capture()["rows"], 5)

    def test_manifest_publish_failure_recovers_frozen_stage_without_network(self):
        with patch("analytics311.capture._atomic_json", side_effect=OSError("simulated interrupted manifest write")):
            with self.assertRaises(AnalyticsError) as caught:
                self.capture()
        self.assertEqual(caught.exception.code, "capture_storage_error")
        self.assertTrue(self.output.exists())
        self.assertFalse(self.output.with_suffix(".manifest.json").exists())
        self.assertEqual(capture_status(self.output)["status"], "publishing")
        calls = len(self.source.calls)
        result = self.capture()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(self.source.calls), calls)
        self.assertEqual(json.loads(self.output.with_suffix(".manifest.json").read_text())["sha256"], _file_digest(self.output))

    def test_invocation_time_budget_preserves_resumable_checkpoint(self):
        with patch("analytics311.capture.time.monotonic", side_effect=[0, 2]):
            with self.assertRaises(AnalyticsError) as caught:
                self.capture(max_seconds=1)
        self.assertEqual(caught.exception.code, "budget_exceeded")
        self.assertEqual(capture_status(self.output)["status"], "paused")
        self.assertFalse(self.output.exists())

    def test_non_unique_source_count_quarantines_before_rows(self):
        original = self.source.get_json
        def nonunique(path, params=None, **kwargs):
            result, headers = original(path, params, **kwargs)
            if params and params["$select"].startswith("count("):
                result[0]["unique_count"] = "4"
            return result, headers
        self.source.get_json = nonunique
        with self.assertRaises(AnalyticsError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, "source_keys_not_unique")
        self.assertEqual(self.source.page_calls, 0)


def _file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TransportTests(unittest.TestCase):
    def test_app_token_is_header_only_and_response_size_bounded(self):
        class Response(io.BytesIO):
            headers = {}
        class Opener:
            def open(self, request, timeout):
                self.request = request
                return Response(b"[]")
        opener = Opener()
        with patch.dict("os.environ", {"SOCRATA_APP_TOKEN": "secret-test-token"}):
            client = SocrataClient(opener)
            self.assertEqual(client.get_json("/resource/erm2-nwe9.json", {"$limit": 0})[0], [])
        self.assertEqual(opener.request.get_header("X-app-token"), "secret-test-token")
        self.assertNotIn("secret-test-token", opener.request.full_url)
        with self.assertRaises(AnalyticsError) as caught:
            client.get_json("/resource/erm2-nwe9.json", max_bytes=1)
        self.assertEqual(caught.exception.code, "budget_exceeded")


if __name__ == "__main__":
    unittest.main()
