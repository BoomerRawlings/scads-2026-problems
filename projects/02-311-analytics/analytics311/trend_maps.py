"""Publish bounded, immutable NTA comparison artifacts for a configured map.

An administrator creates the dedicated result index and NTA join layer first.
The artifact writer can create result documents, never alter source requests.
"""

import hashlib
import json
import math
import re
import time
from urllib.parse import quote

from .elastic import ElasticClient, validate_index
from .errors import AnalyticsError


RESULT_MAPPING = {
    "mappings": {
        "dynamic": "strict",
        "_meta": {"analytics311_role": "trend-results", "schema_version": "1"},
        "properties": {
            **{field: {"type": "keyword"} for field in ("result_id", "nta2020", "nta_version", "dataset_version")},
            **{field: {"type": "long"} for field in ("baseline_count", "current_count", "absolute_change")},
            **{field: {"type": "double"} for field in ("relative_change", "rate_change")},
            "created_at": {"type": "date"},
        },
    }
}

METRIC_UNITS = {
    "baseline_count": "requests", "current_count": "requests", "absolute_change": "requests",
    "relative_change": "fraction of baseline count", "rate_change": "requests per calendar day",
}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _document_id(result_id, nta):
    return hashlib.sha256(_json([result_id, nta]).encode()).hexdigest()


def _verify_mapping(client, index):
    response = client.request("GET", f"/{quote(index, safe='')}/_mapping")
    if set(response) != {index}:
        raise AnalyticsError("invalid_configuration", "Trend results require a dedicated concrete index, not an alias")
    mapping = response[index].get("mappings", {}) if isinstance(response[index], dict) else {}
    if (mapping.get("_meta") != RESULT_MAPPING["mappings"]["_meta"] or mapping.get("dynamic") != "strict"):
        raise AnalyticsError("invalid_configuration", "Initialize the dedicated trend-result index with RESULT_MAPPING before publishing")
    actual = mapping.get("properties", {})
    for field, definition in RESULT_MAPPING["mappings"]["properties"].items():
        if actual.get(field, {}).get("type") != definition["type"]:
            raise AnalyticsError("invalid_configuration", f"Trend result index has incompatible mapping for {field}")


def _create_batch(client, index, documents):
    lines = []
    for identifier, document in documents:
        lines.extend((_json({"create": {"_id": identifier}}), _json(document)))
    response = client.request("POST", f"/{quote(index, safe='')}/_bulk?refresh=wait_for", "\n".join(lines) + "\n")
    items = response.get("items")
    if not isinstance(items, list) or len(items) != len(documents):
        raise AnalyticsError("partial_execution", "Trend publication returned an incomplete bulk response; no map link issued")
    for item, (identifier, document) in zip(items, documents):
        created = item.get("create", {}) if isinstance(item, dict) else {}
        if created.get("_id") != identifier or created.get("_index") != index:
            raise AnalyticsError("partial_execution", "Trend publication returned a mismatched document identity")
        if created.get("status") != 409 and (created.get("status") != 201 or created.get("_shards", {}).get("failed") != 0):
            raise AnalyticsError("partial_execution", "Trend publication failed for one or more groups; retry the same result after fixing the backend")
    # Verify new documents too: an administrator's ingest pipeline could have
    # transformed their contents despite an otherwise successful create response.
    expected = dict(documents)
    response = client.request("POST", f"/{quote(index, safe='')}/_mget", {"ids": list(expected)})
    found = response.get("docs")
    if not isinstance(found, list) or len(found) != len(expected):
        raise AnalyticsError("partial_execution", "Could not verify published trend documents")
    seen = set()
    for document in found:
        identifier = document.get("_id")
        if (identifier not in expected or identifier in seen or document.get("_index") != index
                or document.get("found") is not True or document.get("_source") != expected[identifier]):
            raise AnalyticsError("partial_execution", "A trend document conflicts with the saved result; publish a new analytical result")
        seen.add(identifier)


