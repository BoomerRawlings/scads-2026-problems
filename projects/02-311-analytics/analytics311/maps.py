"""Kibana locator bridge. Live filter/layer parity is a deployment acceptance gate."""
import copy
import ipaddress
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, build_opener

from .compiler import compile_query
from .elastic import _NoRedirect, validate_index
from .errors import AnalyticsError


class KibanaClient:
    def __init__(self, config):
        try:
            url = config.get("url", "")
            if not isinstance(url, str):
                raise ValueError()
            self.url = url.rstrip("/")
            parsed = urlsplit(self.url)
            port = parsed.port
        except (AttributeError, TypeError, ValueError):
            raise AnalyticsError("invalid_configuration", "Kibana URL must be a valid HTTP(S) origin") from None
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment or port == 0:
            raise AnalyticsError("invalid_configuration", "Kibana URL must be an HTTP(S) origin")
        try:
            local = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            local = parsed.hostname == "localhost"
        if parsed.scheme == "http" and not (local and config.get("allow_insecure_local") is True):
            raise AnalyticsError("invalid_configuration", "Kibana HTTP requires explicit loopback development mode")
        self.key = os.environ.get("KIBANA_API_KEY")
        if not self.key and not (local and config.get("allow_insecure_local") is True):
            raise AnalyticsError("backend_unavailable", "KIBANA_API_KEY is required for this endpoint")
        space = config.get("space")
        if space is not None and (not isinstance(space, str) or not space or len(space) > 128):
            raise AnalyticsError("invalid_configuration", "Kibana space must be a nonempty string of at most 128 characters")
        self.prefix = "/s/" + quote(space, safe="") if space else ""

    def request(self, path, body=None, *, method="POST"):
        if method not in {"GET", "POST"} or not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise AnalyticsError("invalid_configuration", "Kibana request requires GET/POST and a path on its configured origin")
        if method == "GET" and body is not None:
            raise AnalyticsError("invalid_configuration", "Kibana GET requests do not accept a body")
        headers = {"Content-Type": "application/json", "kbn-xsrf": "analytics311"}
        if self.key:
            headers["Authorization"] = "ApiKey " + self.key
        encoded = None if body is None else json.dumps(body, allow_nan=False).encode()
        request = Request(self.url + self.prefix + path, data=encoded, headers=headers, method=method)
        try:
            with build_opener(_NoRedirect()).open(request, timeout=30) as response:
                payload = response.read(1024 * 1024 + 1)
            if len(payload) > 1024 * 1024:
                raise AnalyticsError("budget_exceeded", "Kibana response exceeded budget")
            result = json.loads(payload)
            if not isinstance(result, dict):
                raise ValueError("Expected a JSON object")
            return result
        except HTTPError as exc:
            error = AnalyticsError("backend_unavailable", f"Kibana returned HTTP {exc.code}; check configuration and privileges")
            # Retain actionable transport evidence, never arbitrary server bodies,
            # credentials, or query parameters in a public failure receipt.
            error.backend_details = {"http_status": exc.code, "method": method,
                                     "path": path.split("?", 1)[0]}
            raise error from None
        except (URLError, OSError, ValueError):
            raise AnalyticsError("backend_unavailable", "Kibana is unavailable or returned invalid JSON") from None


def _verify_data_view(client, data_view_id, index):
    """No implicit date predicate or wildcard may change the saved cohort."""
    if not isinstance(data_view_id, str) or not data_view_id or data_view_id.startswith("CONFIGURE_"):
        raise AnalyticsError("backend_unavailable", "Configure an exact-index Kibana data view without a time field")
    index = validate_index(index)
    response = client.request("/api/data_views/data_view/" + quote(data_view_id, safe=""), method="GET")
    view = response.get("data_view")
    if not isinstance(view, dict) or view.get("title") != index:
        raise AnalyticsError("invalid_configuration", "Kibana data view must target exactly the configured concrete index")
    if view.get("timeFieldName") not in (None, ""):
        raise AnalyticsError("invalid_configuration", "Kibana data view must have no time field; all date selection belongs to the saved DSL")


