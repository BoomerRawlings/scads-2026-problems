import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from analytics311.errors import AnalyticsError
from analytics311.ingest import normalize_record
from analytics311.workloads import normalize_file


class NormalizationBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.jsonl"
        self.output = self.root / "normalized.jsonl"
        self.partial = self.root / "normalized.jsonl.part"
        self.manifest = self.root / "normalized.manifest.json"
        self.rows = [{"unique_key": str(i), "created_date": "2025-01-01T12:00:00", "status": "Open"}
                     for i in (1, 2)]
        self.write_source(self.rows)

    def write_source(self, rows):
        self.source.write_bytes(b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8") for row in rows))

    @staticmethod
    def normalized_bytes(row):
        return (json.dumps(normalize_record(row), allow_nan=False) + "\n").encode("utf-8")

    def assert_unpublished(self):
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())

    def test_exact_byte_cap_publishes_portable_bytes_and_limits(self):
        expected = b"".join(self.normalized_bytes(row) for row in self.rows)
        result = normalize_file(self.source, self.output, max_output_bytes=len(expected), min_free_bytes=0)
        self.assertEqual(expected, self.output.read_bytes())
        self.assertEqual(len(expected), result["bytes"])
        self.assertEqual({"max_output_bytes": len(expected), "min_free_bytes": 0}, result["normalization_limits"])
        self.assertEqual(result["bytes"], json.loads(self.manifest.read_text())["bytes"])

    def test_cap_rejects_next_record_and_preserves_partial_for_inspection(self):
        first = self.normalized_bytes(self.rows[0])
        with self.assertRaises(AnalyticsError) as error:
            normalize_file(self.source, self.output, max_output_bytes=len(first), min_free_bytes=0)
        self.assertEqual("budget_exceeded", error.exception.code)
        self.assertIn("does not resume", str(error.exception))
        self.assert_unpublished()
        self.assertEqual(first, self.partial.read_bytes())
        with self.assertRaises(AnalyticsError):
            normalize_file(self.source, self.output, max_output_bytes=100000, min_free_bytes=0)
        self.assertEqual(first, self.partial.read_bytes())

    def test_escaped_output_is_budgeted_by_wire_bytes(self):
        row = {**self.rows[0], "descriptor": "\u0080" * 100}
        self.write_source([row])
        normalized = self.normalized_bytes(row)
        self.assertGreater(len(normalized), len(self.source.read_bytes()))
        with self.assertRaises(AnalyticsError) as error:
            normalize_file(self.source, self.output, max_output_bytes=len(normalized) - 1, min_free_bytes=0)
        self.assertEqual("budget_exceeded", error.exception.code)
        self.assertEqual(b"", self.partial.read_bytes())
        self.assert_unpublished()

    def test_reserve_shortage_before_start_creates_no_partial(self):
        with patch("analytics311.workloads.shutil.disk_usage", return_value=SimpleNamespace(free=99)), patch(
            "analytics311.workloads.file_hash"
        ) as hashing:
            with self.assertRaises(AnalyticsError) as error:
                normalize_file(self.source, self.output, min_free_bytes=100)
            hashing.assert_not_called()
        self.assertEqual("budget_exceeded", error.exception.code)
        self.assertFalse(self.partial.exists())
        self.assert_unpublished()

    def test_partial_appearing_after_preflight_is_not_overwritten(self):
        def inject_partial(*args, **kwargs):
            self.partial.write_bytes(b"another writer owns these bytes\n")
            return {}

        with patch("analytics311.workloads.source_manifest", side_effect=inject_partial):
            with self.assertRaises(FileExistsError):
                normalize_file(self.source, self.output, min_free_bytes=0)
        self.assertEqual(b"another writer owns these bytes\n", self.partial.read_bytes())
        self.assert_unpublished()

    def test_unobserved_writes_are_deducted_before_next_row(self):
        first = self.normalized_bytes(self.rows[0])
        with patch("analytics311.workloads.shutil.disk_usage", side_effect=[
            SimpleNamespace(free=100 + len(first)), SimpleNamespace(free=100)
        ]) as disk:
            with self.assertRaises(AnalyticsError) as error:
                normalize_file(self.source, self.output, min_free_bytes=100)
        self.assertEqual("budget_exceeded", error.exception.code)
        self.assertEqual(2, disk.call_count)
        self.assertEqual(first, self.partial.read_bytes())
        self.assert_unpublished()

    def test_periodic_check_observes_external_disk_consumption(self):
        first = self.normalized_bytes(self.rows[0])
        with patch("analytics311.workloads._NORMALIZATION_DISK_CHECK_BYTES", len(first)), patch(
            "analytics311.workloads.shutil.disk_usage", side_effect=[
                SimpleNamespace(free=10_000), SimpleNamespace(free=100)
            ]
        ) as disk:
            with self.assertRaises(AnalyticsError) as error:
                normalize_file(self.source, self.output, min_free_bytes=100)
        self.assertEqual("budget_exceeded", error.exception.code)
        self.assertEqual(2, disk.call_count)
        self.assertEqual(first, self.partial.read_bytes())
        self.assert_unpublished()

    def test_final_reserve_check_prevents_publication(self):
        with patch("analytics311.workloads.shutil.disk_usage", side_effect=[
            SimpleNamespace(free=10_000), SimpleNamespace(free=99)
        ]):
            with self.assertRaises(AnalyticsError) as error:
                normalize_file(self.source, self.output, min_free_bytes=100)
        self.assertEqual("budget_exceeded", error.exception.code)
        self.assertEqual(b"".join(self.normalized_bytes(row) for row in self.rows), self.partial.read_bytes())
        self.assert_unpublished()

    def test_invalid_limits_fail_before_reading_source(self):
        for options in ({"max_output_bytes": True}, {"max_output_bytes": 0},
                        {"max_output_bytes": 10 ** 15 + 1}, {"min_free_bytes": -1},
                        {"min_free_bytes": 1.5}, {"min_free_bytes": 10 ** 15 + 1}):
            with self.subTest(options=options), patch("analytics311.workloads.file_hash") as hashing:
                with self.assertRaises(AnalyticsError) as error:
                    normalize_file(self.source, self.output, **options)
                self.assertEqual("invalid_spec", error.exception.code)
                hashing.assert_not_called()
        self.assertFalse(self.partial.exists())


if __name__ == "__main__":
    unittest.main()
