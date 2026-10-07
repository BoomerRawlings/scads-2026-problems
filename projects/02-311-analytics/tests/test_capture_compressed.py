from contextlib import closing
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from analytics311.errors import AnalyticsError
from tools import capture_compressed as module
from test_capture import Source


class CompressedCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "capture.jsonl.gz"
        self.source = Source()
        self.disk = patch.object(module.shutil, "disk_usage", return_value=type("Disk", (), {"free": 10_000_000_000})())
        self.disk.start()
        self.addCleanup(self.disk.stop)

    def capture(self, **options):
        args = {"page_size": 2, "max_rows": 100, "max_bytes": 1_000_000,
                "max_pages": 100, "max_seconds": 30, "retries": 0, "client": self.source}
        args.update(options)
        return module.capture_compressed("2025-01-01", "2025-01-02", self.output, **args)

    def state(self):
        _, checkpoint, _, _ = module.paths(self.output)
        with closing(sqlite3.connect(checkpoint)) as db:
            return module._load(db)

    def chunks(self):
        _, checkpoint, directory, _ = module.paths(self.output)
        with closing(sqlite3.connect(checkpoint)) as db:
            return [(directory / item["name"], item) for item in module.entries(db)]

    def test_manifest_describes_decompressed_bytes_and_separate_transport(self):
        result = self.capture()
        raw = gzip.decompress(self.output.read_bytes())
        rows = [json.loads(line) for line in raw.splitlines()]
        manifest = json.loads(Path(result["manifest"]).read_bytes())
        self.assertEqual([row["unique_key"] for row in rows], [row["unique_key"] for row in self.source.rows])
        self.assertEqual((manifest["row_count"], manifest["unique_key_count"]), (5, 5))
        self.assertEqual((manifest["bytes"], manifest["sha256"]), (len(raw), hashlib.sha256(raw).hexdigest()))
        self.assertEqual(manifest["transport"]["sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertEqual(manifest["transport"]["bytes"], self.output.stat().st_size)
        self.assertFalse(manifest["coverage"]["complete"])
        self.assertFalse(manifest["transactional_source_snapshot"])
        self.assertEqual(manifest["kind"], "reconciled_public_capture")
        self.assertEqual(len(self.chunks()), 3)
        checkpoint = Path(result["checkpoint"])
        with closing(sqlite3.connect(checkpoint)) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {"metadata", "chunks", "abandoned"})
        self.assertFalse(self.output.with_suffix("").exists())

    def test_interrupted_source_resumes_exact_cursor(self):
        self.source.fail_page = 2
        with self.assertRaises(KeyboardInterrupt):
            self.capture()
        self.assertEqual((self.state()["rows"], self.state()["status"]), (2, "paused"))
        self.assertFalse(self.output.exists())
        self.source.fail_page = None
        self.assertEqual(self.capture()["rows"], 5)
        self.assertEqual(len(gzip.decompress(self.output.read_bytes()).splitlines()), 5)

    def test_full_pending_chunk_commits_once_after_crash(self):
        with patch.object(module, "commit_chunk", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.capture()
        self.assertEqual(self.state()["rows"], 0)
        pending = self.state()["pending"]
        self.assertEqual(pending["rows"], 2)
        self.capture()
        self.assertEqual(len(self.chunks()), 3)
        self.assertEqual(self.chunks()[0][1]["name"], pending["name"])

    def test_truncated_owned_pending_is_retained_and_new_page_created(self):
        with patch.object(module, "commit_chunk", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.capture()
        _, checkpoint, directory, _ = module.paths(self.output)
        pending = directory / self.state()["pending"]["name"]
        prefix = pending.read_bytes()[:11]
        pending.write_bytes(prefix)
        self.capture()
        self.assertEqual(pending.read_bytes(), prefix)
        with closing(sqlite3.connect(checkpoint)) as db:
            abandoned = list(module.entries(db, "abandoned"))
        self.assertEqual(abandoned, [{"name": pending.name, "compressed_bytes": 11}])
        self.assertEqual(len(self.chunks()), 3)

    def test_unknown_orphan_is_never_overwritten(self):
        self.source.fail_page = 2
        with self.assertRaises(KeyboardInterrupt):
            self.capture()
        directory = module.paths(self.output)[2]
        orphan = directory / "foreign.gz"
        orphan.write_bytes(b"preserve me")
        self.source.fail_page = None
        with self.assertRaises(AnalyticsError) as error:
            self.capture()
        self.assertEqual(error.exception.code, "output_conflict")
        self.assertEqual(orphan.read_bytes(), b"preserve me")

    def test_corrupt_chunk_quarantines_without_publishing(self):
        self.source.fail_page = 2
        with self.assertRaises(KeyboardInterrupt):
            self.capture()
        chunk, _ = self.chunks()[0]
        data = bytearray(chunk.read_bytes())
        data[-1] ^= 1
        chunk.write_bytes(data)
        self.source.fail_page = None
        with self.assertRaises(AnalyticsError) as error:
            self.capture()
        self.assertEqual(error.exception.code, "invalid_capture_state")
        self.assertEqual(self.state()["status"], "quarantined")
        self.assertFalse(self.output.exists())

    def test_strict_order_and_duplicate_source_keys_quarantine(self):
        self.source.duplicate_page = True
        with self.assertRaises(AnalyticsError) as error:
            self.capture()
        self.assertEqual(error.exception.code, "duplicate_source_record")
        self.assertEqual(self.state()["rows"], 0)
        self.assertEqual(self.state()["status"], "quarantined")

    def test_source_drift_after_page_quarantines(self):
        self.source.drift_page = 2
        with self.assertRaises(AnalyticsError) as error:
            self.capture()
        self.assertEqual(error.exception.code, "source_changed")
        self.assertEqual(self.state()["rows"], 2)
        self.assertFalse(self.output.exists())

    def test_final_count_drift_never_publishes(self):
        self.source.final_count_adjustment = 1
        with self.assertRaises(AnalyticsError) as error:
            self.capture()
        self.assertEqual(error.exception.code, "source_changed")
        self.assertFalse(self.output.exists())

    def test_omitted_record_fails_reconciliation(self):
        self.source.omit_last = True
        with self.assertRaises(AnalyticsError) as error:
            self.capture()
        self.assertEqual(error.exception.code, "source_count_mismatch")
        self.assertFalse(self.output.exists())

    def test_resume_checks_source_revision_before_additional_pages(self):
        self.source.fail_page = 2
        with self.assertRaises(KeyboardInterrupt):
            self.capture()
        calls = self.source.page_calls
        self.source.metadata_drift = True
        self.source.fail_page = None
        with self.assertRaises(AnalyticsError) as error:
            self.capture()
        self.assertEqual(error.exception.code, "source_changed")
        self.assertEqual(self.source.page_calls, calls)

    def test_interrupted_publication_verifies_prefix_and_resumes_without_network(self):
        original = module.append_exact
        def interrupted(path, blocks, requests):
            first = next(iter(blocks))
            path.write_bytes(first[:9])
            raise KeyboardInterrupt
        with patch.object(module, "append_exact", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.capture()
        self.assertEqual(self.state()["status"], "publishing")
        calls = len(self.source.calls)
        self.capture()
        self.assertEqual(len(self.source.calls), calls)
        self.assertEqual(len(gzip.decompress(self.output.read_bytes()).splitlines()), 5)

    def test_wrong_publication_prefix_is_retained_and_rejected(self):
        def interrupted(path, blocks, requests):
            path.write_bytes(b"foreign")
            raise KeyboardInterrupt
        with patch.object(module, "append_exact", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.capture()
        partial = module.paths(self.output)[2] / self.state()["assembly"]
        with self.assertRaises(AnalyticsError) as error:
            self.capture()
        self.assertEqual(error.exception.code, "invalid_capture_state")
        self.assertEqual(partial.read_bytes(), b"foreign")

    def test_crash_after_exclusive_publication_link_recovers(self):
        original = Path.unlink
        tripped = False
        def interrupted(path, *args, **kwargs):
            nonlocal tripped
            if path.name.startswith("assembly-") and not tripped:
                tripped = True
                raise KeyboardInterrupt
            return original(path, *args, **kwargs)
        with patch.object(Path, "unlink", interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.capture()
        self.assertTrue(self.output.exists())
        self.assertEqual(self.output.stat().st_nlink, 2)
        self.capture()
        self.assertEqual(self.output.stat().st_nlink, 1)

    def test_chunk_change_between_verification_and_copy_never_publishes(self):
        original = module.append_exact
        def changed(path, blocks, requests):
            chunk, _ = self.chunks()[0]
            contents = bytearray(chunk.read_bytes())
            contents[-1] ^= 1
            chunk.write_bytes(contents)
            return original(path, blocks, requests)
        with patch.object(module, "append_exact", side_effect=changed):
            with self.assertRaises(AnalyticsError) as error:
                self.capture()
        self.assertEqual(error.exception.code, "invalid_capture_state")
        self.assertFalse(self.output.exists())
        self.assertEqual(self.state()["status"], "quarantined")

    def test_empty_capture_is_valid_gzip_with_empty_raw_digest(self):
        self.source = Source([])
        result = self.capture()
        self.assertEqual(gzip.decompress(self.output.read_bytes()), b"")
        self.assertEqual(result["sha256"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(result["rows"], 0)

    def test_free_space_reserve_prevents_source_requests(self):
        with patch.object(module.shutil, "disk_usage", return_value=type("Disk", (), {"free": 1_000_000_100})()):
            with self.assertRaises(AnalyticsError) as error:
                self.capture()
        self.assertEqual(error.exception.code, "budget_exceeded")
        self.assertFalse(self.source.calls)

    def test_budget_cannot_exceed_500mb_or_1000_row_pages(self):
        for options in ({"max_storage_bytes": 500_000_001}, {"page_size": 1001}, {"max_seconds": 86401}):
            with self.subTest(options=options), self.assertRaises(AnalyticsError) as error:
                self.capture(**options)
            self.assertEqual(error.exception.code, "invalid_spec")

    def test_page_budget_pauses_and_resume_does_not_duplicate(self):
        with self.assertRaises(AnalyticsError) as error:
            self.capture(max_pages=1)
        self.assertEqual(error.exception.code, "budget_exceeded")
        self.assertEqual(self.state()["rows"], 2)
        self.capture()
        self.assertEqual(self.state()["rows"], 5)

    def test_completed_capture_idempotent_and_no_source_requests(self):
        first = self.capture()
        calls = len(self.source.calls)
        second = self.capture()
        self.assertEqual(first, second)
        self.assertEqual(len(self.source.calls), calls)

    def test_decompressed_capture_passes_existing_observed_normalization_gate(self):
        from analytics311.workloads import normalize_file
        self.capture()
        raw = self.output.with_suffix("")
        raw.write_bytes(gzip.decompress(self.output.read_bytes()))
        result = normalize_file(raw, raw.with_name("normalized.jsonl"), max_output_bytes=1_000_000)
        self.assertEqual(result["row_count"], 5)
        self.assertEqual(result["comparison_qualification"]["scope"], "reconciled_observed_snapshot")
        self.assertFalse(result["comparison_qualification"]["population_complete"])
        self.assertFalse(result["coverage"]["complete"])

    def test_checkpoint_status_is_read_only_without_source_calls(self):
        self.source.fail_page = 2
        with self.assertRaises(KeyboardInterrupt):
            self.capture()
        calls = len(self.source.calls)
        progress = module.compressed_status(self.output)
        self.assertEqual((progress["rows"], progress["source_count"], progress["status"]), (2, 5, "paused"))
        self.assertEqual(len(self.source.calls), calls)
        self.assertIsNone(progress["file"])

    def test_conflicting_unowned_artifact_preserved(self):
        self.output.write_bytes(b"owned elsewhere")
        with self.assertRaises(AnalyticsError) as error:
            self.capture()
        self.assertEqual(error.exception.code, "output_conflict")
        self.assertEqual(self.output.read_bytes(), b"owned elsewhere")


if __name__ == "__main__":
    unittest.main()