def _create_locator_link(client, payload):
    """Bridge browser-only Maps locators through Kibana's server URL locator.

    Maps 9.5.5 registers MAPS_APP_LOCATOR in the browser, so passing it directly
    to the server short-URL API returns 409. The public /app/r redirect resolves
    the exact versioned locator state in the browser, without reimplementing
    Maps' Rison URL encoding or altering any query/filter.
    """
    status = client.request("/api/status", method="GET")
    version = status.get("version", {}).get("number")
    if not isinstance(version, str) or len(version) > 64 or not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
        raise AnalyticsError("backend_unavailable", "Kibana locator links require the actual version.number from /api/status; configure status access")
    redirect = "/app/r/?" + urlencode({"l": payload["locatorId"], "v": version,
                                      "p": json.dumps(payload["params"], separators=(",", ":"), allow_nan=False)})
    request = {"locatorId": "LEGACY_SHORT_URL_LOCATOR", "params": {"url": redirect}}
    response = client.request("/api/short_url", request)
    identifier = response.get("id")
    if not isinstance(identifier, str) or not identifier or len(identifier) > 255:
        raise AnalyticsError("backend_unavailable", "Kibana did not return a short URL object ID")
    # /goto resolves object IDs and performs a full navigation for this legacy
    # wrapper, ensuring the browser locator redirect app mounts afresh.
    return {"url": client.url + client.prefix + "/goto/" + quote(identifier, safe=""),
            "short_url_request": request, "short_url_id": identifier, "locator_version": version}


def build_map_request(service, saved, mode, cohort_scope, selected):
    """Construct exact selection; this function never claims the map was rendered."""
    config = service.config.get("kibana", {})
    if mode != "requests":
        raise AnalyticsError("unsupported_operation", "Neighborhood trend map publishing requires a verified NTA boundary/result layer; use aggregate CSV until configured")
    if not config.get("map_id") or config["map_id"].startswith("CONFIGURE_") or not config.get("data_view_id") or config["data_view_id"].startswith("CONFIGURE_"):
        raise AnalyticsError("backend_unavailable", "Configure a saved Kibana map and snapshot-specific data view; see docs/runtime.md")
    queries = [compile_query(spec) for spec in service._record_specs(saved, selected)]
    selection = queries[0] if len(queries) == 1 else {"bool": {"should": queries, "minimum_should_match": 1}}
    coverage = service.manifest.get("coverage", {})
    if not coverage.get("gte") or not coverage.get("lt"):
        raise AnalyticsError("coverage_gap", "Map requires explicit snapshot date bounds")
    # Empty KQL replaces saved queries. All date selection is in the DSL filter;
    # timeRange has no effect on the required data view with no time field.
    return {"locatorId": "MAPS_APP_LOCATOR", "params": {
        "mapId": config["map_id"], "query": {"language": "kuery", "query": ""},
        "timeRange": {"from": coverage["gte"], "to": coverage["lt"]},
        "filters": [{"meta": {"index": config["data_view_id"], "disabled": False, "negate": False,
                                "alias": f"311 result {saved['result_id']} ({cohort_scope})"},
                     "$state": {"store": "appState"}, "query": selection}]}}


def create_map_link(service, saved, mode, cohort_scope, selected):
    if service.config["backend"] != "elastic":
        raise AnalyticsError("unsupported_operation", "Fixture results cannot produce a real Kibana map; use an indexed immutable dataset")
    if mode == "neighborhood_trends":
        from .trend_maps import publish_trend_map
        config = service.config.get("kibana", {})
        client = KibanaClient(config)
        _verify_data_view(client, config.get("trend_data_view_id"), config.get("result_index"))
        publication = publish_trend_map(service, saved, selected)
        payload = publication["locator_request"]
        return {**publication, "result_id": saved["result_id"], **_create_locator_link(client, payload)}
    payload = build_map_request(service, saved, mode, cohort_scope, selected)
    client = KibanaClient(service.config["kibana"])
    _verify_data_view(client, service.config["kibana"]["data_view_id"], service.config.get("index"))
    count = mapped = 0
    for spec in service._record_specs(saved, selected):
        spec["preview_limit"] = 1
        count += service.backend.execute(spec)["total"]
        located = copy.deepcopy(spec)
        located["filters"] = {"all": [spec.get("filters", {"all": []}), {"field": "location", "op": "exists", "value": True}]}
        mapped += service.backend.execute(located)["total"]
    return {"result_id": saved["result_id"], **_create_locator_link(client, payload),
            "cohort_scope": cohort_scope, "group_ids": [r["group_id"] for r in selected] if selected is not None else None,
            "source_count": count, "mapped_count": mapped, "missing_location_count": count - mapped,
            "locator_request": payload, "parity_verified": False,
            "warnings": ["The data view targets the exact index and has no time field. A returned link is not proof that rendered layers honor the saved DSL filters.",
                         "Point/vector tile layers can limit displayed features; mapped_count is the matching geolocated population, not a rendered feature count."]}
