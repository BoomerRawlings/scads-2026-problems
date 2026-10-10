"""Provision and inspect actual Kibana 9.5.5 maps on an explicit live target.

No services are started. Provision creates new objects only. Render verification
requires Playwright/Chromium and independent bounded-cohort expectations; it
fails closed when Kibana's actual Inspector/source/request evidence is missing.
See docs/live-maps.md for the versioned upstream schemas and expectation format.
"""

import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
from urllib.parse import quote, urlsplit
import uuid

from analytics311.errors import AnalyticsError
from analytics311.maps import KibanaClient
from analytics311.service import AnalyticsService, atomic_json, canonical, read_json
from analytics311.trend_maps import RESULT_MAPPING, METRIC_UNITS
from analytics311.elastic import validate_index

VERSION = "9.5.5"
MAX_BOUNDARY_BYTES = 16 * 1024 * 1024
MAX_POINTS = 10000
JOIN_ID = "analytics311-nta-join"
LAYER_LABELS = {"requests": "311 requests", "neighborhood_trends": "NTA closure-independent request trends"}


def require(condition, message):
    if not condition:
        raise AnalyticsError("acceptance_failed", message)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def new_path(path):
    path = Path(path)
    require(not path.exists(), "Output exists; choose a new evidence path.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def key(name):
    return "__kbnjoin__max_of_" + name + "__" + JOIN_ID


def source(view, geo, *, global_query, tooltip):
    return {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, "analytics311:" + view)),
            "type": "ES_SEARCH", "indexPatternRefName": "source_view", "geoField": geo,
            "scalingType": "LIMIT", "filterByMapBounds": False,
            "applyGlobalQuery": global_query, "applyGlobalTime": False,
            "tooltipProperties": tooltip, "sortField": "nta2020" if geo == "geometry" else "unique_key",
            "sortOrder": "asc"}


def map_object(mode, *, source_view, result_view=None, metric="rate_change"):
    """Descriptors follow pinned upstream schemas; live import is still a gate."""
    require(mode in {"requests", "neighborhood_trends"}, "Unknown map mode.")
    require(metric in METRIC_UNITS, "Unsupported trend metric.")
    points = mode == "requests"
    layer = {"id": "analytics311-" + mode, "label": LAYER_LABELS[mode],
             "type": "GEOJSON_VECTOR", "visible": True, "alpha": 0.8, "minZoom": 0, "maxZoom": 24,
             "sourceDescriptor": source(source_view, "location" if points else "geometry", global_query=points,
                                         tooltip=["unique_key", "complaint_type"] if points else ["nta2020", "ntaname"]),
             "style": {"type": "VECTOR", "properties": {
                 "fillColor": {"type": "STATIC", "options": {"color": "#2379a5"}},
                 "lineColor": {"type": "STATIC", "options": {"color": "#142b46"}},
                 "lineWidth": {"type": "STATIC", "options": {"size": 1}},
                 "iconSize": {"type": "STATIC", "options": {"size": 5}}}}}
    refs = [{"name": "source_view", "type": "index-pattern", "id": source_view}]
    if not points:
        require(isinstance(result_view, str) and bool(result_view), "Trend data view required.")
        layer["joins"] = [{"leftField": "nta2020", "right": {
            "id": JOIN_ID, "type": "ES_TERM_SOURCE", "indexPatternRefName": "result_view",
            "term": "nta2020", "size": 1000, "applyGlobalQuery": True, "applyGlobalTime": False,
            "metrics": [{"type": "max", "field": field} for field in METRIC_UNITS]}}]
        layer["style"]["properties"]["fillColor"] = {"type": "DYNAMIC", "options": {
            "field": {"name": key(metric), "origin": "join"}, "color": "Green to Red", "type": "ORDINAL",
            "fieldMetaOptions": {"isEnabled": False}, "useCustomColorRamp": False}}
        refs.append({"name": "result_view", "type": "index-pattern", "id": result_view})
    state = {"zoom": 9.2, "center": {"lon": -73.94, "lat": 40.72}, "query": {"query": "", "language": "kuery"},
             "filters": [], "refreshConfig": {"isPaused": True, "interval": 0},
             "settings": {"autoFitToDataBounds": False, "backgroundColor": "#f6f3ed", "projection": "mercator"}}
    return {"attributes": {"title": "NYC 311 " + mode, "description": "Exact saved-cohort map; no external basemap.",
                           "layerListJSON": canonical([layer]), "mapStateJSON": canonical(state),
                           "uiStateJSON": canonical({"isLayerTOCOpen": True, "openTOCDetails": []})}, "references": refs}


