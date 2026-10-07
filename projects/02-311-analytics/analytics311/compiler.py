"""Compile normalized analytical requests to inspectable Elasticsearch DSL."""

from .contracts import FIELDS
from .errors import AnalyticsError


def _predicate(node):
    if "all" in node:
        return {"bool": {"filter": [_predicate(item) for item in node["all"]]}}
    if "any" in node:
        return {"bool": {"should": [_predicate(item) for item in node["any"]], "minimum_should_match": 1}}
    if "not" in node:
        return {"bool": {"must_not": [_predicate(node["not"])]}}
    field, op, value = node["field"], node["op"], node["value"]
    if op == "exists":
        exists = {"exists": {"field": field}}
        return exists if value else {"bool": {"must_not": [exists]}}
    return {{"eq": "term", "in": "terms", "range": "range"}[op]: {field: value}}


def compile_query(normalized_spec):
    """Selection only, reusable by analysis, record export, and map adapters."""
    spec = normalized_spec
    clauses = []
    if "time" in spec:
        time = spec["time"]
        clauses.append({"range": {time["field"]: {key: time[key] for key in ("gte", "lt")}}})
    if "periods" in spec:
        clauses.append({"bool": {"should": [
            {"range": {"created_date": bounds}} for bounds in spec["periods"].values()
        ], "minimum_should_match": 1}})
    if "filters" in spec:
        clauses.append(_predicate(spec["filters"]))
    if "geo" in spec:
        geo = spec["geo"]
        if geo["type"] == "radius":
            clauses.append({"geo_distance": {"distance": f'{geo["distance_m"]}m',
                                               "location": {key: geo[key] for key in ("lat", "lon")}}})
        elif geo["type"] == "bbox":
            clauses.append({"geo_bounding_box": {"location": {
                key: geo[key] for key in ("top_left", "bottom_right")}}})
        else:
            clauses.append({"geo_polygon": {"location": {"points": geo["points"]}}})
    return {"bool": {"filter": clauses}} if clauses else {"match_all": {}}


def _metric_aggs(metrics):
    aggregations = {}
    for metric in metrics:
        if metric in ("closed_count", "open_count"):
            aggregations[metric] = {"filter": {"term": {"is_closed": metric == "closed_count"}}}
        elif metric == "mean_closure_hours":
            aggregations[metric] = {"avg": {"field": "closure_hours"}}
        elif metric in ("median_closure_hours", "p90_closure_hours"):
            aggregations[metric] = {"percentiles": {"field": "closure_hours", "keyed": True,
                                      "percents": [50 if metric == "median_closure_hours" else 90]}}
    return aggregations


def compile_search(normalized_spec, after_key=None, page_size=500):
    """Build one page. Composite results must all be read before top-N ranking."""
    spec = normalized_spec
    if spec["operation"] == "compare_periods":
        raise AnalyticsError("unsupported_operation", "Compile comparison periods as separate aggregate requests")
    if type(page_size) is not int or not 1 <= page_size <= 5000:
        raise AnalyticsError("invalid_spec", "page_size must be an integer from 1 to 5000")
    body = {"query": compile_query(spec), "track_total_hits": True}
    if spec["operation"] == "records":
        body.update(size=spec["preview_limit"], _source=list(FIELDS),
                    sort=[{"created_date": {"order": "asc", "missing": "_last"}}, {"unique_key": "asc"}])
        if after_key is not None:
            if not isinstance(after_key, list):
                raise AnalyticsError("invalid_spec", "Record after_key must be a search_after array")
            body["search_after"] = after_key
        return body
    body["size"] = 0
    metrics = _metric_aggs(spec["metrics"])
    if spec["group_by"]:
        sources = []
        for group in spec["group_by"]:
            field = group["field"]
            if FIELDS[field] == "date":
                definition = {"date_histogram": {"field": field, "calendar_interval": group["interval"],
                              "time_zone": spec["timezone"], "format": "strict_date_time"}}
            else:
                definition = {"terms": {"field": field, "missing_bucket": True}}
            sources.append({field: definition})
        composite = {"size": page_size, "sources": sources}
        if after_key is not None:
            if not isinstance(after_key, dict):
                raise AnalyticsError("invalid_spec", "Aggregate after_key must be an object")
            composite["after"] = after_key
        groups = {"composite": composite}
        if metrics:
            groups["aggs"] = metrics
        body["aggs"] = {"groups": groups}
    elif metrics:
        body["aggs"] = metrics
    return body
