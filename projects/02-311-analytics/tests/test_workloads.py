import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analytics311.workloads import fetch_sample, generate, normalize_file
from analytics311.errors import AnalyticsError


class WorkloadTests(unittest.TestCase):
    def test_sample_refuses_provider_rows_above_request_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.jsonl"
            rows = [{"unique_key": str(i), "created_date": "2025-01-01T12:00:00"} for i in range(2)]
            with patch("analytics311.workloads.urlopen", return_value=io.BytesIO(json.dumps(rows).encode())):
                with self.assertRaises(AnalyticsError) as error:
                    fetch_sample("2025-01-01", "2025-01-02", path, max_records=1)
            self.assertEqual("budget_exceeded", error.exception.code)
            self.assertFalse(path.exists())
            self.assertFalse(path.with_suffix(".manifest.json").exists())

    def test_sample_refuses_duplicates_out_of_order_and_out_of_window_rows(self):
        for rows in ([{"unique_key": key, "created_date": "2025-01-01T12:00:00"} for key in ("2", "1")],
                     [{"unique_key": "1", "created_date": "2025-01-01T12:00:00"}] * 2,
                     [{"unique_key": "1", "created_date": "2025-01-02T00:00:00"}]):
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "sample.jsonl"
                with patch("analytics311.workloads.urlopen", return_value=io.BytesIO(json.dumps(rows).encode())):
                    with self.assertRaises(AnalyticsError) as error:
                        fetch_sample("2025-01-01", "2025-01-02", path, max_records=2)
                self.assertEqual("partial_execution", error.exception.code)
                self.assertFalse(path.exists())
                self.assertFalse(path.with_suffix(".manifest.json").exists())

    def test_sample_exact_budget_stays_incomplete_and_matches_its_hash(self):
        from analytics311.service import file_hash
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.jsonl"
            rows = [{"unique_key": str(i), "created_date": "2025-01-01T12:00:00"} for i in range(2)]
            with patch("analytics311.workloads.urlopen", return_value=io.BytesIO(json.dumps(rows).encode())) as network:
                result = fetch_sample("2025-01-01", "2025-01-02", path, max_records=2)
            self.assertEqual(1, network.call_count)
            self.assertEqual(2, result["row_count"])
            self.assertEqual(file_hash(path), result["sha256"])
            self.assertFalse(result["coverage"]["complete"])

    def test_new_output_never_overwrites_orphaned_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.jsonl"
            sidecar = path.with_suffix(".manifest.json")
            sidecar.write_text('{"previous":"capture"}', encoding="utf-8")
            with self.assertRaises(AnalyticsError):
                generate(path, 1)
            self.assertEqual('{"previous":"capture"}', sidecar.read_text())
            self.assertFalse(path.exists())

    def test_normalization_limits_redundant_full_file_hash_reads(self):
        from analytics311.service import file_hash
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory) / "raw.jsonl", Path(directory) / "normalized.jsonl"
            generate(source, 10)
            with patch("analytics311.workloads.file_hash", wraps=file_hash) as hashing:
                result = normalize_file(source, destination)
            paths = [Path(call.args[0]) for call in hashing.call_args_list]
            # Additional source passes remain pre/post guards. The processing
            # pass also hashes actual bytes; staged metadata adds no full scan.
            self.assertLessEqual(paths.count(source), 2)
            self.assertLessEqual(paths.count(destination), 1)
            self.assertEqual(file_hash(destination), result["sha256"])
            self.assertTrue(result["coverage"]["complete"])

    def test_generation_is_reproducible_streamed_and_labeled(self):
        with tempfile.TemporaryDirectory() as directory:
            first = generate(Path(directory) / "one.jsonl", 1500, 42)
            second = generate(Path(directory) / "two.jsonl", 1500, 42)
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(first["row_count"], 1500)
            with open(first["file"]) as stream:
                keys = {json.loads(line)["unique_key"] for line in stream}
            self.assertEqual(len(keys), 1500)
            self.assertEqual(first["kind"], "generated_workload")
            self.assertIn("not NYC findings", first["source"])

    def test_normalization_keeps_failures_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "raw.jsonl"
            source.write_text('\n'.join([json.dumps({"unique_key": "1", "created_date": "2025-12-01T12:00:00", "status": "Open"}),
                                         json.dumps({"created_date": "2025-12-01T12:00:00"}), "not json"]))
            result = normalize_file(source, Path(directory) / "normalized.jsonl")
            self.assertEqual(result["row_count"], 1)
            self.assertEqual(result["quality_counts"]["rejected"], 1)
            self.assertEqual(result["quality_counts"]["invalid_json"], 1)
            self.assertFalse(result["coverage"]["complete"])

    def test_generator_rejects_overwrite_and_invalid_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.jsonl"
            generate(path, 1)
            with self.assertRaises(AnalyticsError):
                generate(path, 1)
            with self.assertRaises(AnalyticsError):
                generate(Path(directory) / "other.jsonl", 0)