def read_boundaries(path):
    path = Path(path)
    require(path.is_file() and 0 < path.stat().st_size <= MAX_BOUNDARY_BYTES, "Boundary file exceeds bounded input.")
    raw = path.read_bytes()
    value = json.loads(raw)
    features = value.get("features", [])
    require(value.get("type") == "FeatureCollection" and 1 <= len(features) <= 1000, "Expected bounded GeoJSON collection.")
    docs = []
    codes = set()
    for feature in features:
        props, geometry = feature.get("properties", {}), feature.get("geometry", {})
        code = props.get("nta2020")
        require(isinstance(code, str) and code and code not in codes, "Missing or duplicate NTA code.")
        require(geometry.get("type") in {"Polygon", "MultiPolygon"}, "NTA boundary must be a polygon.")
        codes.add(code)
        docs.append({"nta2020": code, "ntaname": str(props.get("ntaname", "")),
                     "ntatype": str(props.get("ntatype", "")), "geometry": geometry})
    return docs, hashlib.sha256(raw).hexdigest()


def create_view(client, identifier, index):
    response = client.request("/api/data_views/data_view", {"data_view": {"id": identifier, "title": index},
                                                         "override": False})
    require(response.get("data_view", {}).get("id") == identifier, "Data view creation identity mismatch.")
    view = client.request("/api/data_views/data_view/" + quote(identifier, safe=""), method="GET").get("data_view", {})
    require(view.get("title") == index and view.get("timeFieldName") in (None, ""), "Data view changes cohort selection.")


