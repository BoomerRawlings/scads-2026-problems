"""Deterministic qualification-runner checks, never live Maps evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from analytics311.errors import AnalyticsError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("live_maps", ROOT / "tools/live_maps.py")
maps = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(maps)


def style(features):
    return {"sources": {"actual": {"type": "geojson", "data": {"type": "FeatureCollection", "features": features}}},
            "layers": [{"source": "actual", "paint": {"fill-color": ["get", maps.key("rate_change")]}}]}


def point(identifier):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-74, 40.7]},
            "properties": {"unique_key": identifier}}


class LiveMapsTests(unittest.TestCase):
    def test_points_map_uses_exact_view_no_implicit_time_or_bounds(self):
        payload = maps.map_object("requests", source_view="points-view")
        layer = json.loads(payload["attributes"]["layerListJSON"])[0]
        self.assertEqual(layer["type"], "GEOJSON_VECTOR")
        self.assertEqual(layer["sourceDescriptor"]["scalingType"], "LIMIT")
        self.assertFalse(layer["sourceDescriptor"]["filterByMapBounds"])
        self.assertFalse(layer["sourceDescriptor"]["applyGlobalTime"])
        self.assertTrue(layer["sourceDescriptor"]["applyGlobalQuery"])
        self.assertEqual(payload["references"], [{"id": "points-view", "name": "source_view", "type": "index-pattern"}])
        self.assertNotIn("EMS", json.dumps(payload))

    def test_trend_map_filters_join_not_polygons_and_styles_saved_metric(self):
        payload = maps.map_object("neighborhood_trends", source_view="boundary-view", result_view="result-view")
        layer = json.loads(payload["attributes"]["layerListJSON"])[0]
        self.assertFalse(layer["sourceDescriptor"]["applyGlobalQuery"])
        right = layer["joins"][0]["right"]
        self.assertTrue(right["applyGlobalQuery"])
        self.assertEqual(right["term"], "nta2020")
        self.assertEqual({m["field"] for m in right["metrics"]}, set(maps.METRIC_UNITS))
        self.assertEqual(layer["style"]["properties"]["fillColor"]["options"]["field"]["name"], maps.key("rate_change"))

    def test_rendered_point_source_requires_exact_unique_membership(self):
        expected = {"mapped_unique_keys": ["two", "one"]}
        self.assertEqual(maps.inspect_style(style([point("one"), point("two")]), "requests", expected)["rendered_points"], 2)
        for features in ([point("one")], [point("one"), point("one")], [point("one"), point("other")]):
            with self.subTest(features=features), self.assertRaises(AnalyticsError):
                maps.inspect_style(style(features), "requests", expected)

    def test_visible_layer_must_reference_inspected_geojson(self):
        value = style([point("one")])
        value["layers"][0]["source"] = "different"
        with self.assertRaises(AnalyticsError):
            maps.inspect_style(value, "requests", {"mapped_unique_keys": ["one"]})
        value["sources"]["actual"]["data"] = "http://not-inspected/source"
        with self.assertRaises(AnalyticsError):
            maps.inspect_style(value, "requests", {"mapped_unique_keys": ["one"]})

    def test_rendered_join_requires_same_keys_metrics_and_styled_field(self):
        metrics = {"baseline_count": 0, "current_count": 3, "absolute_change": 3,
                   "relative_change": None, "rate_change": 0.1}
        feature = {"geometry": {"type": "MultiPolygon", "coordinates": []},
                   "properties": {"nta2020": "BK0101", **{maps.key(k): v for k, v in metrics.items()}}}
        expected = {"groups": {"BK0101": metrics}}
        rendered = style([feature, {"properties": {"nta2020": "BK9999"}, "geometry": {"type": "Polygon"}}])
        self.assertEqual(maps.inspect_style(rendered, "neighborhood_trends", expected)["rendered_joined_groups"], 1)
        bad = copy.deepcopy(rendered)
        bad["sources"]["actual"]["data"]["features"][0]["properties"][maps.key("current_count")] = 4
        with self.assertRaises(AnalyticsError): maps.inspect_style(bad, "neighborhood_trends", expected)
        bad = copy.deepcopy(rendered)
        bad["layers"][0]["paint"] = {"fill-color": "#fff"}
        with self.assertRaises(AnalyticsError): maps.inspect_style(bad, "neighborhood_trends", expected)

    def test_nested_browser_request_filter_check_does_not_accept_other_filter(self):
        query = {"term": {"borough": "BROOKLYN"}}
        body = {"batch": [{"request": json.dumps({"query": {"bool": {"filter": [query]}}})}]}
        self.assertTrue(maps.contains_tree(body, query))
        self.assertFalse(maps.contains_tree(body, {"term": {"borough": "QUEENS"}}))

    def test_kibana_centroid_companions_are_checked_without_counting_as_polygons(self):
        metrics = {"baseline_count": 2, "current_count": 3, "absolute_change": 1,
                   "relative_change": 0.5, "rate_change": 0.1}
        polygon = {"id": "source-document", "geometry": {"type": "MultiPolygon", "coordinates": []},
                   "properties": {"nta2020": "BK0101", **{maps.key(k): v for k, v in metrics.items()}}}
        centroid = copy.deepcopy(polygon)
        centroid["geometry"] = {"type": "Point", "coordinates": [-74, 40.7]}
        centroid["properties"]["__kbn_is_centroid_feature__"] = True
        expected = {"groups": {"BK0101": metrics}}
        self.assertEqual(maps.inspect_style(style([centroid, polygon]), "neighborhood_trends", expected)["rendered_joined_groups"], 1)
        for change in ("id", "metric", "unflagged", "orphan", "duplicate", "polygon_flag", "duplicate_polygon"):
            bad = copy.deepcopy(centroid)
            features = [polygon, bad]
            if change == "id": bad["id"] = "another"
            elif change == "metric": bad["properties"][maps.key("current_count")] = 9
            elif change == "unflagged": bad["properties"].pop("__kbn_is_centroid_feature__")
            elif change == "orphan": features = [bad]
            elif change == "duplicate": features.append(copy.deepcopy(bad))
            elif change == "polygon_flag": bad["geometry"]["type"] = "Polygon"
            else: features.append(copy.deepcopy(polygon))
            with self.subTest(change=change), self.assertRaises(AnalyticsError):
                maps.inspect_style(style(features), "neighborhood_trends", expected)

    def test_csv_point_membership_includes_unmapped_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.csv"
            path.write_text("unique_key\none\ntwo\n", encoding="utf-8")
            expected = {"unique_keys": ["one", "two"], "mapped_unique_keys": ["one"], "source_count": 2}
            self.assertEqual(maps.inspect_csv(path, "requests", expected)["csv_rows"], 2)
            path.write_text("unique_key\none\n", encoding="utf-8")
            with self.assertRaises(AnalyticsError): maps.inspect_csv(path, "requests", expected)

    def test_csv_trend_metrics_and_nulls(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.csv"
            path.write_text("nta2020,baseline_count,current_count,absolute_change,relative_change,rate_change\nBK0101,0,3,3,,0.1\n", encoding="utf-8")
            expected = {"groups": {"BK0101": {"baseline_count": 0, "current_count": 3, "absolute_change": 3,
                                              "relative_change": None, "rate_change": 0.1}}}
            self.assertTrue(maps.inspect_csv(path, "neighborhood_trends", expected)["csv_membership_verified"])
            expected["groups"]["BK0101"]["relative_change"] = 0
            with self.assertRaises(AnalyticsError): maps.inspect_csv(path, "neighborhood_trends", expected)

    def test_boundary_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nta.geojson"
            feature = {"properties": {"nta2020": "BK0101", "ntaname": "Greenpoint", "ntatype": "0"},
                       "geometry": {"type": "Polygon", "coordinates": []}}
            path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}))
            docs, digest = maps.read_boundaries(path)
            self.assertEqual(docs[0]["nta2020"], "BK0101")
            self.assertEqual(len(digest), 64)
            path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature, feature]}))
            with self.assertRaises(AnalyticsError): maps.read_boundaries(path)

    def test_incorrect_stack_version_fails_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            config = temp / "config.json"
            config.write_text(json.dumps({"backend": "elastic", "kibana": {}}))
            boundaries = temp / "nta.json"
            boundaries.write_text(json.dumps({"type": "FeatureCollection", "features": [
                {"properties": {"nta2020": "BK0101"}, "geometry": {"type": "Polygon"}}]}))
            calls = []
            def request(method, path, body=None):
                calls.append((method, path))
                return {"version": {"number": "8.0.0"}}
            fake = SimpleNamespace(backend=SimpleNamespace(client=SimpleNamespace(request=request)),
                                   manifest={"geography": {"nta_version": maps.read_boundaries(boundaries)[1]}})
            with patch.object(maps, "AnalyticsService", return_value=fake), patch.object(maps, "KibanaClient"):
                result = maps.provision(config, boundaries, "nta-v1", temp / "new.json", temp / "receipt.json")
            self.assertFalse(result["passed"])
            self.assertFalse(result["rendered_parity_verified"])
            self.assertEqual(calls, [("GET", "/")])
            self.assertFalse((temp / "new.json").exists())

    def test_output_collision_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "old.json"
            path.write_text("original")
            with self.assertRaises(AnalyticsError): maps.new_path(path)
            self.assertEqual(path.read_text(), "original")

    def test_render_receipt_retains_safe_map_link_http_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expectation = root / "expected.json"
            expectation.write_text(json.dumps({"dataset_version": "test-v1", "reference": {"sha256": "a" * 64}}))
            failure = AnalyticsError("backend_unavailable", "Kibana returned HTTP 409; check configuration and privileges")
            failure.backend_details = {"http_status": 409, "method": "POST", "path": "/api/short_url"}
            def create(*args): raise failure
            service = SimpleNamespace(config={"backend": "elastic"}, manifest={"dataset_version": "test-v1"},
                                      create_map_link=create)
            with patch.object(maps, "AnalyticsService", return_value=service), patch.object(maps, "inspect_csv", return_value={}):
                result = maps.render(root / "profile.json", "a" * 32, "requests", expectation, root / "file.csv", root / "render")
            self.assertFalse(result["passed"])
            self.assertEqual(result["error"]["stage"], "map_link")
            self.assertEqual(result["error"]["backend"], failure.backend_details)
            self.assertEqual(result["error"]["reason"], failure.message)

    def test_kibana_redacted_or_wrong_version_never_mutates_indices(self):
        # The first body is the actual /api/status shape retained from the
        # real-corpus run. HTTP 200/available alone must never qualify a version.
        for status, error_code in (
            ({"status": {"overall": {"level": "available"}}}, "kibana_status_version_unavailable"),
            ({"version": {"number": "9.4.0"}}, "acceptance_failed"),
        ):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                config, boundaries = root / "config.json", root / "nta.json"
                config.write_text(json.dumps({"backend": "elastic", "index": "requests-v1",
                                              "kibana": {"result_index": "trends-v1"}}))
                boundaries.write_text(json.dumps({"type": "FeatureCollection", "features": [
                    {"properties": {"nta2020": "BK0101"}, "geometry": {"type": "Polygon"}}]}))
                calls = []
                def request(method, path, body=None):
                    calls.append((method, path))
                    return {"version": {"number": maps.VERSION}}
                service = SimpleNamespace(backend=SimpleNamespace(client=SimpleNamespace(request=request)),
                                          manifest={"geography": {"nta_version": maps.read_boundaries(boundaries)[1]}})
                with patch.object(maps, "AnalyticsService", return_value=service), patch.object(maps, "KibanaClient") as client:
                    client.return_value.request.return_value = status
                    result = maps.provision(config, boundaries, "nta-v1", root / "new.json", root / "receipt.json")
                    client.return_value.request.assert_called_once_with("/api/status", method="GET")
                self.assertFalse(result["passed"])
                self.assertEqual(result["error"]["stage"], "version")
                self.assertEqual(result["error"]["code"], error_code)
                self.assertEqual(calls, [("GET", "/")])
                self.assertFalse((root / "new.json").exists())
                if error_code == "kibana_status_version_unavailable":
                    self.assertIsNone(result["checks"]["kibana_status_version"])
                    self.assertIn("monitor privilege", result["error"]["reason"])

    def test_exact_full_kibana_version_allows_provisioning_to_begin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, boundaries = root / "config.json", root / "nta.json"
            config.write_text(json.dumps({"backend": "elastic", "index": "requests-v1",
                                          "kibana": {"result_index": "trends-v1"}}))
            boundaries.write_text(json.dumps({"type": "FeatureCollection", "features": [
                {"properties": {"nta2020": "BK0101"}, "geometry": {"type": "Polygon"}}]}))
            calls = []
            def request(method, path, body=None):
                calls.append((method, path))
                if method == "GET" and path == "/":
                    return {"version": {"number": maps.VERSION}}
                raise AnalyticsError("test_boundary_stop", "Stop unit test before indexing.")
            service = SimpleNamespace(backend=SimpleNamespace(client=SimpleNamespace(request=request)),
                                      manifest={"geography": {"nta_version": maps.read_boundaries(boundaries)[1]}})
            with patch.object(maps, "AnalyticsService", return_value=service), patch.object(maps, "KibanaClient") as client:
                client.return_value.request.return_value = {"version": {"number": maps.VERSION},
                                                           "status": {"overall": {"level": "available"}}}
                result = maps.provision(config, boundaries, "nta-v1", root / "new.json", root / "receipt.json")
            self.assertEqual(result["error"], {"stage": "boundary_index", "code": "test_boundary_stop"})
            self.assertEqual(result["checks"]["stack_version"], maps.VERSION)
            self.assertEqual(result["checks"]["kibana_status_version"], maps.VERSION)
            self.assertEqual(calls, [("GET", "/"), ("PUT", "/nta-v1")])


if __name__ == "__main__":
    unittest.main()
