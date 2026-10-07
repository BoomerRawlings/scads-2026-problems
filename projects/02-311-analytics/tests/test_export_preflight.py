"""Exact export admission and field projection; tiny authored inputs only."""
import copy
from contextlib import nullcontext
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from analytics311.elastic import ElasticBackend
from analytics311.errors import AnalyticsError
from analytics311.fixture import FixtureBackend
from analytics311.resources import asset_path
from analytics311.service import AnalyticsService
from test_elastic import FakeClient, INDEX, MANIFEST, hit, page, spec


class ExportAdmissionTests(unittest.TestCase):
    def setUp(self):
        # Exercise admission without files, worker launches, or backend requests.
        self.service = object.__new__(AnalyticsService)
        self.service.runs = Path("unused-export-preflight-store")
        self.service.budgets = {"max_export_rows": 4, "max_concurrent_exports": 1}
        self.saved = {"kind": "analysis", "dataset_identity": "snapshot", "execution_complete": True,
                      "total": {"value": 5, "relation": "eq"}, "spec": {"operation": "aggregate"},
                      "all_rows": [{"group_id": "a", "count": 3}, {"group_id": "b", "count": 2}]}
        self.service._load = Mock(side_effect=lambda _: self.saved)
        self.service._start_export = Mock()
        self.service.get_result = Mock(side_effect=lambda _: self.service._start_export.call_args.args[0])
        self.reserve = self.enterContext(patch("analytics311.jobs.reserve_export", return_value=nullcontext()))

    def export(self, mode="records", scope="all_matching", ids=None):
        return self.service.export_csv("a" * 32, mode, scope, group_ids=ids)

    def rejected(self, code, **kwargs):
        with self.assertRaises(AnalyticsError) as caught:
            self.export(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.reserve.assert_not_called()
        self.service._start_export.assert_not_called()

    def test_entire_cohort_count_rejects_before_capacity_or_worker(self):
        # Saved groups may be thresholded; full records retain the original total.
        self.saved["all_rows"] = [{"group_id": "a", "count": 1}]
        self.rejected("budget_exceeded")

    def test_selected_group_count_ignores_larger_unselected_population(self):
        job = self.export(scope="selected_groups", ids=["a", "a"])
        self.assertEqual(job["planned_rows"], 3)
        self.assertEqual(job["rows_written"], 0)
        self.assertFalse(job["complete"])
        self.reserve.assert_called_once()

    def test_selected_comparison_counts_include_both_disjoint_periods(self):
        self.saved["spec"] = {"operation": "compare_periods", "periods": {
            "baseline": {"gte": "2025-01-01T00:00:00Z", "lt": "2025-02-01T00:00:00Z"},
            "current": {"gte": "2025-02-01T00:00:00Z", "lt": "2025-03-01T00:00:00Z"}}}
        self.saved["total"]["value"] = 6
        self.saved["all_rows"] = [{"group_id": "a", "count": 3, "current_count": 3, "baseline_count": 3}]
        self.rejected("budget_exceeded", scope="selected_groups", ids=["a"])

    def test_all_comparison_rows_rejected_when_each_period_would_fit(self):
        self.saved["spec"]["operation"] = "compare_periods"
        self.saved["total"]["value"] = 6
        self.rejected("budget_exceeded")

    def test_aggregate_count_uses_rows_instead_of_underlying_records(self):
        self.assertEqual(self.export(mode="aggregates")["planned_rows"], 2)

    def test_selected_aggregate_count_counts_each_distinct_group_once(self):
        self.assertEqual(self.export(mode="aggregates", scope="selected_groups", ids=["b", "b"])["planned_rows"], 1)

    def test_aggregate_over_budget_rejects_before_capacity_or_worker(self):
        self.service.budgets["max_export_rows"] = 1
        self.rejected("budget_exceeded", mode="aggregates")

    def test_zero_and_exact_limit_remain_admissible(self):
        for count in (0, 4):
            with self.subTest(count=count):
                self.saved["total"]["value"] = count
                self.saved["all_rows"] = []
                self.assertEqual(self.export()["planned_rows"], count)

    def test_inexact_or_invalid_total_cannot_start_an_export(self):
        for value in (None, {}, {"value": 3, "relation": "gte"}, {"value": -1, "relation": "eq"},
                      {"value": True, "relation": "eq"}, {"value": 1.5, "relation": "eq"}):
            with self.subTest(total=value):
                self.saved["total"] = value
                self.rejected("invalid_spec")

    def test_incomplete_result_cannot_start_an_export(self):
        self.saved["execution_complete"] = False
        self.rejected("invalid_spec")

    def test_invalid_selected_count_cannot_start_an_export(self):
        for value in (None, True, -1, "3", 6):
            with self.subTest(count=value):
                self.saved["all_rows"][0]["count"] = value
                self.rejected("invalid_spec", scope="selected_groups", ids=["a"])

    def test_inconsistent_comparison_counts_cannot_start_an_export(self):
        self.saved["spec"]["operation"] = "compare_periods"
        for row in ({"count": 3, "current_count": 2, "baseline_count": 0},
                    {"count": 3, "current_count": 3},
                    {"count": 3, "current_count": 3, "baseline_count": True}):
            with self.subTest(row=row):
                self.saved["all_rows"] = [{"group_id": "a", **row}]
                self.rejected("invalid_spec", scope="selected_groups", ids=["a"])


class SourceProjectionTests(unittest.TestCase):
    def test_elastic_projection_preserves_query_sort_and_pagination(self):
        second = page(2, hits=[hit(2)])
        second["hits"].pop("total")
        client = FakeClient([page(2, hits=[hit(1)]), second, page(2)])
        backend = ElasticBackend({"index": INDEX}, {}, MANIFEST, client=client)
        request = spec(filters={"field": "borough", "op": "eq", "value": "BROOKLYN"})
        original = copy.deepcopy(request)
        rows = list(backend.iter_records(request, source_fields=["unique_key"]))
        self.assertEqual(rows, [{"unique_key": "1"}, {"unique_key": "2"}])
        searches = [call[2] for call in client.calls if call[1].startswith("/_search")]
        self.assertTrue(all(body["_source"] == ["unique_key"] for body in searches))
        self.assertTrue(all(body["query"] == {"bool": {"filter": [{"term": {"borough": "BROOKLYN"}}]}} for body in searches))
        self.assertTrue(all(body["sort"] == [{"created_date": "asc"}, {"unique_key": "asc"}, {"_shard_doc": "asc"}] for body in searches))
        self.assertEqual(searches[1]["search_after"], [1, "1", 1])
        self.assertEqual(request, original)

    def test_invalid_projection_fails_before_any_elastic_request(self):
        for fields in ([], "unique_key", ["*"], ["unique_key", "unique_key"], [None], [{}]):
            with self.subTest(fields=fields):
                client = FakeClient([])
                backend = ElasticBackend({"index": INDEX}, {}, MANIFEST, client=client)
                with self.assertRaises(AnalyticsError) as caught:
                    list(backend.iter_records(spec(), source_fields=fields))
                self.assertEqual(caught.exception.code, "invalid_spec")
                self.assertEqual(client.calls, [])

    def test_reference_projection_happens_after_all_selection_predicates(self):
        backend = FixtureBackend({"fixture_path": str(asset_path("fixtures/requests.jsonl"))}, {}, {})
        request = {"filters": {"field": "borough", "op": "eq", "value": "BROOKLYN"},
                   "time": {"field": "created_date", "gte": "2025-12-01T00:00:00-05:00", "lt": "2026-01-01T00:00:00-05:00"},
                   "geo": {"type": "radius", "lat": 40.68, "lon": -73.95, "distance_m": 20000}}
        full = list(backend.iter_records(request))
        self.assertTrue(full)
        projected = list(backend.iter_records(request, source_fields=["unique_key", "descriptor"]))
        self.assertEqual(projected, [{key: row[key] for key in ("unique_key", "descriptor") if key in row} for row in full])

    def test_invalid_reference_projection_fails_before_source_open(self):
        backend = FixtureBackend({"fixture_path": "missing-fixture.jsonl"}, {}, {})
        with self.assertRaises(AnalyticsError) as caught:
            list(backend.iter_records({}, source_fields=["unknown"]))
        self.assertEqual(caught.exception.code, "invalid_spec")


if __name__ == "__main__":
    unittest.main()