def provision(config_path, boundary_path, boundary_index, output_config, output):
    output, output_config = new_path(output), new_path(output_config)
    require(output.resolve() != output_config.resolve(), "Evidence and profile outputs must differ.")
    config = read_json(config_path)
    require(config.get("backend") == "elastic", "Live Maps requires Elasticsearch.")
    boundary_index = validate_index(boundary_index)
    docs, boundary_sha = read_boundaries(boundary_path)
    service = AnalyticsService(config_path)
    require(service.manifest.get("geography", {}).get("nta_version") == boundary_sha,
            "Source snapshot NTA assignment hash differs from the supplied boundaries.")
    client = service.backend.client
    kibana = KibanaClient(config.get("kibana", {}))
    receipt = {"schema_version": 1, "passed": False, "rendered_parity_verified": False,
               "started_at": datetime.now(timezone.utc).isoformat(), "checks": {}, "boundaries_sha256": boundary_sha}
    stage = "version"
    try:
        require(client.request("GET", "/").get("version", {}).get("number") == VERSION, "Elasticsearch version differs from pinned schema.")
        status = kibana.request("/api/status", method="GET")
        version = status.get("version")
        reported_version = version.get("number") if isinstance(version, dict) else None
        receipt["checks"]["kibana_status_version"] = reported_version
        if reported_version is None:
            # Kibana 9.5.5 redacts this endpoint even on an unsecured local
            # stack unless status.allowAnonymous is explicitly enabled.
            raise AnalyticsError("kibana_status_version_unavailable",
                                 "Kibana status omitted its version. Use credentials with the monitor privilege, "
                                 "or status.allowAnonymous=true only on the isolated local test service. "
                                 "A healthy redacted status is not version evidence.")
        require(reported_version == VERSION, "Kibana version differs from pinned schema.")
        receipt["checks"]["stack_version"] = VERSION
        source_index = validate_index(config["index"])
        result_index = validate_index(config["kibana"]["result_index"])
        require(len({source_index, boundary_index, result_index}) == 3, "Source, result and boundary indices must differ.")
        stage = "boundary_index"
        mapping = {"mappings": {"dynamic": "strict", "properties": {
            "nta2020": {"type": "keyword"}, "ntaname": {"type": "keyword"}, "ntatype": {"type": "keyword"},
            "geometry": {"type": "geo_shape"}}}, "settings": {"number_of_shards": 1, "number_of_replicas": 0}}
        client.request("PUT", "/" + boundary_index, mapping)
        for start in range(0, len(docs), 10):
            batch = docs[start:start + 10]
            body = "".join(canonical({"create": {"_id": doc["nta2020"]}}) + "\n" + canonical(doc) + "\n" for doc in batch)
            result = client.request("POST", "/" + boundary_index + "/_bulk?refresh=wait_for", body)
            require(len(result.get("items", [])) == len(batch), "Incomplete boundary bulk response.")
            for item, doc in zip(result["items"], batch):
                entry = item.get("create", {})
                require(entry.get("status") == 201 and entry.get("_id") == doc["nta2020"] and entry.get("_index") == boundary_index,
                        "Boundary create failed or identity mismatched.")
        require(client.request("POST", "/" + boundary_index + "/_count", {"query": {"match_all": {}}}).get("count") == len(docs),
                "Boundary indexed count differs.")
        client.request("PUT", "/" + boundary_index + "/_settings", {"index.blocks.write": True})
        receipt["checks"]["boundary_count"] = len(docs)
        stage = "result_index"
        client.request("PUT", "/" + result_index, {**copy.deepcopy(RESULT_MAPPING),
                                                   "settings": {"number_of_shards": 1, "number_of_replicas": 0}})
        ids = {name: str(uuid.uuid4()) for name in ("data_view_id", "boundary_view_id", "trend_data_view_id", "map_id", "trend_map_id")}
        stage = "data_views"
        for name, index in (("data_view_id", source_index), ("boundary_view_id", boundary_index), ("trend_data_view_id", result_index)):
            create_view(kibana, ids[name], index)
        receipt["checks"]["exact_no_time_data_views"] = True
        stage = "saved_maps"
        for mode, identifier, view in (("requests", ids["map_id"], ids["data_view_id"]),
                                      ("neighborhood_trends", ids["trend_map_id"], ids["boundary_view_id"])):
            payload = map_object(mode, source_view=view, result_view=ids["trend_data_view_id"])
            created = kibana.request("/api/saved_objects/map/" + identifier, payload)
            require(created.get("id") == identifier and created.get("type") == "map", "Map creation identity mismatch.")
            found = kibana.request("/api/saved_objects/map/" + identifier, method="GET")
            require(found.get("attributes", {}).get("layerListJSON") == payload["attributes"]["layerListJSON"], "Stored map layers differ.")
            require(found.get("references") == payload["references"], "Stored map references differ.")
        config["kibana"].update(ids)
        config["kibana"].update({"trend_metric": "rate_change", "boundary_index": boundary_index})
        # Resolve the existing profile-relative files before writing elsewhere.
        for field in ("manifest_path", "catalog_path", "runs_dir"):
            if field in config:
                path = Path(config[field])
                if not path.is_absolute(): path = Path(config_path).resolve().parent / path
                config[field] = str(path.resolve())
        atomic_json(output_config, config)
        receipt.update({"passed": True, "map_ids": ids, "source_index": source_index, "boundary_index": boundary_index,
                        "result_index": result_index, "dataset_version": service.manifest.get("dataset_version")})
    except AnalyticsError as exc:
        receipt["error"] = {"stage": stage, "code": exc.code}
        if exc.code in {"acceptance_failed", "kibana_status_version_unavailable"}:
            receipt["error"]["reason"] = exc.message
    except (OSError, ValueError, TypeError, KeyError):
        receipt["error"] = {"stage": stage, "code": "acceptance_failed"}
    finally:
        atomic_json(output, receipt)
    return receipt


