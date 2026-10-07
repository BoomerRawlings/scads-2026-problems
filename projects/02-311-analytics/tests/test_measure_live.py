import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analytics311.errors import AnalyticsError


spec = importlib.util.spec_from_file_location("measure_live", Path(__file__).resolve().parents[1] / "tools/measure_live.py")
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)


def suite():
    return {"analyses": {"filter": {"operation": "records", "filters": {"field": "borough"}},
                         "group": {"operation": "aggregate", "group_by": [{"field": "borough"}]},
                         "closure": {"operation": "aggregate", "metrics": ["mean_closure_hours"]},
                         "geo": {"operation": "records", "geo": {"type": "radius"}},
                         "compare": {"operation": "compare_periods"}},
            "export": {"operation": "records", "time": {"gte": "2025-10-01", "lt": "2025-10-02"}}}


class LiveMeasurementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)

    def write_ids(self, rows, name="ids.csv"):
        path = self.path / name
        with path.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows([["unique_key"], *[[row] for row in rows]])
        return path

    def test_independent_membership_is_order_independent_but_file_hash_is_not(self):
        first, ids = measure.inspect_ids(self.write_ids(["3", "1", "2"]), oracle=True)
        second, _ = measure.inspect_ids(self.write_ids(["1", "2", "3"], "second.csv"), oracle=True)
        self.assertEqual(ids, {"1", "2", "3"})
        self.assertEqual(first["membership_sha256"], second["membership_sha256"])
        self.assertNotEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["rows"], 3)

    def test_duplicate_and_missing_identifiers_fail(self):
        for rows in (["1", "1"], [""]):
            with self.subTest(rows=rows):
                with self.assertRaises(AnalyticsError):
                    measure.inspect_ids(self.write_ids(rows), oracle=True)

    def test_oracle_schema_and_size_are_bounded(self):
        path = self.write_ids(["1"])
        path.write_text("unique_key,extra\n1,x\n", encoding="utf-8")
        with self.assertRaises(AnalyticsError) as caught:
            measure.inspect_ids(path, oracle=True)
        self.assertEqual(caught.exception.code, "oracle_schema_mismatch")
        path = self.write_ids(["1", "2"])
        with patch.object(measure, "MAX_CSV_ROWS", 1):
            with self.assertRaises(AnalyticsError):
                measure.inspect_ids(path, oracle=True)
        with patch.object(measure, "MAX_CSV_BYTES", 1):
            with self.assertRaises(AnalyticsError):
                measure.inspect_ids(path, oracle=True)

    def test_representative_export_requires_exact_columns_and_complete_rows(self):
        path = self.path / "export.csv"
        row = ["1", "2025-10-01T04:00:00+00:00", "Noise - Residential", "loud, music\ncontinued",
               "BROOKLYN", "NYPD", "Closed", "BK0101", "1.5"]
        with path.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows([measure.EXPORT_COLUMNS, row])
        observed, ids = measure.inspect_ids(path)
        expected, _ = measure.inspect_ids(self.write_ids(["1"]), oracle=True)
        self.assertEqual(ids, {"1"})
        self.assertEqual(observed["membership_sha256"], expected["membership_sha256"])
        self.assertEqual(observed["columns"], list(measure.EXPORT_COLUMNS))
        self.assertGreater(observed["bytes"], expected["bytes"])
        for columns, values in ((["unique_key"], ["1"]), (list(reversed(measure.EXPORT_COLUMNS)), list(reversed(row))),
                                (measure.EXPORT_COLUMNS, row[:-1]), (measure.EXPORT_COLUMNS, row + ["extra"])):
            with self.subTest(columns=columns, values=values):
                with path.open("w", encoding="utf-8", newline="") as stream:
                    csv.writer(stream).writerows([columns, values])
                with self.assertRaises(AnalyticsError): measure.inspect_ids(path)

    def test_five_actual_workload_families_required(self):
        self.assertEqual(measure.validate_suite(suite()), suite())
        for family in measure.CASES:
            value = suite()
            del value["analyses"][family]
            with self.subTest(family=family), self.assertRaises(AnalyticsError):
                measure.validate_suite(value)
        value = suite()
        value["analyses"]["closure"]["metrics"] = ["count"]
        with self.assertRaises(AnalyticsError):
            measure.validate_suite(value)

    def test_generated_and_unreconciled_manifest_do_not_qualify(self):
        self.assertFalse(measure.has_real_capture({"kind": "generated_test_fixture", "row_count": 10_000_000}))
        value = {"source_kind": "real_public_records", "kind": "reconciled_public_capture",
                 "extraction_complete": True, "observed_complete": False}
        self.assertFalse(measure.has_real_capture(value))
        value["observed_complete"] = True
        self.assertTrue(measure.has_real_capture({"provenance": {"provenance": value}}))

    def test_node_samples_keep_numbers_and_hide_node_host_names(self):
        class Client:
            def request(self, method, path):
                return {"_nodes": {"failed": 0}, "nodes": {"private-id": {
                    "name": "private-name", "host": "private-host", "jvm": {"mem": {"heap_used_in_bytes": 123}},
                    "process": {"mem": {"total_virtual_in_bytes": 456}},
                    "indices": {"query_cache": {"hit_count": 7}}}}}
        sample = measure.node_sample(Client(), "before")
        text = json.dumps(sample)
        self.assertNotIn("private", text)
        self.assertEqual(sample["nodes"][0]["jvm"]["mem"]["heap_used_in_bytes"], 123)
        self.assertEqual(sample["nodes"][0]["process"]["mem"]["total_virtual_in_bytes"], 456)

    def test_partial_node_stats_fail_instead_of_zero_memory(self):
        class Client:
            def request(self, *args):
                return {"_nodes": {"failed": 1}, "nodes": {}}
        with self.assertRaises(AnalyticsError):
            measure.node_sample(Client(), "before")

    def test_empty_memory_objects_do_not_pass_measurement_completeness(self):
        class Client:
            def request(self, *args):
                return {"_nodes": {"failed": 0}, "nodes": {"id": {"jvm": {}, "process": {}, "indices": {}}}}
        with self.assertRaises(AnalyticsError): measure.node_sample(Client(), "before")

    def test_unexpected_sampler_error_is_retained(self):
        class ImmediateEvent:
            def wait(self, seconds): return False
            def set(self): pass
        samples = []
        sampler = measure.Sampler(None, samples)
        sampler.stop = ImmediateEvent()
        with patch.object(measure, "node_sample", side_effect=[{"phase": "before"}, ValueError("untrusted details")]):
            sampler.start()
            sampler.thread.join(timeout=2)
        self.assertFalse(sampler.thread.is_alive())
        self.assertEqual(samples[1], {"phase": "during", "error_code": "sampler_failed", "exception_type": "ValueError"})

    def test_cleanup_continues_after_one_owned_handle_wait_fails(self):
        class Process:
            def __init__(self, fail=False): self.fail, self.waited = fail, False
            def poll(self): return 0
            def wait(self, timeout):
                self.waited = True
                if self.fail: raise OSError("test")
        first, second = Process(True), Process()
        workers = measure.Workers(self.path)
        workers.processes = {"one": first, "two": second}
        self.assertEqual(workers.cleanup(), ["owned_worker_wait_failed"])
        self.assertTrue(first.waited)
        self.assertTrue(second.waited)

    def test_linux_rss_parser_does_not_use_virtual_memory(self):
        with patch.object(Path, "read_text", return_value="Name:\tpython\nVmSize:\t99999 kB\nVmRSS:\t123 kB\n"):
            self.assertEqual(measure.rss_bytes(), 123 * 1024)
        with patch.object(Path, "read_text", side_effect=FileNotFoundError()):
            self.assertIsNone(measure.rss_bytes())

    def test_small_real_snapshot_failure_keeps_partial_receipt_without_query(self):
        oracle = self.write_ids(["1"])
        suite_path = self.path / "suite.json"
        suite_path.write_text(json.dumps(suite()))
        output = self.path / "report.json"
        class Service:
            def __init__(self, *args):
                self.manifest = {"immutable": True, "row_count": 1}
        config = {"backend": "elastic", "elastic_url": "http://127.0.0.1:9200", "index": "nyc311-real-v1"}
        with patch.object(measure, "load_profile", return_value=(self.path / "source.json", config)), \
             patch.object(measure, "AnalyticsService", Service):
            result = measure.run_measurements("ignored", suite_path, output, self.path / "work", oracle)
        self.assertFalse(result["passed"])
        self.assertEqual(result["error"]["code"], "real_million_snapshot_required")
        self.assertEqual(json.loads(output.read_text())["queries"], [])

    def test_existing_output_and_invalid_budgets_are_refused(self):
        output = self.path / "report.json"
        output.write_text("preserve")
        with self.assertRaises(AnalyticsError):
            measure.run_measurements("ignored", "ignored", output, self.path / "work", "ignored")
        self.assertEqual(output.read_text(), "preserve")
        for repeats in (0, True, 11):
            with self.subTest(repeats=repeats), self.assertRaises(AnalyticsError):
                measure.run_measurements("ignored", "ignored", self.path / "new", self.path / "work", "ignored", repeats=repeats)


if __name__ == "__main__":
    unittest.main()