def publish_trend_map(service, saved, selected):
    """Create exact saved-group documents and a locator for their metric layer.

    A successful return confirms publication, not Kibana rendering or NTA joins.
    ``selected`` is None for all groups, otherwise a list of saved group rows.
    """
    spec = saved.get("spec", {})
    if service.config.get("backend") != "elastic":
        raise AnalyticsError("unsupported_operation", "Trend maps require a real immutable Elasticsearch dataset")
    if spec.get("operation") != "compare_periods" or spec.get("group_by") != [{"field": "nta2020"}]:
        raise AnalyticsError("unsupported_operation", "Trend maps require a period comparison grouped only by nta2020")
    if saved.get("execution_complete") is not True or saved.get("coverage_complete") is not True:
        raise AnalyticsError("coverage_gap", "Trend maps require a complete comparison with complete source coverage")
    config = service.config.get("kibana", {})
    for key in ("trend_map_id", "trend_data_view_id"):
        if not isinstance(config.get(key), str) or not config[key] or config[key].startswith("CONFIGURE_"):
            raise AnalyticsError("backend_unavailable", "Configure the NTA trend map and result data view before publishing")
    nta_version = service.manifest.get("geography", {}).get("nta_version")
    if not isinstance(nta_version, str) or not nta_version:
        raise AnalyticsError("unsupported_operation", "Trend maps require a manifest with the NTA boundary version")
    index = validate_index(config.get("result_index"))
    if index in {service.config.get("index"), service.manifest.get("index")}:
        raise AnalyticsError("invalid_configuration", "Trend result index must differ from the source request index")
    metric = config.get("trend_metric", "relative_change")
    if metric not in METRIC_UNITS:
        raise AnalyticsError("invalid_configuration", "Unsupported trend map metric")
    result_id = saved.get("result_id")
    if not isinstance(result_id, str) or not re.fullmatch(r"[0-9a-f]{32}", result_id):
        raise AnalyticsError("invalid_spec", "Trend publication requires a saved analytical result")
    rows = saved.get("all_rows", []) if selected is None else selected
    maximum = service.budgets.get("max_map_groups", 5000)
    if type(maximum) is not int or not 1 <= maximum <= 100_000:
        raise AnalyticsError("invalid_configuration", "max_map_groups must be an integer from 1 to 100000")
    if not isinstance(rows, list) or len(rows) > maximum:
        raise AnalyticsError("budget_exceeded", "Trend map exceeds the complete-group publication budget")
    if selected is not None:
        available = {row.get("group_id"): row for row in saved.get("all_rows", [])}
        if any(available.get(row.get("group_id")) != row for row in selected):
            raise AnalyticsError("invalid_spec", "Trend selection must consist of saved result groups")
    documents, ntas, seen, excluded = [], [], set(), 0
    for row in rows:
        nta = row.get("group", {}).get("nta2020")
        if nta is None:
            excluded += 1
            continue
        if not isinstance(nta, str) or not nta or len(nta) > 128 or nta in seen:
            raise AnalyticsError("invalid_spec", "Saved trend groups require unique, nonempty NTA identifiers")
        document = {"result_id": result_id, "nta2020": nta, "nta_version": nta_version,
                    "dataset_version": spec["dataset_version"], "created_at": saved["created_at"]}
        for field in METRIC_UNITS:
            value = row.get(field)
            if field in {"baseline_count", "current_count", "absolute_change"}:
                if type(value) is not int or (field != "absolute_change" and value < 0):
                    raise AnalyticsError("invalid_spec", "Saved comparison has invalid count metrics")
            elif value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise AnalyticsError("invalid_spec", "Saved comparison has non-finite metrics")
            document[field] = value
        documents.append((_document_id(result_id, nta), document))
        ntas.append(nta)
        seen.add(nta)
    seconds = service.budgets.get("deadline_seconds", 30)
    client = ElasticClient(service.config.get("elastic_url", "https://localhost:9200"),
                           allow_insecure_local=service.config.get("allow_insecure_local", False),
                           timeout=seconds, api_key_env="ELASTIC_ARTIFACT_API_KEY")
    deadline = time.monotonic() + seconds
    _verify_mapping(client, index)
    for start in range(0, len(documents), 500):
        if time.monotonic() > deadline:
            raise AnalyticsError("budget_exceeded", "Trend publication deadline exceeded; no map link issued")
        _create_batch(client, index, documents[start:start + 500])
    if time.monotonic() > deadline:
        raise AnalyticsError("budget_exceeded", "Trend publication deadline exceeded; no map link issued")
    selection = {"term": {"result_id": result_id}}
    if selected is not None:
        selection = {"bool": {"filter": [selection, {"terms": {"nta2020": ntas}} if ntas else {"match_none": {}}]}}
    scope = "all_matching" if selected is None else "selected_groups"
    locator = {"locatorId": "MAPS_APP_LOCATOR", "params": {
        "mapId": config["trend_map_id"], "query": {"language": "kuery", "query": ""},
        "timeRange": {"from": "1970-01-01T00:00:00.000Z", "to": "2100-01-01T00:00:00.000Z"},
        "filters": [{"meta": {"index": config["trend_data_view_id"], "disabled": False, "negate": False,
                                "alias": f"311 comparison {result_id} ({scope})"},
                     "$state": {"store": "appState"}, "query": selection}]}}
    return {"locator_request": locator, "result_index": index, "metric": metric, "metric_units": METRIC_UNITS[metric],
            "source_result_id": result_id, "source_dataset_version": spec["dataset_version"],
            "source_periods": spec["periods"], "source_snapshot_coverage": service.manifest.get("coverage"),
            "nta_version": nta_version, "published_group_count": len(documents), "mapped_group_count": len(documents),
            "excluded_group_count": excluded, "selected_nta_ids": ntas if selected is not None else None,
            "cohort_scope": scope, "group_ids": [row["group_id"] for row in rows] if selected is not None else None,
            "parity_verified": False,
            "warnings": ["Published groups have NTA identifiers; actual boundary joins and rendered feature counts remain unverified.",
                         "Configure the trend data view without a time field. The NTA join layer must honor result filters and style the declared metric.",
                         "Groups missing NTA identifiers are excluded. Relative change is null for a zero baseline."]}