def contains_tree(value, expected):
    if value == expected:
        return True
    if isinstance(value, dict):
        return any(contains_tree(child, expected) for child in value.values())
    if isinstance(value, list):
        return any(contains_tree(child, expected) for child in value)
    if isinstance(value, str) and value.startswith(("{", "[")):
        try: return contains_tree(json.loads(value), expected)
        except ValueError: pass
    return False


def value_equal(observed, expected):
    if expected is None:
        return observed is None
    return type(observed) in (int, float) and type(expected) in (int, float) and math.isfinite(observed) and math.isclose(observed, expected, rel_tol=1e-9, abs_tol=1e-10)


def verify_point_id_binding(service, expectation):
    """Prove live ES document IDs equal independently expected source keys.

    Our ingester explicitly assigns _id=unique_key, but check the actual frozen
    index as well before using Kibana's retained ES metadata for membership.
    """
    index = validate_index(service.config.get("index"))
    expected = expectation.get("mapped_unique_keys")
    require(isinstance(expected, list) and 0 < len(expected) <= MAX_POINTS
            and all(isinstance(value, str) and value for value in expected)
            and len(expected) == len(set(expected)), "Expected located IDs must be bounded and unique.")
    response = service.backend.client.request("POST", "/" + index + "/_search", {
        "size": len(expected), "track_total_hits": True, "_source": ["unique_key"],
        "query": {"ids": {"values": expected}}})
    hits = response.get("hits", {})
    total = hits.get("total", {})
    rows = hits.get("hits", [])
    require(not response.get("timed_out") and response.get("_shards", {}).get("failed") == 0
            and total == {"value": len(expected), "relation": "eq"}
            and isinstance(rows, list) and len(rows) == len(expected), "ES document identity check is incomplete.")
    observed = []
    for row in rows:
        identifier = row.get("_id")
        require(row.get("_index") == index and isinstance(identifier, str)
                and row.get("_source", {}).get("unique_key") == identifier,
                "ES document ID differs from its source unique_key or frozen index.")
        observed.append(identifier)
    require(len(observed) == len(set(observed)) and sorted(observed) == sorted(expected),
            "ES document identity check differs from independent located membership.")
    return {"point_document_id_binding_verified": True, "point_document_id_index": index,
            "point_document_id_count": len(observed), "point_document_id_sha256": fingerprint(sorted(observed))}


