import copy
import json
from pathlib import Path
import unittest

from analytics311.compiler import compile_query, compile_search
from analytics311.contracts import FIELDS, normalize_spec
from analytics311.errors import AnalyticsError


CATALOG = json.loads((Path(__file__).resolve().parents[1] / "config" / "catalog.json").read_text())


class ContractTests(unittest.TestCase):
    def spec(self, **changes):
        return {"schema_version": "1", "dataset_version": "fixture-v1", "operation": "records",
                "as_of": "2025-04-15T12:00:00-04:00", **changes}

    def normalized(self, **changes):
        return normalize_spec(self.spec(**changes), CATALOG)

    def rejected(self, spec, code="invalid_spec", limits=None):
        with self.assertRaises(AnalyticsError) as raised:
            normalize_spec(spec, CATALOG, limits)
        self.assertEqual(code, raised.exception.code)

    def test_normalization_is_detached_and_idempotent(self):
        original = self.spec(filters={"field": "borough", "op": "in", "value": ["BROOKLYN", "BROOKLYN"]})
        snapshot = copy.deepcopy(original)
        result = normalize_spec(original, CATALOG)
        self.assertEqual(snapshot, original)
        self.assertEqual(["BROOKLYN"], result["filters"]["value"])
        self.assertEqual(result, normalize_spec(result, CATALOG))
        self.assertEqual("2025-04-15T16:00:00+00:00", result["as_of"])

    def test_record_default_compiles_bounded_preview_with_exact_total(self):
        normalized = self.normalized()
        body = compile_search(normalized)
        self.assertEqual(normalized["preview_limit"], 5)
        self.assertEqual(body["size"], 5)
        self.assertIs(body["track_total_hits"], True)
        self.assertEqual(compile_search(self.normalized(preview_limit=100))["size"], 100)

    def test_last_month_resolves_calendar_across_dst(self):
        result = self.normalized(time={"preset": "last_month"})
        self.assertEqual({"field": "created_date", "gte": "2025-03-01T05:00:00+00:00",
                          "lt": "2025-04-01T04:00:00+00:00"}, result["time"])

    def test_last_month_uses_local_anchor_day_and_leap_year(self):
        result = self.normalized(as_of="2024-04-01T03:59:59Z", time={"preset": "last_month"})
        self.assertEqual("2024-02-01T05:00:00+00:00", result["time"]["gte"])
        self.assertEqual("2024-03-01T05:00:00+00:00", result["time"]["lt"])

    def test_last_month_year_boundary(self):
        result = self.normalized(as_of="2025-01-10T00:00:00Z", time={"preset": "last_month"})
        self.assertEqual("2024-12-01T05:00:00+00:00", result["time"]["gte"])

    def test_dates_require_explicit_offset(self):
        for value in ("2025-01-01", "2025-01-01T10:00:00", "today", None, 0):
            with self.subTest(value=value):
                self.rejected(self.spec(as_of=value))

    def test_unknown_and_malformed_keys(self):
        for update in ({"query": {"script": "x"}}, {"schema_version": "2"}, {"operation": []},
                       {"timezone": "Moon/Base"}, {"dataset_version": ""}, {"metrics": []},
                       {"filters": {"field": "status", "op": "eq", "value": "Open", "script": "x"}}):
            with self.subTest(update=update):
                self.rejected(self.spec(**update))

    def test_nonfinite_and_boolean_numbers_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf"), True, 10 ** 1000):
            with self.subTest(value=str(value)[:20]):
                self.rejected(self.spec(filters={"field": "closure_hours", "op": "eq", "value": value}))

    def test_type_and_operator_allowlists(self):
        cases = [("borough", "regex", ".*"), ("unknown", "eq", "x"), ("status", "eq", 42),
                 ("is_closed", "eq", "true"), ("is_closed", "exists", 1), ("borough", "in", []),
                 ("status", "range", {"gte": "a"}), ("closure_hours", "range", {}),
                 ("closure_hours", "range", {"gte": 1, "gt": 2}),
                 ("closure_hours", "range", {"gt": 2, "lte": 2})]
        for field, op, value in cases:
            with self.subTest(field=field, op=op, value=value):
                self.rejected(self.spec(filters={"field": field, "op": op, "value": value}))

    def test_filter_budgets(self):
        leaf = {"field": "borough", "op": "eq", "value": "BROOKLYN"}
        self.rejected(self.spec(filters={"not": {"not": leaf}}), "budget_exceeded", {"max_filter_depth": 1})
        self.rejected(self.spec(filters={"all": [leaf, leaf]}), "budget_exceeded", {"max_filter_nodes": 2})
        self.rejected(self.spec(filters={"field": "borough", "op": "in", "value": ["A", "B"]}),
                      "budget_exceeded", {"max_filter_values": 1})

    def test_filter_boolean_structure(self):
        for value in ({"any": []}, {"not": []}, {"all": [], "any": []}, {}):
            with self.subTest(value=value):
                self.rejected(self.spec(filters=value))

    def test_family_expansion_is_exact_and_unknown_requires_clarification(self):
        result = self.normalized(filters={"category_family": "noise"})
        self.assertEqual({"field": "complaint_type", "op": "in", "value": CATALOG["families"]["noise"]}, result["filters"])
        self.rejected(self.spec(filters={"category_family": "noisy-ish"}), "needs_clarification")

    def test_time_bounds_and_presets(self):
        self.rejected(self.spec(time={"gte": "2025-02-01T00:00:00Z", "lt": "2025-01-01T00:00:00Z"}))
        self.rejected(self.spec(time={"preset": "last_month", "gte": "2025-01-01T00:00:00Z"}))
        self.rejected(self.spec(time={"preset": "latest_available"}), "unsupported_operation")
        self.rejected(self.spec(as_of="0001-01-01T00:00:00Z", time={"preset": "last_month"}))

    def test_radius_and_bbox_validation(self):
        self.rejected(self.spec(geo={"type": "radius", "lat": 91, "lon": -74, "distance_m": 1000}))
        self.rejected(self.spec(geo={"type": "radius", "lat": 40, "lon": -74, "distance_m": -1}))
        self.rejected(self.spec(geo={"type": "bbox", "top_left": {"lat": 40, "lon": -74},
                                    "bottom_right": {"lat": 41, "lon": -73}}))

    def test_polygon_closes_and_rejects_self_intersection(self):
        triangle = [{"lat": 40, "lon": -74}, {"lat": 41, "lon": -74}, {"lat": 40, "lon": -73}]
        geo = self.normalized(geo={"type": "polygon", "points": triangle})["geo"]
        self.assertEqual(triangle + triangle[:1], geo["points"])
        normalized = normalize_spec(self.spec(geo={"type": "polygon", "points": triangle}), CATALOG,
                                    {"max_polygon_points": 3})
        self.assertEqual(normalized, normalize_spec(normalized, CATALOG, {"max_polygon_points": 3}))
        bowtie = [{"lat": 40, "lon": -74}, {"lat": 41, "lon": -73},
                  {"lat": 41, "lon": -74}, {"lat": 40, "lon": -73}]
        self.rejected(self.spec(geo={"type": "polygon", "points": bowtie}))
        self.rejected(self.spec(geo={"type": "polygon", "points": triangle[:2]}))

    def test_grouping_validation_and_mixed_dimensions(self):
        groups = [{"field": "borough"}, {"field": "created_date", "interval": "week"}]
        self.assertEqual(groups, self.normalized(operation="aggregate", group_by=groups,
                                                time={"preset": "last_month"})["group_by"])
        self.rejected(self.spec(operation="aggregate", group_by=groups), "unsupported_operation")
        self.rejected(self.spec(operation="aggregate", group_by=[{"field": "borough"}, {"field": "borough"}]))
        self.rejected(self.spec(group_by=[{"field": "borough"}]), "unsupported_operation")

    def test_bounded_options(self):
        for update in ({"preview_limit": 101}, {"preview_limit": True}, {"top_n": 0},
                       {"rank_by": "random"}, {"rank_order": "up"}):
            with self.subTest(update=update):
                self.rejected(self.spec(**update))

    def test_minimum_count_defaults_and_boundaries(self):
        periods = {"baseline": {"gte": "2025-01-01T00:00:00Z", "lt": "2025-02-01T00:00:00Z"},
                   "current": {"gte": "2025-02-01T00:00:00Z", "lt": "2025-03-01T00:00:00Z"}}
        for operation in ("aggregate", "compare_periods"):
            arguments = {"operation": operation}
            if operation == "compare_periods":
                arguments["periods"] = periods
            with self.subTest(operation=operation):
                self.assertEqual(0, self.normalized(**arguments)["minimum_count"])
                for threshold in (0, 1, 1_000_000):
                    result = self.normalized(**arguments, minimum_count=threshold)
                    self.assertEqual(threshold, result["minimum_count"])
                    self.assertEqual(result, normalize_spec(result, CATALOG))
        self.assertNotIn("minimum_count", self.normalized())

    def test_minimum_count_rejects_records_and_invalid_thresholds(self):
        self.rejected(self.spec(minimum_count=0), "unsupported_operation")
        for threshold in (-1, 1_000_001, True, 1.0, "1", None, float("nan")):
            with self.subTest(threshold=threshold):
                self.rejected(self.spec(operation="aggregate", minimum_count=threshold))

    def test_compare_periods(self):
        periods = {"baseline": {"gte": "2025-01-01T00:00:00Z", "lt": "2025-02-01T00:00:00Z"},
                   "current": {"gte": "2025-02-01T00:00:00Z", "lt": "2025-03-01T00:00:00Z"}}
        result = self.normalized(operation="compare_periods", periods=periods, group_by=[{"field": "nta2020"}])
        self.assertEqual("absolute_change", result["rank_by"])
        self.rejected(self.spec(operation="compare_periods", periods=periods, time={"preset": "last_month"}),
                      "unsupported_operation")
        periods["current"]["gte"] = "2025-01-31T23:59:59.999999Z"
        self.rejected(self.spec(operation="compare_periods", periods=periods))


