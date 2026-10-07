"""Reference scan resource boundaries and exact date/geometry/statistic answers."""
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analytics311.errors import AnalyticsError
from analytics311.fixture import FixtureBackend, MAX_LINE_BYTES, _inside_polygon, _percentile


class FixtureOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "records.jsonl"
        self.backend = FixtureBackend({"fixture_path": str(self.path)}, {}, {})

    def write(self, rows):
        self.path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def ids(self, **spec):
        return [row["unique_key"] for row in self.backend.iter_records(spec)]

    def test_date_operands_and_boolean_short_circuit_preserve_instant_semantics(self):
        self.write([
            {"unique_key": "a", "created_date": "2025-11-02T01:30:00-04:00"},
            {"unique_key": "b", "created_date": "2025-11-02T01:30:00-05:00"},
            {"unique_key": "c"},
        ])
        filters = {"any": [
            {"field": "created_date", "op": "in", "value": ["2025-11-02T05:30:00Z"]},
            {"field": "created_date", "op": "range", "value": {"gt": "2025-11-02T06:29:59Z", "lte": "2025-11-02T06:30:00Z"}},
        ]}
        self.assertEqual(self.ids(filters=filters), ["a", "b"])
        filters = {"all": [{"field": "created_date", "op": "exists", "value": True},
                           {"not": {"field": "created_date", "op": "eq", "value": "2025-11-02T05:30:00Z"}}]}
        self.assertEqual(self.ids(filters=filters), ["b"])

    def test_new_scan_observes_changed_source_and_mutated_filter(self):
        self.write([{"unique_key": "a", "borough": "BROOKLYN"}, {"unique_key": "b", "borough": "QUEENS"}])
        spec = {"filters": {"field": "borough", "op": "in", "value": ["BROOKLYN"]}}
        self.assertEqual(self.ids(**spec), ["a"])
        spec["filters"]["value"][:] = ["QUEENS"]
        self.assertEqual(self.ids(**spec), ["b"])
        self.write([{"unique_key": "new", "borough": "QUEENS"}])
        self.assertEqual(self.ids(**spec), ["new"])

    def test_polygon_edges_vertices_and_dateline_are_preserved(self):
        points = [{"lat": -1, "lon": 179}, {"lat": 1, "lon": 179},
                  {"lat": 1, "lon": -179}, {"lat": -1, "lon": -179}]
        self.write([{"unique_key": key, "location": {"lat": lat, "lon": lon}}
                    for key, lat, lon in [("west", 0, 179.5), ("east", 0, -179.5),
                                         ("vertex", 1, 179), ("edge", 1, 180),
                                         ("outside", 0, 0), ("north", 2, 180)]])
        self.assertEqual(self.ids(geo={"type": "polygon", "points": points}), ["west", "east", "vertex", "edge"])
        self.assertTrue(_inside_polygon(0, -180, points))
        self.assertFalse(_inside_polygon(0, 178.9, points))

    def test_all_duration_metrics_keep_exact_anchors_and_missing_denominator(self):
        durations = [1e16, 1.0, 2.0, 3.0, 4.0]
        self.write([{"is_closed": True, "closure_hours": value} for value in durations]
                   + [{"is_closed": True}, {"is_closed": False, "closure_hours": 200},
                      {"is_closed": True, "closure_hours": -1}])
        result = self.backend.execute({"operation": "aggregate", "metrics": [
            "count", "closed_count", "open_count", "mean_closure_hours", "median_closure_hours", "p90_closure_hours"]})
        row = result["rows"][0]
        self.assertEqual(row["count"], 8)
        self.assertEqual(row["closed_count"], 7)
        self.assertEqual(row["open_count"], 1)
        self.assertEqual(row["mean_closure_hours"], math.fsum(durations) / 5)
        self.assertEqual(row["median_closure_hours"], 3)
        self.assertEqual(row["p90_closure_hours"], 4 + (1e16 - 4) * 0.6000000000000001)
        self.assertEqual(_percentile(durations, .5), 3)
        self.assertEqual(durations, [1e16, 1.0, 2.0, 3.0, 4.0])

    def test_count_only_does_not_depend_on_duration_quality(self):
        self.write([{"is_closed": True, "closure_hours": "invalid"}, {"is_closed": False}])
        self.assertEqual(self.backend.execute({"operation": "aggregate", "metrics": ["count"]})["rows"],
                         [{"group": {}, "count": 2}])

    def test_oversized_line_rejected_before_json_decoding(self):
        with self.path.open("wb") as stream:
            stream.write(b" " * (MAX_LINE_BYTES + 1))
        with patch("analytics311.fixture.json.loads", side_effect=AssertionError("Oversized input reached parser")):
            with self.assertRaises(AnalyticsError) as caught:
                list(self.backend.iter_records({}))
        self.assertEqual(caught.exception.code, "budget_exceeded")

    def test_blank_lines_consume_deadline_budget(self):
        self.path.write_bytes(b"\n\n\n{}\n")
        self.backend.deadline_seconds = 1
        with patch("analytics311.fixture.time.monotonic", side_effect=[0, .1, .2, 1.1]):
            with self.assertRaises(AnalyticsError) as caught:
                list(self.backend.iter_records({}))
        self.assertEqual(caught.exception.code, "budget_exceeded")

    def test_export_deadline_overrides_short_analysis_deadline(self):
        self.write([{"unique_key": "a"}, {"unique_key": "b"}])
        self.backend.deadline_seconds = .1
        with patch("analytics311.fixture.time.monotonic", side_effect=[1, 2, 3]):
            rows = list(self.backend.iter_records({}, deadline=4))
        self.assertEqual([row["unique_key"] for row in rows], ["a", "b"])
        with patch("analytics311.fixture.time.monotonic", return_value=5):
            with self.assertRaises(AnalyticsError) as caught:
                list(self.backend.iter_records({}, deadline=4))
        self.assertEqual(caught.exception.code, "budget_exceeded")

    def test_non_object_and_deep_json_fail_with_stable_error(self):
        for value in (b"[]\n", b"null\n", b"42\n", b"[" * 1500 + b"]" * 1500 + b"\n"):
            with self.subTest(value=value[:10]):
                self.path.write_bytes(value)
                with self.assertRaises(AnalyticsError) as caught:
                    list(self.backend.iter_records({}))
                self.assertEqual(caught.exception.code, "backend_unavailable")

    def test_execute_uses_supplied_deadline_for_scan_and_postprocessing(self):
        self.write([{"unique_key": "a"}])
        self.backend.deadline_seconds = .01
        for operation in ("records", "aggregate"):
            with self.subTest(operation=operation):
                with patch("analytics311.fixture.time.monotonic", return_value=5):
                    self.assertEqual(self.backend.execute({"operation": operation}, deadline=6)["total"], 1)
                with patch("analytics311.fixture.time.monotonic", side_effect=[4, 5, 7]):
                    with self.assertRaises(AnalyticsError) as caught:
                        self.backend.execute({"operation": operation}, deadline=6)
                self.assertEqual(caught.exception.code, "budget_exceeded")

    def test_aggregate_rejects_result_when_statistical_calculation_exhausts_deadline(self):
        self.write([{"is_closed": True, "closure_hours": 2}])
        # Scan + pre-group check pass; the final deadline check rejects an expired computation.
        with patch("analytics311.fixture.time.monotonic", side_effect=[1, 2, 3, 7]):
            with self.assertRaises(AnalyticsError) as caught:
                self.backend.execute({"operation": "aggregate", "metrics": ["mean_closure_hours"]}, deadline=6)
        self.assertEqual(caught.exception.code, "budget_exceeded")


if __name__ == "__main__":
    unittest.main()