def inspect_style(style, mode, expectation, *, source_index=None):
    """Compare actual Inspector-rendered GeoJSON; API/search response is insufficient."""
    require(isinstance(style.get("sources"), dict) and isinstance(style.get("layers"), list), "Inspector omitted rendered sources/layers.")
    features = []
    source_ids = []
    for identifier, source_data in style["sources"].items():
        if not isinstance(source_data, dict):
            continue
        data = source_data.get("data")
        if source_data.get("type") == "geojson" and isinstance(data, dict) and data.get("type") == "FeatureCollection":
            source_ids.append(identifier)
            features.extend(data.get("features", []))
    require(source_ids and len(features) <= MAX_POINTS, "No bounded rendered GeoJSON source found.")
    require(any(layer.get("source") in source_ids for layer in style["layers"]), "Rendered layer does not reference inspected source.")
    if mode == "requests":
        expected = expectation.get("mapped_unique_keys")
        require(isinstance(expected, list) and 0 < len(expected) <= MAX_POINTS and len(expected) == len(set(expected)), "Expected located IDs must be bounded and unique.")
        observed = []
        for feature in features:
            properties = feature.get("properties", {})
            value = properties.get("unique_key")
            if isinstance(value, list) and len(value) == 1: value = value[0]
            if source_index is not None:
                # Tooltip fields are fetched lazily; ES metadata is preserved
                # by the pinned source's flattenHit -> hitsToGeoJson conversion.
                identifier = properties.get("_id")
                require(properties.get("_index") == source_index and isinstance(identifier, str)
                        and identifier and ("unique_key" not in properties or value == identifier),
                        "Rendered point ES identity differs from the verified frozen source.")
                value = identifier
            require(isinstance(value, str) and feature.get("geometry", {}).get("type") == "Point", "Rendered point omitted source ID or geometry.")
            observed.append(value)
        require(len(observed) == len(set(observed)) and sorted(observed) == sorted(expected), "Rendered point membership differs from independent expectation.")
        return {"rendered_points": len(observed), "membership_sha256": fingerprint(sorted(observed))}
    expected = expectation.get("groups")
    require(isinstance(expected, dict) and 0 < len(expected) <= 1000, "Expected joined groups must be bounded.")
    observed, polygons, centroids = {}, {}, []
    for feature in features:
        properties = feature.get("properties", {})
        nta = properties.get("nta2020")
        if isinstance(nta, list) and len(nta) == 1: nta = nta[0]
        metrics = {name: properties.get(key(name)) for name in METRIC_UNITS}
        if metrics["baseline_count"] is None and metrics["current_count"] is None:
            continue
        if properties.get("__kbn_is_centroid_feature__") is True:
            require(feature.get("geometry", {}).get("type") == "Point", "Kibana centroid flag appears on non-point geometry.")
            centroids.append((nta, feature, metrics))
            continue
        require(isinstance(nta, str) and nta not in observed and feature.get("geometry", {}).get("type") in {"Polygon", "MultiPolygon"},
                "Rendered join omitted unique NTA polygon identity.")
        observed[nta] = metrics
        polygons[nta] = feature
    centroid_ntas = set()
    for nta, feature, metrics in centroids:
        polygon = polygons.get(nta)
        require(polygon is not None and nta not in centroid_ntas and polygon.get("id") is not None
                and feature.get("id") == polygon["id"]
                and all(value_equal(metrics[name], observed[nta][name]) for name in METRIC_UNITS),
                "Kibana centroid does not match its unique joined polygon identity and metrics.")
        centroid_ntas.add(nta)
    require(set(observed) == set(expected), "Rendered joined neighborhood selection differs.")
    for nta, metrics in expected.items():
        require(set(metrics) == set(METRIC_UNITS), "Expected join must define all supported metrics.")
        require(all(value_equal(observed[nta][name], value) for name, value in metrics.items()), "Rendered neighborhood metrics differ.")
    require(any(key("rate_change") in canonical(layer.get("paint", {})) for layer in style["layers"]), "Visible style does not use declared trend metric.")
    return {"rendered_joined_groups": len(observed), "metrics_sha256": fingerprint(observed)}


def inspect_csv(path, mode, expectation):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= 16 * 1024 * 1024, "CSV exceeds bounded map qualification scope.")
    before = path.stat()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = []
        for row in csv.DictReader(stream, strict=True):
            require(len(rows) < MAX_POINTS and None not in row and None not in row.values(), "CSV incomplete or exceeds map qualification scope.")
            rows.append(row)
    if mode == "requests":
        expected = expectation.get("unique_keys")
        require(isinstance(expected, list) and len(expected) == len(set(expected)) and len(expected) == expectation.get("source_count"), "Expected complete source IDs/count differ.")
        observed = [row.get("unique_key") for row in rows]
        require(len(observed) == len(set(observed)) and sorted(observed) == sorted(expected), "CSV membership differs from independent reference.")
        require(set(expectation.get("mapped_unique_keys", [])) <= set(expected), "Located IDs exceed source cohort.")
    else:
        groups = {}
        excluded = 0
        for row in rows:
            nta = row.get("nta2020")
            if not nta:
                excluded += 1
                continue
            require(nta not in groups, "CSV duplicates a neighborhood.")
            groups[nta] = {name: None if row.get(name) == "" else float(row[name]) for name in METRIC_UNITS}
        require(excluded == expectation.get("excluded_group_count", 0), "CSV unlocated group count differs.")
        require(set(groups) == set(expectation.get("groups", {})), "CSV neighborhood membership differs.")
        for nta, metrics in expectation["groups"].items():
            require(set(metrics) == set(METRIC_UNITS) and all(value_equal(groups[nta][name], value) for name, value in metrics.items()),
                    "CSV metrics differ from independent reference.")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), "CSV changed during inspection.")
    return {"csv_rows": len(rows), "csv_sha256": digest, "csv_membership_verified": True}


def _subject(page, name):
    return page.locator('[data-test-subj="' + name + '"]')


