import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analytics311.elastic import ElasticBackend
from analytics311.errors import AnalyticsError
from analytics311.maps import KibanaClient
from analytics311.resources import asset_path
from analytics311.service import AnalyticsService, file_hash, read_json
from test_elastic import FakeClient, INDEX, MANIFEST, hit, page, spec


class ExportHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {"backend": "fixture", "fixture_path": str(asset_path("fixtures/requests.jsonl")),
                       "manifest_path": str(asset_path("fixtures/manifest.json")),
                       "catalog_path": str(asset_path("config/catalog.json")),
                       "runs_dir": str(self.root / "runs"), "export_inline": True,
                       "budgets": {"deadline_seconds": 1, "export_deadline_seconds": 10}}
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.service = AnalyticsService(config_path)
        self.request = {"dataset_version": "fixture-v1", "operation": "records",
                        "filters": {"field": "unique_key", "op": "in", "value": ["FIX-021", "FIX-022", "FIX-023", "FIX-032"]}}

    def test_export_can_outlive_query_budget_without_rereading_csv(self):
        result = self.service.run_analysis(self.request)
        original = self.service.backend.iter_records
        clock = [0]

        def slow_rows(request, **kwargs):
            for row in original(request, **kwargs):
                clock[0] += 2
                yield row

        def source_hash_only(path):
            self.assertNotEqual(Path(path).suffix, ".part", "CSV digest must be accumulated while writing")
            return file_hash(path)

        with patch("analytics311.service.time.monotonic", side_effect=lambda: clock[0]), \
             patch.object(self.service.backend, "iter_records", side_effect=slow_rows), \
             patch("analytics311.service.file_hash", side_effect=source_hash_only):
            job = self.service.export_csv(result["result_id"], "records", "all_matching")
        self.assertEqual(job["status"], "complete", job)
        self.assertEqual(job["rows_written"], 4)
        self.assertEqual(job["sha256"], hashlib.sha256(Path(job["file"]).read_bytes()).hexdigest())
        self.assertGreater(clock[0], self.config["budgets"]["deadline_seconds"])

    def test_empty_export_cannot_publish_after_deadline(self):
        request = {**self.request, "filters": {"field": "unique_key", "op": "eq", "value": "absent"}}
        result = self.service.run_analysis(request)
        clock = [0]

        def delayed_empty(request, **kwargs):
            clock[0] = 11
            return iter(())

        with patch("analytics311.service.time.monotonic", side_effect=lambda: clock[0]), \
             patch.object(self.service.backend, "iter_records", side_effect=delayed_empty):
            job = self.service.export_csv(result["result_id"], "records", "all_matching")
        self.assertEqual(job["status"], "failed", job)
        self.assertEqual(job["error"]["code"], "budget_exceeded")
        self.assertEqual(list(self.service.runs.glob("*.csv*")), [])
        self.assertEqual(list(self.service.runs.glob("*.export")), [])

    def test_comparison_periods_share_one_deadline(self):
        request = {"dataset_version": "fixture-v1", "operation": "compare_periods",
                   "periods": {"baseline": {"gte": "2025-11-01T00:00:00-04:00", "lt": "2025-12-01T00:00:00-05:00"},
                               "current": {"gte": "2025-12-01T00:00:00-05:00", "lt": "2026-01-01T00:00:00-05:00"}}}
        original = self.service.backend.execute
        clock, deadlines = [0], []

        def slow_period(request, **kwargs):
            deadlines.append(kwargs.get("deadline"))
            clock[0] += .75
            return original(request, **kwargs)

        with patch("analytics311.service.time.monotonic", side_effect=lambda: clock[0]), \
             patch.object(self.service.backend, "execute", side_effect=slow_period), self.assertRaises(AnalyticsError) as caught:
            self.service.run_analysis(request)
        self.assertEqual(caught.exception.code, "budget_exceeded")
        self.assertEqual(deadlines, [1, 1])
        self.assertFalse(list(self.service.runs.glob("*.json")))

    def test_saved_result_read_once_while_identity_still_verified(self):
        result = self.service.run_analysis(self.request)
        with patch("analytics311.service.read_json", wraps=read_json) as reader:
            received = self.service.get_result(result["result_id"])
        self.assertEqual(received["total"]["value"], 4)
        self.assertEqual(reader.call_count, 1)
        with patch.object(self.service, "_identity", return_value="changed"), self.assertRaises(AnalyticsError) as caught:
            self.service.get_result(result["result_id"])
        self.assertEqual(caught.exception.code, "result_expired")

    def test_aggregate_export_stream_digest_matches_quoted_unicode_bytes(self):
        path = self.root / "unicode.jsonl"
        path.write_text(json.dumps({"unique_key": "one", "borough": '=\"🌍\",\nline', "is_closed": False}) + "\n", encoding="utf-8")
        self.service.backend.path = path
        self.service.config["fixture_path"] = str(path)
        result = self.service.run_analysis({"dataset_version": "fixture-v1", "operation": "aggregate", "group_by": [{"field": "borough"}]})
        job = self.service.export_csv(result["result_id"], "aggregates", "all_matching", columns=["borough", "count"])
        self.assertEqual(job["status"], "complete", job)
        data = Path(job["file"]).read_bytes()
        self.assertEqual(job["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(job["bytes_written"], len(data))
        with open(job["file"], encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(list(csv.DictReader(stream)), [{"borough": '\'=\"🌍\",\nline', "count": "1"}])


class ElasticIntegrityTests(unittest.TestCase):
    def backend(self, responses):
        client = FakeClient(responses)
        return ElasticBackend({"index": INDEX}, {}, MANIFEST, client=client), client

    def test_incomplete_composite_counts_cannot_claim_complete(self):
        for buckets in ([], [{"key": {"borough": "A"}, "doc_count": 1}], [{"key": {"borough": "A"}, "doc_count": 3}]):
            backend, client = self.backend([page(total=2, buckets=buckets)])
            with self.subTest(buckets=buckets), self.assertRaises(AnalyticsError) as caught:
                backend.execute(spec("aggregate", group_by=[{"field": "borough"}]))
            self.assertEqual(caught.exception.code, "partial_execution")
            self.assertEqual(client.calls[-1][0], "DELETE")

    def test_malformed_counts_dimensions_and_records_are_typed_failures(self):
        cases = [(spec(), page(-1)), (spec(), page(hits=[None])),
                 (spec("aggregate", group_by=[{"field": "borough"}]), page(buckets=[{"key": {"agency": "A"}, "doc_count": 2}])),
                 (spec("aggregate", group_by=[{"field": "borough"}]), page(buckets=[{"key": {"borough": "A"}, "doc_count": -1}])),
                 (spec("aggregate", group_by=[{"field": "borough"}]), page(aggregations={"groups": []}))]
        for request, response in cases:
            backend, client = self.backend([response])
            with self.subTest(response=response), self.assertRaises(AnalyticsError) as caught:
                backend.execute(request)
            self.assertEqual(caught.exception.code, "partial_execution")
            self.assertEqual(client.calls[-1][0], "DELETE")

    def test_export_uses_supplied_deadline_and_compiles_selection_once(self):
        backend, client = self.backend([page(1, hits=[hit(1)]), page(1)])
        from analytics311.compiler import compile_query
        with patch("analytics311.elastic.time.monotonic", return_value=50), \
             patch("analytics311.compiler.compile_query", wraps=compile_query) as compiler:
            self.assertEqual(len(list(backend.iter_records(spec(), deadline=300))), 1)
        self.assertEqual(compiler.call_count, 1)
        searches = [call[2] for call in client.calls if call[1].startswith("/_search")]
        self.assertTrue(all(body["timeout"] == "250000ms" for body in searches))
        backend, client = self.backend([])
        with patch("analytics311.elastic.time.monotonic", return_value=301), self.assertRaises(AnalyticsError):
            list(backend.iter_records(spec(), deadline=300))
        self.assertFalse(any(call[1].startswith("/_search") for call in client.calls))

    def test_bad_kibana_origins_and_space_return_configuration_errors(self):
        for config in ({"url": None}, {"url": []}, {"url": "http://[bad"}, {"url": "http://localhost:abc"},
                       {"url": "http://localhost:0"}, {"url": "http://localhost:5601", "allow_insecure_local": True, "space": 12}):
            with self.subTest(config=config), self.assertRaises(AnalyticsError) as caught:
                KibanaClient(config)
            self.assertEqual(caught.exception.code, "invalid_configuration")
