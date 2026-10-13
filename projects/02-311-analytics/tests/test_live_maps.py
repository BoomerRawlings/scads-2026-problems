"""Deterministic qualification-runner checks, never live Maps evidence."""
import copy
import importlib.util
from html import escape
from html.parser import HTMLParser
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

    def test_live_point_metadata_requires_verified_index_ids_and_consistent_source_key(self):
        feature = point("one")
        feature["properties"] = {"_id": "one", "_index": "requests-v1"}
        expected = {"mapped_unique_keys": ["one"]}
        self.assertEqual(maps.inspect_style(style([feature]), "requests", expected,
                                           source_index="requests-v1")["rendered_points"], 1)
        # Raw document IDs are never a fallback without a verified index.
        with self.assertRaises(AnalyticsError): maps.inspect_style(style([feature]), "requests", expected)
        for properties in ({"_id": "one", "_index": "other-v1"}, {"_id": "other", "_index": "requests-v1"},
                           {"_id": 1, "_index": "requests-v1"}, {"unique_key": "one"},
                           {"_id": "one", "_index": "requests-v1", "unique_key": "different"}):
            bad = dict(feature, properties=properties)
            with self.subTest(properties=properties), self.assertRaises(AnalyticsError):
                maps.inspect_style(style([bad]), "requests", expected, source_index="requests-v1")

    def test_live_point_id_binding_checks_actual_source_not_only_ingestion_convention(self):
        expected = {"mapped_unique_keys": ["one", "two"]}
        rows = [{"_id": value, "_index": "requests-v1", "_source": {"unique_key": value}} for value in ("one", "two")]
        response = {"timed_out": False, "_shards": {"failed": 0},
                    "hits": {"total": {"value": 2, "relation": "eq"}, "hits": rows}}
        client = unittest.mock.Mock()
        client.request.return_value = response
        service = SimpleNamespace(config={"index": "requests-v1"}, backend=SimpleNamespace(client=client))
        self.assertTrue(maps.verify_point_id_binding(service, expected)["point_document_id_binding_verified"])
        client.request.assert_called_once_with("POST", "/requests-v1/_search", {
            "size": 2, "track_total_hits": True, "_source": ["unique_key"], "query": {"ids": {"values": ["one", "two"]}}})
        for change in ("source", "index", "missing", "duplicate", "partial", "timeout"):
            bad = copy.deepcopy(response)
            if change == "source": bad["hits"]["hits"][0]["_source"]["unique_key"] = "different"
            elif change == "index": bad["hits"]["hits"][0]["_index"] = "other-v1"
            elif change == "missing": bad["hits"]["hits"].pop()
            elif change == "duplicate": bad["hits"]["hits"][1] = bad["hits"]["hits"][0]
            elif change == "partial": bad["_shards"]["failed"] = 1
            else: bad["timed_out"] = True
            client.request.return_value = bad
            with self.subTest(change=change), self.assertRaises(AnalyticsError): maps.verify_point_id_binding(service, expected)

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

    def test_browser_diagnostics_preserve_stage_identity_without_url_state(self):
        page = SimpleNamespace(url="http://name:secret@localhost:5601/s/test/app/maps/map/actual#/?_a=private-source")
        actual = maps._browser_diagnostics(page, "inspector_map_details", "actual", ["Error"])
        self.assertEqual(actual, {"stage": "inspector_map_details", "final_path": "/s/test/app/maps/map/actual",
                                 "expected_map_id": "actual", "saved_map_path_verified": True, "page_error_types": ["Error"]})
        self.assertNotIn("secret", json.dumps(actual))
        self.assertNotIn("private-source", json.dumps(actual))
        page.url = "http://localhost:5601/app/maps/map#/actual?_a=private-source"
        self.assertFalse(maps._browser_diagnostics(page, "saved_map_path", "actual", [])["saved_map_path_verified"])

    def test_layer_loading_waits_for_named_layer_before_spinners_with_remaining_budget(self):
        page = unittest.mock.Mock()
        toc = page.locator.return_value
        layer, spinners = unittest.mock.Mock(), unittest.mock.Mock()
        toc.locator.side_effect = [layer, spinners]
        layer.count.return_value = 1
        events = []
        toc.wait_for.side_effect = lambda **kwargs: events.append(("toc", kwargs))
        layer.wait_for.side_effect = lambda **kwargs: events.append(("named_layer", kwargs))
        spinners.first.wait_for.side_effect = lambda **kwargs: events.append(("no_spinners", kwargs))
        with patch.object(maps.time, "monotonic", side_effect=[100, 103, 107, 108]):
            result = maps.wait_for_map_layers(page, "neighborhood_trends", deadline=120)
        self.assertEqual(events, [("toc", {"state": "visible", "timeout": 20000}),
                                  ("named_layer", {"state": "visible", "timeout": 17000}),
                                  ("no_spinners", {"state": "detached", "timeout": 13000})])
        page.locator.assert_called_once_with('[data-test-subj="mapLayerTOC"]')
        self.assertEqual(toc.locator.call_args_list, [unittest.mock.call(
            '[data-test-subj="layerTocActionsPanelToggleButtonNTA_closure-independent_request_trends"]'),
            unittest.mock.call('.euiLoadingSpinner')])
        self.assertEqual(result["named_layer_count"], 1)
        self.assertNotIn("rendered_parity_verified", result)

    def test_layer_loading_rejects_duplicate_layer_and_expired_budget(self):
        for failure in ("duplicate", "deadline", "spinner_timeout"):
            with self.subTest(failure=failure):
                page = unittest.mock.Mock()
                toc = page.locator.return_value
                layer, spinners = unittest.mock.Mock(), unittest.mock.Mock()
                toc.locator.side_effect = [layer, spinners]
                layer.count.return_value = 2 if failure == "duplicate" else 1
                if failure == "spinner_timeout": spinners.first.wait_for.side_effect = TimeoutError()
                times = [100, 101, 120] if failure == "deadline" else [100, 101, 102]
                error = TimeoutError if failure == "spinner_timeout" else AnalyticsError
                with patch.object(maps.time, "monotonic", side_effect=times), self.assertRaises(error):
                    maps.wait_for_map_layers(page, "requests", deadline=120)
                if failure != "spinner_timeout": spinners.first.wait_for.assert_not_called()

    def test_inspector_actions_share_remaining_budget_beyond_default_thirty_seconds(self):
        tab, close, screenshot = (unittest.mock.Mock() for _ in range(3))
        with patch.object(maps.time, "monotonic", side_effect=[100, 149, 150, 151, 190, 191]):
            maps._render_action(220, tab.click)
            maps._render_action(220, close.click)
            maps._render_action(220, screenshot, path="map.png", full_page=True)
        tab.click.assert_called_once_with(timeout=120000)
        close.click.assert_called_once_with(timeout=70000)
        screenshot.assert_called_once_with(timeout=30000, path="map.png", full_page=True)

    def test_inspector_action_cannot_start_or_succeed_after_shared_deadline(self):
        for times, invoked in (([220], False), ([100, 221], True)):
            with self.subTest(times=times):
                action = unittest.mock.Mock(return_value="late value")
                with patch.object(maps.time, "monotonic", side_effect=times), self.assertRaises(AnalyticsError):
                    maps._render_action(220, action)
                self.assertEqual(action.called, invoked)

    def test_inspector_reads_code_text_not_eui_accessibility_siblings(self):
        # Pinned EUI116.5.0: screen-reader label precedes <code>; token/line spans
        # preserve text nodes/newlines. Container innerText is not valid JSON.
        value = {"sources": {"actual": {"data": "quoted ' ! \\n snow \u96ea"}}, "layers": []}
        raw = json.dumps(value, indent=2, ensure_ascii=False)
        html = ('<div data-test-subj="mapboxStyleContainer"><pre>'
                '<span>\ufeff</span><div class="euiScreenReaderOnly">json code block:</div><span>\ufeff</span>'
                '<code data-code-language="json">' + ''.join('<span>' + escape(line) + '</span>' for line in raw.splitlines(keepends=True))
                + '</code></pre></div>')
        class TextNodes(HTMLParser):
            def __init__(self): super().__init__(); self.inside = False; self.all = []; self.code = []
            def handle_starttag(self, tag, attrs):
                if tag == "code": self.inside = True
            def handle_endtag(self, tag):
                if tag == "code": self.inside = False
            def handle_data(self, data):
                self.all.append(data)
                if self.inside: self.code.append(data)
        dom = TextNodes(); dom.feed(html)
        with self.assertRaises(json.JSONDecodeError): json.loads("".join(dom.all))
        page = unittest.mock.Mock()
        container = page.locator.return_value
        code = container.locator.return_value
        code.text_content.return_value = "".join(dom.code)
        parsed, details = maps.read_inspector_style(page, timeout_ms=1234)
        self.assertEqual(parsed, value)
        page.locator.assert_called_once_with('[data-test-subj="mapboxStyleContainer"]')
        container.locator.assert_called_once_with('code[data-code-language="json"]')
        code.text_content.assert_called_once_with(timeout=1234)
        container.inner_text.assert_not_called()
        self.assertEqual(details["utf8_bytes"], len(raw.encode("utf-8")))
        self.assertEqual(details["sha256"], maps.hashlib.sha256(raw.encode("utf-8")).hexdigest())

    def test_inspector_parse_failure_has_bounded_identity_and_position_not_source_text(self):
        page = unittest.mock.Mock()
        page.locator.return_value.locator.return_value.text_content.return_value = 'private-source {broken'
        with self.assertRaises(AnalyticsError) as caught:
            maps.read_inspector_style(page, timeout_ms=100)
        details = caught.exception.inspector_details
        self.assertEqual(details["parse_error"], {"line": 1, "column": 1, "position": 0})
        self.assertEqual(details["utf8_bytes"], 22)
        self.assertNotIn("private-source", json.dumps(details))
        self.assertNotIn("private-source", caught.exception.message)

    def test_render_failure_receipt_includes_specific_browser_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expectation = root / "expected.json"
            expectation.write_text(json.dumps({"dataset_version": "test-v1", "reference": {"sha256": "a" * 64},
                                              "source_count": 0, "mapped_unique_keys": []}))
            mapped = {"source_count": 0, "mapped_count": 0, "url": "http://localhost/goto/id",
                      "locator_request": {"params": {"mapId": "actual", "filters": [{"query": {"match_all": {}}}]}}}
            service = SimpleNamespace(config={"backend": "elastic"}, manifest={"dataset_version": "test-v1"},
                                      create_map_link=lambda *args: mapped)
            diagnostics = {"stage": "inspector_map_details", "final_path": "/app/maps/map/actual",
                           "expected_map_id": "actual", "saved_map_path_verified": True, "page_error_types": []}
            def browser(*args, **kwargs):
                self.assertEqual(kwargs["map_id"], "actual")
                (args[1] / "browser-diagnostics.json").write_text(json.dumps(diagnostics))
                raise TimeoutError()
            with patch.object(maps, "AnalyticsService", return_value=service), patch.object(maps, "inspect_csv", return_value={}), \
                 patch.object(maps, "verify_point_id_binding", return_value={}), \
                 patch.object(maps, "browser_style", side_effect=browser):
                result = maps.render(root / "profile.json", "a" * 32, "requests", expectation, root / "file.csv", root / "render")
            self.assertFalse(result["passed"])
            self.assertEqual(result["error"], {"stage": "browser", "code": "acceptance_failed", "type": "TimeoutError"})
            self.assertEqual(result["browser_diagnostics"], diagnostics)

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
