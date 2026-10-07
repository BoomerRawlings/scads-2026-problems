"""Hand-authored expected answers, independent of the DSL compiler."""

import json
from pathlib import Path
import tempfile
import unittest

from analytics311.errors import AnalyticsError
from analytics311.fixture import FixtureBackend


ROOT = Path(__file__).resolve().parents[1]


def request(**updates):
    spec = {
        "operation": "records", "timezone": "America/New_York", "preview_limit": 100,
        "time": {"field": "created_date", "gte": "2025-11-01T00:00:00-04:00", "lt": "2026-01-01T00:00:00-05:00"},
    }
    spec.update(updates)
    return spec


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.config = {"fixture_path": str(ROOT / "fixtures" / "requests.jsonl")}
        self.backend = FixtureBackend(self.config, {}, {})

    def ids(self, spec):
        return {row["unique_key"] for row in self.backend.iter_records(spec)}

    def test_authored_fixture_totals_and_null_bucket(self):
        result = self.backend.execute(request(operation="aggregate", group_by=[{"field": "borough"}]))
        self.assertEqual(result["total"], 32)
        self.assertFalse(result["approximate"])
        self.assertEqual({row["group"]["borough"]: row["count"] for row in result["rows"]},
                         {"BROOKLYN": 14, "MANHATTAN": 6, "QUEENS": 6, "BRONX": 3, "STATEN ISLAND": 2, None: 1})

    def test_preview_does_not_change_full_cohort(self):
        spec = request(preview_limit=2, time={"field": "created_date", "gte": "2025-12-01T00:00:00-05:00", "lt": "2026-01-01T00:00:00-05:00"},
                       filters={"all": [{"field": "borough", "op": "eq", "value": "BROOKLYN"},
                                         {"field": "complaint_type", "op": "in", "value": ["Noise - Residential", "Noise - Street/Sidewalk", "Noise - Commercial"]}]})
        result = self.backend.execute(spec)
        self.assertEqual(result["total"], 4)
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(self.ids(spec), {"FIX-021", "FIX-022", "FIX-023", "FIX-032"})

    def test_metrics_exclude_missing_duration_without_losing_closed_count(self):
        spec = request(operation="aggregate", filters={"field": "borough", "op": "eq", "value": "BROOKLYN"},
                       metrics=["count", "closed_count", "open_count", "mean_closure_hours", "median_closure_hours", "p90_closure_hours"])
        row = self.backend.execute(spec)["rows"][0]
        self.assertEqual(row, {"group": {}, "count": 14, "closed_count": 11, "open_count": 3,
                               "mean_closure_hours": 17.4, "median_closure_hours": 10.0, "p90_closure_hours": 48.0})

    def test_boolean_tree_numeric_range_and_missing(self):
        spec = request(filters={"all": [
            {"any": [{"field": "borough", "op": "eq", "value": "BROOKLYN"}, {"field": "borough", "op": "eq", "value": "QUEENS"}]},
            {"not": {"field": "complaint_type", "op": "eq", "value": "Rodent"}},
            {"field": "closure_hours", "op": "range", "value": {"gte": 4, "lt": 10}},
        ]})
        self.assertEqual(self.ids(spec), {"FIX-011", "FIX-015", "FIX-023", "FIX-028"})
        self.assertEqual(self.ids(request(filters={"field": "location", "op": "exists", "value": False})), {"FIX-014", "FIX-031"})

    def test_date_equality_and_ranges_compare_instants(self):
        self.assertEqual(self.ids(request(filters={"field": "created_date", "op": "eq", "value": "2025-11-02T05:30:00+00:00"})), {"FIX-015"})
        self.assertEqual(self.ids(request(filters={"field": "created_date", "op": "in", "value": ["2025-11-02T06:30:00+00:00"]})), {"FIX-016"})
        spec = request(filters={"field": "created_date", "op": "range", "value": {"gte": "2025-11-02T05:30:00Z", "lt": "2025-11-02T06:30:00Z"}})
        self.assertEqual(self.ids(spec), {"FIX-015"})

    def test_dst_histogram_midnight_and_sparse_groups(self):
        spec = request(operation="aggregate", time={"field": "created_date", "gte": "2025-11-02T00:00:00-04:00", "lt": "2025-11-04T00:00:00-05:00"},
                       group_by=[{"field": "created_date", "interval": "day"}])
        counts = {row["group"]["created_date"]: row["count"] for row in self.backend.execute(spec)["rows"]}
        self.assertEqual(counts, {"2025-11-02T00:00:00-04:00": 2, "2025-11-03T00:00:00-05:00": 1})
        spec["group_by"] = [{"field": "created_date", "interval": "week"}, {"field": "borough"}]
        pairs = {(row["group"]["created_date"], row["group"]["borough"]): row["count"] for row in self.backend.execute(spec)["rows"]}
        self.assertEqual(pairs, {("2025-10-27T00:00:00-04:00", "QUEENS"): 1,
                                ("2025-10-27T00:00:00-04:00", "BRONX"): 1,
                                ("2025-11-03T00:00:00-05:00", "MANHATTAN"): 1})

    def test_monthly_authored_counts(self):
        result = self.backend.execute(request(operation="aggregate", group_by=[{"field": "created_date", "interval": "month"}]))
        self.assertEqual({row["group"]["created_date"]: row["count"] for row in result["rows"]},
                         {"2025-11-01T00:00:00-04:00": 16, "2025-12-01T00:00:00-05:00": 16})

    def test_geographic_cohorts_and_polygon_boundaries(self):
        spec = request(geo={"type": "radius", "lat": 40.68, "lon": -73.95, "distance_m": 1500},
                       filters={"field": "complaint_type", "op": "eq", "value": "Rodent"})
        self.assertEqual(self.ids(spec), {"FIX-001", "FIX-002", "FIX-017", "FIX-018"})
        box = {"type": "bbox", "top_left": {"lat": 40.70, "lon": -73.95}, "bottom_right": {"lat": 40.68, "lon": -73.94}}
        expected = {f"FIX-{i:03}" for i in [1, 2, 3, 4, 11, 13, 17, 18, 19, 20, 21, 22, 23, 32]}
        self.assertEqual(self.ids(request(geo=box)), expected)
        polygon = {"type": "polygon", "points": [{"lat": 40.68, "lon": -73.95}, {"lat": 40.70, "lon": -73.95},
                                                   {"lat": 40.70, "lon": -73.94}, {"lat": 40.68, "lon": -73.94}, {"lat": 40.68, "lon": -73.95}]}
        self.assertEqual(self.ids(request(geo=polygon)), expected)

    def test_period_export_union_excludes_gap(self):
        spec = request(periods={"baseline": {"gte": "2025-11-01T00:00:00-04:00", "lt": "2025-11-04T00:00:00-05:00"},
                                "current": {"gte": "2025-12-01T00:00:00-05:00", "lt": "2025-12-04T00:00:00-05:00"}})
        spec.pop("time")
        self.assertEqual(self.ids(spec), {"FIX-001", "FIX-005", "FIX-015", "FIX-016", "FIX-017", "FIX-021"})

    def test_empty_aggregate_has_zero_count_and_null_durations(self):
        row = self.backend.execute(request(operation="aggregate", filters={"field": "unique_key", "op": "eq", "value": "absent"},
                                          metrics=["count", "mean_closure_hours", "median_closure_hours", "p90_closure_hours"]))["rows"][0]
        self.assertEqual(row, {"group": {}, "count": 0, "mean_closure_hours": None, "median_closure_hours": None, "p90_closure_hours": None})

    def test_scan_limit_counts_nonmatches(self):
        backend = FixtureBackend({**self.config, "budgets": {"max_fixture_rows": 2}}, {}, {})
        with self.assertRaises(AnalyticsError) as caught:
            backend.execute(request(filters={"field": "unique_key", "op": "eq", "value": "absent"}))
        self.assertEqual(caught.exception.code, "budget_exceeded")

    def test_group_limit_never_returns_silently_truncated_groups(self):
        backend = FixtureBackend({**self.config, "budgets": {"max_groups": 2}}, {}, {})
        with self.assertRaises(AnalyticsError) as caught:
            backend.execute(request(operation="aggregate", group_by=[{"field": "borough"}]))
        self.assertEqual(caught.exception.code, "budget_exceeded")

    def test_malformed_fixture_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.jsonl"
            path.write_text('{bad json}\n', encoding="utf-8")
            backend = FixtureBackend({"fixture_path": str(path)}, {}, {})
            with self.assertRaises(AnalyticsError) as caught:
                backend.execute(request())
            self.assertEqual(caught.exception.code, "backend_unavailable")

    def test_example_requests_validate(self):
        from analytics311.contracts import normalize_spec
        catalog = json.loads((ROOT / "config" / "catalog.json").read_text(encoding="utf-8"))
        for path in (ROOT / "examples").glob("*.json"):
            with self.subTest(path=path.name):
                normalize_spec(json.loads(path.read_text(encoding="utf-8")), catalog)


if __name__ == "__main__":
    unittest.main()