def _remaining_timeout_ms(deadline):
    remaining = deadline - time.monotonic()
    require(remaining > 0, "Map layer loading exceeded the render deadline.")
    return max(1, int(remaining * 1000))


def wait_for_map_layers(page, mode, *, deadline):
    """Pinned GIS FTR prerequisite, not rendered-data acceptance evidence."""
    require(mode in LAYER_LABELS, "Unknown map mode.")
    toc = _subject(page, "mapLayerTOC")
    toc.wait_for(state="visible", timeout=_remaining_timeout_ms(deadline))
    # Pinned GIS escapes spaces in the displayed layer label for this subject.
    subject = "layerTocActionsPanelToggleButton" + LAYER_LABELS[mode].replace(" ", "_")
    layer = _subject(toc, subject)
    layer.wait_for(state="visible", timeout=_remaining_timeout_ms(deadline))
    require(layer.count() == 1, "Expected exactly one named map layer.")
    # The locator resolves its current first element: detached therefore means
    # no loading spinner remains, rather than merely one old spinner vanishing.
    toc.locator(".euiLoadingSpinner").first.wait_for(state="detached", timeout=_remaining_timeout_ms(deadline))
    _remaining_timeout_ms(deadline)
    require(layer.count() == 1, "Named map layer changed while loading.")
    return {"method": "named_toc_layer_then_no_loading_spinner", "named_layer_count": 1,
            "layer_label": LAYER_LABELS[mode]}


def _browser_diagnostics(page, stage, map_id, errors):
    # Path only: never retain credentials, query state, source text, or raw DOM.
    path = urlsplit(page.url).path
    target = "/app/maps/map/" + quote(map_id, safe="")
    return {"stage": stage, "final_path": path[:1024], "expected_map_id": map_id,
            "saved_map_path_verified": path.endswith(target), "page_error_types": list(errors)}


def read_inspector_style(page, *, timeout_ms):
    """Read actual code DOM, excluding EUI's sibling accessibility labels.

    MapDetails uses nonvirtualized EuiCodeBlock. textContent preserves its code
    text without forcing layout of the potentially large highlighted geometry.
    No application internals, network responses, or reconstructed state are used.
    """
    raw = _subject(page, "mapboxStyleContainer").locator('code[data-code-language="json"]').text_content(timeout=timeout_ms)
    require(isinstance(raw, str), "Inspector code text is missing.")
    encoded = raw.encode("utf-8")
    details = {"method": "inspector_code_text_content", "utf8_bytes": len(encoded),
               "sha256": hashlib.sha256(encoded).hexdigest()}
    if len(encoded) > 32 * 1024 * 1024:
        error = AnalyticsError("acceptance_failed", "Inspector style exceeds budget.")
        error.inspector_details = details
        raise error
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        error = AnalyticsError("acceptance_failed", "Inspector code is not complete JSON.")
        error.inspector_details = {**details, "parse_error": {"line": exc.lineno, "column": exc.colno, "position": exc.pos}}
        raise error from None
    require(isinstance(value, dict), "Inspector style must be a JSON object.")
    return value, details