class CompilerTests(unittest.TestCase):
    spec = ContractTests.spec
    normalized = ContractTests.normalized

    def test_record_query_uses_exact_filters_and_stable_sort(self):
        spec = self.normalized(time={"preset": "last_month"}, filters={"all": [
            {"field": "borough", "op": "eq", "value": "BROOKLYN"}, {"category_family": "noise"}]})
        body = compile_search(spec)
        self.assertEqual(5, body["size"])
        self.assertTrue(body["track_total_hits"])
        self.assertEqual(set(FIELDS), set(body["_source"]))
        self.assertEqual([{"created_date": {"order": "asc", "missing": "_last"}}, {"unique_key": "asc"}], body["sort"])
        self.assertEqual({"term": {"borough": "BROOKLYN"}}, body["query"]["bool"]["filter"][1]["bool"]["filter"][0])

    def test_boolean_not_and_missing(self):
        spec = self.normalized(filters={"any": [
            {"field": "location", "op": "exists", "value": False},
            {"not": {"field": "status", "op": "eq", "value": "Closed"}}]})
        boolean = compile_query(spec)["bool"]["filter"][0]["bool"]
        self.assertEqual(1, boolean["minimum_should_match"])
        self.assertEqual({"bool": {"must_not": [{"exists": {"field": "location"}}]}}, boolean["should"][0])

    def test_geo_compiler(self):
        body = compile_query(self.normalized(geo={"type": "radius", "lat": 40.7, "lon": -74, "distance_m": 1000}))
        self.assertEqual({"geo_distance": {"distance": "1000m", "location": {"lat": 40.7, "lon": -74}}}, body["bool"]["filter"][0])
        box = {"type": "bbox", "top_left": {"lat": 41, "lon": -74}, "bottom_right": {"lat": 40, "lon": -73}}
        self.assertIn("geo_bounding_box", compile_query(self.normalized(geo=box))["bool"]["filter"][0])

    def test_composite_pages_never_apply_top_n(self):
        spec = self.normalized(operation="aggregate", group_by=[{"field": "borough"}, {"field": "agency"}], top_n=2,
                               metrics=["count", "closed_count", "open_count", "mean_closure_hours", "median_closure_hours", "p90_closure_hours"])
        body = compile_search(spec, after_key={"borough": "BRONX", "agency": "NYPD"}, page_size=500)
        composite = body["aggs"]["groups"]["composite"]
        self.assertEqual(500, composite["size"])
        self.assertEqual({"borough": "BRONX", "agency": "NYPD"}, composite["after"])
        self.assertTrue(composite["sources"][0]["borough"]["terms"]["missing_bucket"])
        self.assertEqual([50], body["aggs"]["groups"]["aggs"]["median_closure_hours"]["percentiles"]["percents"])
        self.assertEqual({"filter": {"term": {"is_closed": False}}}, body["aggs"]["groups"]["aggs"]["open_count"])

    def test_date_source_uses_calendar_and_timezone(self):
        spec = self.normalized(operation="aggregate", time={"preset": "last_month"},
                               group_by=[{"field": "created_date", "interval": "day"}])
        source = compile_search(spec)["aggs"]["groups"]["composite"]["sources"][0]["created_date"]["date_histogram"]
        self.assertEqual("day", source["calendar_interval"])
        self.assertEqual("America/New_York", source["time_zone"])
        self.assertEqual("strict_date_time", source["format"])

    def test_unbucketed_count_uses_exact_total(self):
        body = compile_search(self.normalized(operation="aggregate"))
        self.assertEqual({"query": {"match_all": {}}, "track_total_hits": True, "size": 0}, body)

    def test_comparison_selection_union_excludes_gap(self):
        periods = {"baseline": {"gte": "2025-01-01T00:00:00Z", "lt": "2025-02-01T00:00:00Z"},
                   "current": {"gte": "2025-03-01T00:00:00Z", "lt": "2025-04-01T00:00:00Z"}}
        spec = self.normalized(operation="compare_periods", periods=periods)
        union = compile_query(spec)["bool"]["filter"][0]["bool"]
        self.assertEqual(2, len(union["should"]))
        self.assertEqual(1, union["minimum_should_match"])
        with self.assertRaises(AnalyticsError):
            compile_search(spec)

    def test_record_cursor_passes_through(self):
        body = compile_search(self.normalized(), after_key=["2025-03-01T00:00:00Z", "001"])
        self.assertEqual(["2025-03-01T00:00:00Z", "001"], body["search_after"])


if __name__ == "__main__":
    unittest.main()
