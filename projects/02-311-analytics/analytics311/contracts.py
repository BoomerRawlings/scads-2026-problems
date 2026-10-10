"""Versioned, provider-neutral request validation; no query code is accepted."""

from datetime import datetime, timezone
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import AnalyticsError


FIELDS = {
    **dict.fromkeys(("unique_key", "complaint_type", "descriptor", "agency", "agency_name",
                    "status", "borough", "incident_zip", "nta2020", "ntaname",
                    "community_board", "council_district", "police_precinct"), "keyword"),
    "created_date": "date", "closed_date": "date", "closure_hours": "number",
    "is_closed": "boolean", "location": "geo",
}
METRICS = ("count", "closed_count", "open_count", "mean_closure_hours",
           "median_closure_hours", "p90_closure_hours")
DEFAULT_PREVIEW_ROWS = 5
_KEYS = {"schema_version", "dataset_version", "operation", "timezone", "as_of", "time",
         "filters", "geo", "group_by", "metrics", "periods", "preview_limit", "top_n",
         "rank_by", "rank_order", "minimum_count"}


def _error(message, code="invalid_spec"):
    raise AnalyticsError(code, message)


def validate_source_fields(value):
    """Accept only an explicit projection of known fields; None keeps all fields."""
    if value is None:
        return None
    if (not isinstance(value, list) or not value
            or any(not isinstance(field, str) or field not in FIELDS for field in value)
            or len(set(value)) != len(value)):
        _error("source_fields must be a nonempty list of unique known fields")
    return list(value)