def browser_style(url, output_dir, filter_query, mode, expectation, *, map_id, source_index=None, timeout_seconds=120):
    """Uses public Inspector UI selectors also used by pinned Kibana FTR tests."""
    from playwright.sync_api import sync_playwright
    calls, errors = [], []
    start = time.monotonic()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        api_key = os.environ.get("KIBANA_API_KEY")
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        if api_key:
            origin = urlsplit(url)[:2]
            def authenticate(route):
                headers = {k: v for k, v in route.request.headers.items() if k.lower() != "authorization"}
                if urlsplit(route.request.url)[:2] == origin:
                    headers["Authorization"] = "ApiKey " + api_key
                route.continue_(headers=headers)
            context.route("**/*", authenticate)
        page = context.new_page()
        page.set_default_timeout(min(timeout_seconds * 1000, 30000))
        def capture(request):
            if len(calls) >= 100: return
            parsed = urlsplit(request.url)
            if parsed.netloc != urlsplit(url).netloc or "search" not in parsed.path: return
            data = request.post_data
            if data and len(data.encode()) <= 2 * 1024 * 1024:
                try: calls.append({"path": parsed.path, "body": json.loads(data)})
                except ValueError: pass
        page.on("request", capture)
        page.on("pageerror", lambda error: errors.append(type(error).__name__) if len(errors) < 100 else None)
        style = None
        inspector_read = None
        layer_loading = None
        stage = "navigation"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            stage = "saved_map_path"
            target = "/app/maps/map/" + quote(map_id, safe="")
            page.wait_for_url(lambda address: urlsplit(address).path.endswith(target), timeout=timeout_seconds * 1000)
            stage = "map_container"
            _subject(page, "mapContainer").wait_for(state="visible", timeout=timeout_seconds * 1000)
            stage = "map_canvas"
            page.locator("canvas").first.wait_for(state="visible")
            stage = "map_layer_loading"
            layer_loading = wait_for_map_layers(page, mode, deadline=start + timeout_seconds)
            # Loading indicators are a prerequisite only. Actual source and
            # membership assertions below remain the decisive readiness gate.
            stage = "inspector_open"
            overflow = _subject(page, "app-menu-overflow-button")
            if overflow.is_visible(): overflow.click()
            _subject(page, "openInspectorButton").click()
            _subject(page, "inspectorPanel").wait_for(state="visible")
            stage = "inspector_map_details"
            chooser = _subject(page, "inspectorViewChooser")
            if _subject(page, "inspectorViewChooserMap details").count() == 0:
                chooser.click()
            _subject(page, "inspectorViewChooserMap details").click()
            stage = "inspector_style_tab"
            _subject(page, "mapboxStyleTab").click()
            stage = "rendered_source_parity"
            failure = None
            while time.monotonic() - start < timeout_seconds:
                try:
                    stage = "inspector_style_code"
                    remaining_ms = max(1, int((timeout_seconds - (time.monotonic() - start)) * 1000))
                    style, inspector_read = read_inspector_style(page, timeout_ms=remaining_ms)
                    require(time.monotonic() - start <= timeout_seconds, "Inspector code exceeded the render deadline.")
                    stage = "rendered_source_parity"
                    verified = inspect_style(style, mode, expectation, source_index=source_index)
                    require(any(contains_tree(call["body"], filter_query) for call in calls), "Actual browser search omitted saved DSL filter.")
                    break
                except (AnalyticsError, ValueError) as exc:
                    if getattr(exc, "inspector_details", None): inspector_read = exc.inspector_details
                    failure = exc
                    page.wait_for_timeout(500)
            else:
                raise failure or AnalyticsError("acceptance_failed", "Rendered data readiness timed out.")
            require(not errors, "Browser reported an application error.")
            atomic_json(output_dir / "rendered-style.json", style)
            atomic_json(output_dir / "browser-searches.json", calls)
            stage = "inspector_close"
            page.keyboard.press("Escape")
            await_close = _subject(page, "inspectorPanel")
            if await_close.is_visible():
                close = await_close.get_by_role("button", name="Close", exact=False)
                if close.count(): close.first.click()
            await_close.wait_for(state="hidden")
            stage = "screenshot"
            page.screenshot(path=str(output_dir / "map.png"), full_page=True)
            stage = "complete"
            return {**verified, "browser_search_count": len(calls), "saved_filter_observed": True,
                    "browser_saved_map_path_verified": True,
                    "layer_loading_precondition": layer_loading,
                    "inspector_read": inspector_read,
                    "browser_page_errors": 0, "screenshot_sha256": hashlib.sha256((output_dir / "map.png").read_bytes()).hexdigest()}
        finally:
            diagnostics = _browser_diagnostics(page, stage, map_id, errors)
            if layer_loading is not None: diagnostics["layer_loading_precondition"] = layer_loading
            if inspector_read is not None: diagnostics["inspector_read"] = inspector_read
            atomic_json(output_dir / "browser-diagnostics.json", diagnostics)
            if style is not None:
                atomic_json(output_dir / "rendered-style.json", style)
            if not (output_dir / "map.png").exists():
                try: page.screenshot(path=str(output_dir / "failure.png"), full_page=True)
                except Exception: pass
            atomic_json(output_dir / "browser-searches.json", calls)
            context.close()
            browser.close()


