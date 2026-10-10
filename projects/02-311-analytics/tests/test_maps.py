import copy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from analytics311.maps import build_map_request, create_map_link, KibanaClient, _rison, _saved_map_url_955
from analytics311.fixture import FixtureBackend
from analytics311.service import AnalyticsService
from analytics311.errors import AnalyticsError

ROOT = Path(__file__).resolve().parents[1]


class FakeKibanaOpener:
    def __init__(self, view, version="9.5.5"):
        self.view = view
        self.version = version
        self.calls = []

    def open(self, request, timeout):
        self.calls.append(request)
        if "/api/data_views/data_view/" in request.full_url:
            if request.get_method() != "GET" or request.data is not None:
                raise AssertionError("Data view must be read using GET without a body")
            response = {"data_view": self.view}
        elif request.full_url.endswith("/api/status"):
            response = {"version": {"number": self.version}}
        elif request.full_url.endswith("/api/short_url"):
            if request.get_method() != "POST":
                raise AssertionError("Short URL creation must remain POST")
            response = {"id": "verified-object-id", "slug": "different-slug"}
        else:
            raise AssertionError(f"Unexpected mocked URL: {request.full_url}")
        return io.BytesIO(json.dumps(response).encode())


class MapTests(unittest.TestCase):
    def local_service(self, directory):
        path = Path(directory) / "requests.jsonl"
        records = [
            {"unique_key": "missing-date", "created_date": None, "location": {"lat": 40.7, "lon": -73.9}},
            {"unique_key": "outside-coverage", "created_date": "2030-01-01T00:00:00Z", "location": {"lat": 40.8, "lon": -73.9}},
            {"unique_key": "no-location", "created_date": "2025-12-01T00:00:00Z", "location": None},
        ]
        path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
        config = {"backend": "elastic", "index": "nyc311-demo-v1", "fixture_path": str(path),
                  "kibana": {"url": "http://localhost:5601", "allow_insecure_local": True,
                             "map_id": "map", "data_view_id": "snapshot-data", "space": "test-space",
                             "trend_map_id": "trend-map", "trend_data_view_id": "result-data", "result_index": "analytics311-results-v1"}}
        spec = {"operation": "records", "preview_limit": 100}
        service = SimpleNamespace(config=config, manifest={"coverage": {"gte": "2025-11-01T00:00:00-04:00", "lt": "2026-01-01T00:00:00-05:00"}},
                                  backend=FixtureBackend(config, {}, {}),
                                  _record_specs=lambda saved, selected: iter([copy.deepcopy(spec)]))
        saved = {"result_id": "a" * 32, "spec": spec}
        return service, saved

    def test_locator_preserves_scope_date_union_and_empty_saved_query(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"backend": "fixture", "fixture_path": str(ROOT / "fixtures/requests.jsonl"),
                      "manifest_path": str(ROOT / "fixtures/manifest.json"), "catalog_path": str(ROOT / "config/catalog.json"),
                      "runs_dir": str(Path(directory) / "runs"), "kibana": {"map_id": "map", "data_view_id": "snapshot-data"}}
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config))
            service = AnalyticsService(path)
            spec = json.loads((ROOT / "examples/rodent-trends.json").read_text())
            result = service.run_analysis(spec)
            saved = service._load(result["result_id"])
            selected = [saved["all_rows"][0]]
            payload = build_map_request(service, saved, "requests", "selected_groups", selected)
            self.assertEqual(payload["locatorId"], "MAPS_APP_LOCATOR")
            self.assertEqual(payload["params"]["query"]["query"], "")
            serialized = json.dumps(payload["params"]["filters"])
            self.assertIn("created_date", serialized)
            self.assertIn("nta2020", serialized)
            self.assertIn("minimum_should_match", serialized)
            self.assertEqual(payload["params"]["timeRange"]["from"], service.manifest["coverage"]["gte"])

    def test_no_credential_urls_or_remote_plaintext(self):
        for url in ("http://example.com", "https://name:secret@example.com", "file:///tmp/server"):
            with self.assertRaises(AnalyticsError):
                KibanaClient({"url": url, "allow_insecure_local": True})

    def test_exact_no_time_data_view_preserves_missing_and_outside_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            service, saved = self.local_service(directory)
            opener = FakeKibanaOpener({"id": "snapshot-data", "title": "nyc311-demo-v1"})
            with patch("analytics311.maps.build_opener", return_value=opener):
                result = create_map_link(service, saved, "requests", "all_matching", None)
            self.assertEqual((result["source_count"], result["mapped_count"], result["missing_location_count"]), (3, 2, 1))
            self.assertFalse(result["parity_verified"])
            self.assertEqual([request.get_method() for request in opener.calls], ["GET", "GET", "POST"])
            self.assertEqual(opener.calls[0].full_url, "http://localhost:5601/s/test-space/api/data_views/data_view/snapshot-data")
            self.assertEqual(result["locator_request"]["params"]["filters"][0]["query"], {"match_all": {}})
            self.assertNotIn("created_date", json.dumps(result["locator_request"]["params"]["filters"]))

    def test_time_field_rejected_before_counts_or_short_url(self):
        with tempfile.TemporaryDirectory() as directory:
            service, saved = self.local_service(directory)
            opener = FakeKibanaOpener({"title": "nyc311-demo-v1", "timeFieldName": "created_date"})
            with patch("analytics311.maps.build_opener", return_value=opener), patch.object(service.backend, "execute") as execute:
                with self.assertRaises(AnalyticsError) as caught:
                    create_map_link(service, saved, "requests", "all_matching", None)
            self.assertEqual(caught.exception.code, "invalid_configuration")
            execute.assert_not_called()
            self.assertEqual(len(opener.calls), 1)

    def test_wrong_index_wildcard_and_alias_titles_rejected(self):
        for title in ("nyc311-*", "nyc311-alias-v1", "nyc311-other-v1", "nyc311-demo-v1,other-v1"):
            with self.subTest(title=title), tempfile.TemporaryDirectory() as directory:
                service, saved = self.local_service(directory)
                opener = FakeKibanaOpener({"title": title})
                with patch("analytics311.maps.build_opener", return_value=opener), patch.object(service.backend, "execute") as execute:
                    with self.assertRaises(AnalyticsError) as caught:
                        create_map_link(service, saved, "requests", "all_matching", None)
                self.assertEqual(caught.exception.code, "invalid_configuration")
                execute.assert_not_called()
                self.assertEqual(len(opener.calls), 1)

    def test_trend_view_validation_precedes_result_publication(self):
        for view in ({"title": "analytics311-results-v1", "timeFieldName": "created_at"}, {"title": "analytics311-results-*"}):
            with self.subTest(view=view), tempfile.TemporaryDirectory() as directory:
                service, saved = self.local_service(directory)
                opener = FakeKibanaOpener(view)
                with patch("analytics311.maps.build_opener", return_value=opener), patch("analytics311.trend_maps.publish_trend_map") as publish:
                    with self.assertRaises(AnalyticsError) as caught:
                        create_map_link(service, saved, "neighborhood_trends", "all_matching", None)
                self.assertEqual(caught.exception.code, "invalid_configuration")
                publish.assert_not_called()
                self.assertEqual(len(opener.calls), 1)

    def test_valid_trend_view_uses_get_then_existing_post_short_url(self):
        with tempfile.TemporaryDirectory() as directory:
            service, saved = self.local_service(directory)
            opener = FakeKibanaOpener({"title": "analytics311-results-v1", "timeFieldName": ""})
            publication = {"locator_request": {"locatorId": "MAPS_APP_LOCATOR", "params": {"mapId": "trend-map"}}, "parity_verified": False}
            def publish(*args):
                self.assertEqual(len(opener.calls), 1)
                self.assertTrue(opener.calls[0].full_url.endswith("/data_view/result-data"))
                return publication
            with patch("analytics311.maps.build_opener", return_value=opener), patch("analytics311.trend_maps.publish_trend_map", side_effect=publish):
                result = create_map_link(service, saved, "neighborhood_trends", "all_matching", None)
            self.assertFalse(result["parity_verified"])
            self.assertEqual([request.get_method() for request in opener.calls], ["GET", "GET", "POST"])
            self.assertEqual(result["url"], "http://localhost:5601/s/test-space/goto/verified-object-id")

    def test_955_short_url_uses_saved_path_and_hash_query_state(self):
        with tempfile.TemporaryDirectory() as directory:
            service, saved = self.local_service(directory)
            opener = FakeKibanaOpener({"title": "nyc311-demo-v1"})
            with patch("analytics311.maps.build_opener", return_value=opener):
                result = create_map_link(service, saved, "requests", "all_matching", None)
            request = json.loads(opener.calls[-1].data)
            self.assertEqual(request["locatorId"], "LEGACY_SHORT_URL_LOCATOR")
            redirect = urlsplit(request["params"]["url"])
            self.assertEqual((redirect.scheme, redirect.netloc, redirect.path, redirect.query), ("", "", "/app/maps/map/map", ""))
            self.assertTrue(redirect.fragment.startswith("/?"))
            state = parse_qs(urlsplit(redirect.fragment).query)
            params = result["locator_request"]["params"]
            self.assertEqual(state["_a"], [_rison({"query": params["query"], "filters": params["filters"]})])
            self.assertEqual(state["_g"], [_rison({"filters": [], "time": params["timeRange"]})])
            self.assertEqual(result["navigation_contract"], "saved-map-path-hash-state-9.5.5")
            self.assertEqual(result["short_url_request"], request)
            self.assertEqual(result["url"], "http://localhost:5601/s/test-space/goto/verified-object-id")

    def test_other_versions_keep_browser_locator_transport_without_955_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            service, saved = self.local_service(directory)
            opener = FakeKibanaOpener({"title": "nyc311-demo-v1"}, version="9.5.6")
            with patch("analytics311.maps.build_opener", return_value=opener):
                result = create_map_link(service, saved, "requests", "all_matching", None)
            request = json.loads(opener.calls[-1].data)
            self.assertEqual(request["locatorId"], "LEGACY_SHORT_URL_LOCATOR")
            redirect = urlsplit(request["params"]["url"])
            self.assertEqual((redirect.scheme, redirect.netloc, redirect.path), ("", "", "/app/r/"))
            query = parse_qs(redirect.query)
            self.assertEqual(query["l"], ["MAPS_APP_LOCATOR"])
            self.assertEqual(query["v"], ["9.5.6"])
            self.assertEqual(json.loads(query["p"][0]), result["locator_request"]["params"])
            self.assertEqual(result["short_url_request"], request)
            self.assertEqual(result["url"], "http://localhost:5601/s/test-space/goto/verified-object-id")
            self.assertEqual(result["short_url_id"], "verified-object-id")

    def test_pinned_upstream_decoded_rison_fixtures_and_full_dsl(self):
        fixture = json.loads((ROOT / "tests/fixtures/kibana-9.5.5-map-url.json").read_text())
        self.assertEqual(fixture["provenance"]["kibana_commit"], "a2890159e2486503b9e3a0c6f422b153a746651a")
        for case in fixture["cases"]:
            self.assertEqual(_rison(case["value"]), case["rison"])
        payload = {"locatorId": "MAPS_APP_LOCATOR", "params": fixture["params"]}
        original = copy.deepcopy(payload)
        address = urlsplit(_saved_map_url_955(payload))
        self.assertEqual(address.path, "/app/maps/map/map-probe-v1")
        self.assertEqual(address.query, "")
        state = parse_qs(urlsplit(address.fragment).query)
        self.assertEqual(state, {"_a": [fixture["cases"][0]["rison"]], "_g": [fixture["cases"][1]["rison"]]})
        self.assertEqual(payload, original)

    def test_955_bridge_fails_closed_on_unqualified_state_or_nonfinite_values(self):
        for params in ({"mapId": "map", "initialLayers": [{}]}, {"mapId": "map", "dataViewSpec": {}},
                       {"mapId": ".."}, {"mapId": "map", "query": {"value": float("nan")}}):
            with self.subTest(params=params), self.assertRaises(AnalyticsError):
                _saved_map_url_955({"locatorId": "MAPS_APP_LOCATOR", "params": params})
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(AnalyticsError): _rison(cycle)

    def test_locator_version_missing_blocks_short_url_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            service, saved = self.local_service(directory)
            opener = FakeKibanaOpener({"title": "nyc311-demo-v1"})
            original = opener.open
            def open_request(request, timeout):
                if request.full_url.endswith("/api/status"):
                    opener.calls.append(request)
                    return io.BytesIO(b'{"status":{"overall":{"level":"available"}}}')
                return original(request, timeout)
            opener.open = open_request
            with patch("analytics311.maps.build_opener", return_value=opener), self.assertRaises(AnalyticsError) as caught:
                create_map_link(service, saved, "requests", "all_matching", None)
            self.assertEqual(caught.exception.code, "backend_unavailable")
            self.assertTrue(all(request.get_method() == "GET" for request in opener.calls))

    def test_http_failure_retains_status_without_server_body_or_secrets(self):
        client = KibanaClient({"url": "http://localhost:5601", "allow_insecure_local": True})
        failure = HTTPError("http://localhost:5601/api/short_url", 409, "Conflict", {},
                            io.BytesIO(b'{"message":"secret-untrusted-server-body"}'))
        with patch("analytics311.maps.build_opener") as opener:
            opener.return_value.open.side_effect = failure
            with self.assertRaises(AnalyticsError) as caught:
                client.request("/api/short_url", {"locatorId": "MAPS_APP_LOCATOR", "params": {}})
        self.assertEqual(caught.exception.backend_details, {"http_status": 409, "method": "POST", "path": "/api/short_url"})
        self.assertNotIn("secret", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