def _object(value, allowed, label, required=()):
    if not isinstance(value, dict):
        _error(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        _error(f"{label} keys must be strings")
    unexpected = set(value) - set(allowed)
    missing = set(required) - set(value)
    if unexpected:
        _error(f"Unknown {label} keys: {', '.join(sorted(unexpected))}")
    if missing:
        _error(f"Missing {label} keys: {', '.join(sorted(missing))}")


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        _error(f"{label} must be an integer from {low} to {high}")
    return value


def _number(value, label):
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        _error(f"{label} must be a finite number")
    return value


def _text(value, label, maximum=512):
    if not isinstance(value, str) or not value or len(value) > maximum:
        _error(f"{label} must be a nonempty string (maximum {maximum} characters)")
    return value


def _date(value, label):
    _text(value, label, 100)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if "T" not in value or parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        _error(f"{label} must be an ISO 8601 timestamp with an explicit offset")


def _bounds(value, label):
    _object(value, {"gte", "lt"}, label, {"gte", "lt"})
    normalized = {key: _date(value[key], f"{label}.{key}") for key in ("gte", "lt")}
    if datetime.fromisoformat(normalized["gte"]) >= datetime.fromisoformat(normalized["lt"]):
        _error(f"{label}.gte must precede {label}.lt")
    return normalized


def _typed(value, field):
    kind = FIELDS[field]
    if kind == "keyword":
        return _text(value, f"{field} value")
    if kind == "number":
        return _number(value, f"{field} value")
    if kind == "boolean":
        if type(value) is not bool:
            _error(f"{field} value must be a boolean")
        return value
    if kind == "date":
        return _date(value, f"{field} value")
    _error("Use the geo property for location filters", "unsupported_operation")


def _filters(value, catalog, limits, counter, depth=0):
    if depth > limits.get("max_filter_depth", 12):
        _error("Filter nesting exceeds max_filter_depth", "budget_exceeded")
    counter[0] += 1
    if counter[0] > limits.get("max_filter_nodes", 100):
        _error("Filter tree exceeds max_filter_nodes", "budget_exceeded")
    _object(value, {"all", "any", "not", "field", "op", "value", "category_family"}, "filter")
    for boolean in ("all", "any", "not"):
        if boolean in value:
            _object(value, {boolean}, "boolean filter")
            if boolean == "not":
                return {boolean: _filters(value[boolean], catalog, limits, counter, depth + 1)}
            if not isinstance(value[boolean], list) or not value[boolean]:
                _error(f"{boolean} must contain a nonempty filter list")
            return {boolean: [_filters(item, catalog, limits, counter, depth + 1)
                              for item in value[boolean]]}
    if "category_family" in value:
        _object(value, {"category_family"}, "category family filter")
        family = _text(value["category_family"], "category_family")
        expansion = catalog.get("families", {}).get(family)
        if not isinstance(expansion, list) or not expansion:
            _error(f"Unknown category family {family!r}; inspect the catalog", "needs_clarification")
        value = {"field": "complaint_type", "op": "in", "value": expansion}
    _object(value, {"field", "op", "value"}, "predicate", {"field", "op", "value"})
    field = _text(value["field"], "field")
    if field not in FIELDS:
        _error(f"Unknown field: {field}")
    op = value["op"]
    if not isinstance(op, str) or op not in {"eq", "in", "range", "exists"}:
        _error("Filter op must be eq, in, range, or exists")
    operand = value["value"]
    if op == "exists":
        if type(operand) is not bool:
            _error("exists value must be true or false")
    elif op == "in":
        if not isinstance(operand, list) or not operand:
            _error("in value must be a nonempty array")
        if len(operand) > limits.get("max_filter_values", 1000):
            _error("in filter exceeds max_filter_values", "budget_exceeded")
        operand = list(dict.fromkeys(_typed(item, field) for item in operand))
    elif op == "range":
        if FIELDS[field] not in {"date", "number"}:
            _error("range is supported only for date and numeric fields")
        _object(operand, {"gt", "gte", "lt", "lte"}, "range")
        if not operand or ({"gt", "gte"} <= operand.keys()) or ({"lt", "lte"} <= operand.keys()):
            _error("range requires bounds, with at most one lower and one upper bound")
        operand = {key: _typed(item, field) for key, item in operand.items()}
        lower = operand.get("gte", operand.get("gt"))
        upper = operand.get("lte", operand.get("lt"))
        if lower is not None and upper is not None:
            if FIELDS[field] == "date":
                lower, upper = datetime.fromisoformat(lower), datetime.fromisoformat(upper)
            if lower > upper or (lower == upper and ("gt" in operand or "lt" in operand)):
                _error("range lower bound must not exceed upper bound or form an empty interval")
    else:
        operand = _typed(operand, field)
    return {"field": field, "op": op, "value": operand}


def _point(value, label):
    _object(value, {"lat", "lon"}, label, {"lat", "lon"})
    lat, lon = _number(value["lat"], f"{label}.lat"), _number(value["lon"], f"{label}.lon")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        _error(f"{label} coordinates are outside latitude/longitude bounds")
    return {"lat": lat, "lon": lon}


def _cross(a, b, c):
    return ((b["lon"] - a["lon"]) * (c["lat"] - a["lat"])
            - (b["lat"] - a["lat"]) * (c["lon"] - a["lon"]))


def _intersects(a, b, c, d):
    if (max(a["lon"], b["lon"]) < min(c["lon"], d["lon"])
            or max(c["lon"], d["lon"]) < min(a["lon"], b["lon"])
            or max(a["lat"], b["lat"]) < min(c["lat"], d["lat"])
            or max(c["lat"], d["lat"]) < min(a["lat"], b["lat"])):
        return False
    return _cross(a, b, c) * _cross(a, b, d) <= 0 and _cross(c, d, a) * _cross(c, d, b) <= 0


def _geo(value, limits):
    if not isinstance(value, dict):
        _error("geo must be an object")
    kind = value.get("type")
    if kind == "radius":
        _object(value, {"type", "lat", "lon", "distance_m"}, "geo", {"lat", "lon", "distance_m"})
        point = _point({key: value[key] for key in ("lat", "lon")}, "geo center")
        distance = _number(value["distance_m"], "distance_m")
        if not 0 < distance <= 20_040_000:
            _error("distance_m must be positive and no greater than 20040000")
        return {"type": kind, **point, "distance_m": distance}
    if kind == "bbox":
        _object(value, {"type", "top_left", "bottom_right"}, "geo", {"top_left", "bottom_right"})
        left, right = _point(value["top_left"], "top_left"), _point(value["bottom_right"], "bottom_right")
        if left["lat"] <= right["lat"] or left["lon"] >= right["lon"]:
            _error("bbox requires north-west top_left and south-east bottom_right; dateline crossing unsupported")
        return {"type": kind, "top_left": left, "bottom_right": right}
    if kind == "polygon":
        _object(value, {"type", "points"}, "geo", {"points"})
        points = value["points"]
        maximum = limits.get("max_polygon_points", 100)
        if not isinstance(points, list) or not 3 <= len(points) <= maximum + 1:
            _error("polygon requires 3 to max_polygon_points vertices")
        points = [_point(point, "polygon point") for point in points]
        if points[0] == points[-1]:
            points.pop()
        if len(points) > maximum:
            _error("polygon exceeds max_polygon_points", "budget_exceeded")
        if len({(point["lat"], point["lon"]) for point in points}) != len(points) or len(points) < 3:
            _error("polygon requires at least three distinct, nonrepeated vertices")
        if max(point["lon"] for point in points) - min(point["lon"] for point in points) > 180:
            _error("Dateline-crossing polygons are unsupported", "unsupported_operation")
        edges = list(zip(points, points[1:] + points[:1]))
        area = sum(a["lon"] * b["lat"] - b["lon"] * a["lat"] for a, b in edges)
        if abs(area) < 1e-12:
            _error("polygon must have nonzero area")
        for i, (a, b) in enumerate(edges):
            for j in range(i + 1, len(edges)):
                if j == i + 1 or (i == 0 and j == len(edges) - 1):
                    continue
                if _intersects(a, b, *edges[j]):
                    _error("polygon edges must not intersect")
        return {"type": kind, "points": points + points[:1]}
    _error("geo.type must be radius, bbox, or polygon")


def normalize_spec(spec: dict, catalog: dict, limits: dict | None = None) -> dict:
    """Return a detached, canonical request or a stable AnalyticsError.

    Absolute dates normalize to UTC. Calendar interpretation remains governed by
    timezone; last_month uses as_of, never a snapshot's latest available date.
    """
    limits = limits or {}
    _object(spec, _KEYS, "request", {"dataset_version", "operation"})
    if spec.get("schema_version", "1") != "1":
        _error("Only schema_version '1' is supported")
    operation = spec["operation"]
    if not isinstance(operation, str) or operation not in {"records", "aggregate", "compare_periods"}:
        _error("operation must be records, aggregate, or compare_periods")
    tz_name = _text(spec.get("timezone", "America/New_York"), "timezone", 100)
    try:
        zone = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        _error("timezone must be an installed IANA timezone (install tzdata if unavailable)")
    normalized = {
        "schema_version": "1",
        "dataset_version": _text(spec["dataset_version"], "dataset_version", 128),
        "operation": operation,
        "timezone": tz_name,
        "as_of": _date(spec.get("as_of", datetime.now(timezone.utc).isoformat()), "as_of"),
    }
    if "time" in spec:
        time = spec["time"]
        _object(time, {"field", "gte", "lt", "preset"}, "time")
        field = time.get("field", "created_date")
        if field not in ("created_date", "closed_date"):
            _error("time.field must be created_date or closed_date")
        if "preset" in time:
            _object(time, {"field", "preset"}, "time preset")
            if time["preset"] != "last_month":
                _error("Only the last_month time preset is supported", "unsupported_operation")
            try:
                anchor = datetime.fromisoformat(normalized["as_of"]).astimezone(zone)
            except (OverflowError, ValueError):
                _error("as_of falls outside supported local calendar years")
            end = datetime(anchor.year, anchor.month, 1, tzinfo=zone)
            if anchor.year == 1 and anchor.month == 1:
                _error("last_month falls outside supported calendar years")
            start = datetime(anchor.year - (anchor.month == 1), (anchor.month - 2) % 12 + 1, 1, tzinfo=zone)
            bounds = _bounds({"gte": start.isoformat(), "lt": end.isoformat()}, "time")
        else:
            bounds = _bounds({key: value for key, value in time.items() if key != "field"}, "time")
        normalized["time"] = {"field": field, **bounds}
    if "filters" in spec:
        normalized["filters"] = _filters(spec["filters"], catalog, limits, [0])
    if "geo" in spec:
        normalized["geo"] = _geo(spec["geo"], limits)
    groups = spec.get("group_by", [])
    if not isinstance(groups, list) or len(groups) > 3:
        _error("group_by must be an array of at most three dimensions")
    normalized["group_by"] = []
    seen, date_groups = set(), []
    for group in groups:
        _object(group, {"field", "interval"}, "group_by dimension", {"field"})
        field = _text(group["field"], "group_by field")
        if field not in FIELDS or FIELDS[field] not in {"keyword", "date", "boolean"}:
            _error(f"Unsupported grouping field: {field}", "unsupported_operation")
        if field in seen:
            _error("group_by fields must be unique")
        seen.add(field)
        if FIELDS[field] == "date":
            if group.get("interval") not in ("day", "week", "month"):
                _error("Date groups require day, week, or month interval")
            date_groups.append(field)
        elif "interval" in group:
            _error("interval is valid only for date groupings")
        normalized["group_by"].append(dict(group))
    if date_groups:
        if len(date_groups) > 1 or normalized.get("time", {}).get("field") != date_groups[0]:
            _error("Use one date grouping with a bounded time filter on the same field", "unsupported_operation")
    metrics = spec.get("metrics", ["count"])
    if not isinstance(metrics, list) or not metrics or any(not isinstance(m, str) or m not in METRICS for m in metrics):
        _error(f"metrics must be a nonempty array from: {', '.join(METRICS)}")
    if len(set(metrics)) != len(metrics):
        _error("metrics must not contain duplicates")
    normalized["metrics"] = list(metrics)
    if operation == "records" and (groups or metrics != ["count"]):
        _error("records does not accept groupings or aggregate metrics", "unsupported_operation")
    if operation == "compare_periods":
        if "time" in spec or date_groups:
            _error("compare_periods uses periods, with keyword groupings only", "unsupported_operation")
        _object(spec.get("periods"), {"baseline", "current"}, "periods", {"baseline", "current"})
        periods = {name: _bounds(spec["periods"][name], f"periods.{name}") for name in ("baseline", "current")}
        baseline, current = periods["baseline"], periods["current"]
        if (max(datetime.fromisoformat(baseline["gte"]), datetime.fromisoformat(current["gte"]))
                < min(datetime.fromisoformat(baseline["lt"]), datetime.fromisoformat(current["lt"]))):
            _error("Comparison periods must not overlap")
        normalized["periods"] = periods
    elif "periods" in spec:
        _error("periods is valid only for compare_periods")
    if operation == "records":
        if "minimum_count" in spec:
            _error("minimum_count is valid only for aggregate or compare_periods", "unsupported_operation")
    else:
        normalized["minimum_count"] = _integer(spec.get("minimum_count", 0), 0, 1_000_000, "minimum_count")
    normalized["preview_limit"] = _integer(spec.get("preview_limit", min(DEFAULT_PREVIEW_ROWS, limits.get("max_preview_rows", 100))), 1,
                                           min(100, limits.get("max_preview_rows", 100)), "preview_limit")
    normalized["top_n"] = _integer(spec.get("top_n", 20), 1, 100, "top_n")
    ranking = spec.get("rank_by", "absolute_change" if operation == "compare_periods" else "count")
    ranks = {"count", "absolute_change", "relative_change", "rate_change"} if operation == "compare_periods" else {"count"}
    if not isinstance(ranking, str) or ranking not in ranks:
        _error(f"rank_by must be one of: {', '.join(sorted(ranks))}")
    normalized["rank_by"] = ranking
    order = spec.get("rank_order", "desc")
    if order not in ("asc", "desc"):
        _error("rank_order must be asc or desc")
    normalized["rank_order"] = order
    return normalized