def render(config_path, result_id, mode, expectation_path, csv_path, output_dir, *, group_ids=None, timeout_seconds=120):
    require(type(timeout_seconds) is int and 1 <= timeout_seconds <= 180, "Render timeout must be 1..180 seconds.")
    output_dir = new_path(output_dir)
    output_dir.mkdir()
    expectation = read_json(expectation_path)
    receipt = {"schema_version": 1, "passed": False, "rendered_parity_verified": False,
               "overall_release_verified": False, "mode": mode, "checks": {},
               "expectation_sha256": fingerprint(expectation), "reference": expectation.get("reference"),
               "scope": "Bounded saved-cohort rendered source membership/metrics and browser filter checks; no whole-index performance claim."}
    stage = "saved_result"
    try:
        service = AnalyticsService(config_path)
        require(service.config.get("backend") == "elastic", "Live render requires Elasticsearch.")
        require(expectation.get("dataset_version") == service.manifest.get("dataset_version"), "Expectation dataset differs.")
        require(isinstance(expectation.get("reference"), dict) and expectation["reference"].get("sha256"), "Independent reference receipt required.")
        stage = "csv"
        receipt["checks"].update(inspect_csv(csv_path, mode, expectation))
        stage = "map_link"
        scope = "selected_groups" if group_ids is not None else "all_matching"
        mapped = service.create_map_link(result_id, mode, scope, group_ids)
        receipt["saved_result_id"] = result_id
        receipt["cohort_scope"] = scope
        if mode == "requests":
            require(mapped["source_count"] == expectation.get("source_count"), "Map source count differs from reference.")
            require(mapped["mapped_count"] == len(expectation.get("mapped_unique_keys", [])), "Map located count differs from reference.")
            stage = "point_document_identity"
            receipt["checks"].update(verify_point_id_binding(service, expectation))
        else:
            require(mapped["published_group_count"] == len(expectation.get("groups", {})), "Published groups differ from reference.")
        stage = "browser"
        query = mapped["locator_request"]["params"]["filters"][0]["query"]
        receipt["checks"].update(browser_style(mapped["url"], output_dir, query, mode, expectation,
                                               map_id=mapped["locator_request"]["params"]["mapId"],
                                               source_index=service.config.get("index") if mode == "requests" else None,
                                               timeout_seconds=timeout_seconds))
        receipt.update({"passed": True, "rendered_parity_verified": True})
    except AnalyticsError as exc:
        receipt["error"] = {"stage": stage, "code": exc.code}
        if exc.code in {"acceptance_failed", "backend_unavailable", "coverage_gap"}:
            receipt["error"]["reason"] = exc.message
        if getattr(exc, "backend_details", None):
            receipt["error"]["backend"] = exc.backend_details
    except Exception as exc:
        receipt["error"] = {"stage": stage, "code": "acceptance_failed", "type": type(exc).__name__}
    finally:
        diagnostic_path = output_dir / "browser-diagnostics.json"
        if diagnostic_path.exists():
            receipt["browser_diagnostics"] = read_json(diagnostic_path)
        atomic_json(output_dir / "receipt.json", receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("provision")
    for name in ("config", "boundaries", "boundary-index", "output-config", "output"):
        p.add_argument("--" + name, required=True)
    r = commands.add_parser("render")
    for name in ("config", "result-id", "expectation", "csv", "output-dir"):
        r.add_argument("--" + name, required=True)
    r.add_argument("--mode", choices=("requests", "neighborhood_trends"), required=True)
    r.add_argument("--group-id", action="append", dest="group_ids")
    r.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    if args.command == "provision":
        result = provision(args.config, args.boundaries, args.boundary_index, args.output_config, args.output)
    else:
        result = render(args.config, args.result_id, args.mode, args.expectation, args.csv, args.output_dir,
                        group_ids=args.group_ids, timeout_seconds=args.timeout_seconds)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
