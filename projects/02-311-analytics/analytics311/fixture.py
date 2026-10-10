"""Bounded, exact reference execution for authored development fixtures.

This intentionally scans JSONL. Its limits prevent it being mistaken for a
replacement for Elasticsearch or evidence of production-scale performance.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .errors import AnalyticsError
from .contracts import DEFAULT_PREVIEW_ROWS, validate_source_fields


MAX_LINE_BYTES = 10 * 1024 * 1024


def _instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Dates require an explicit UTC offset")
    return parsed.astimezone(timezone.utc)


def _value(record, field):
    return record.get(field)


def _predicate(record, predicate):
    """Compatibility helper; scans prepare the predicate once, before reading."""
    return _prepare_predicate(predicate)(record)


def _prepare_predicate(predicate):
    """Bind immutable query operands to this execution, never to a global cache."""
    if not predicate:
        return lambda record: True
    if "all" in predicate:
        children = tuple(_prepare_predicate(item) for item in predicate["all"])
        return lambda record: all(child(record) for child in children)
    if "any" in predicate:
        children = tuple(_prepare_predicate(item) for item in predicate["any"])
        return lambda record: any(child(record) for child in children)
    if "not" in predicate:
        child = _prepare_predicate(predicate["not"])
        return lambda record: not child(record)
    field, op = predicate["field"], predicate["op"]
    wanted = predicate["value"]
    is_date = field in {"created_date", "closed_date"}
    if op == "exists":
        return lambda record: (record.get(field) is not None) == wanted
    if op == "eq":
        wanted = _instant(wanted) if is_date else wanted
        compare = lambda actual: actual == wanted
    elif op == "in":
        wanted = frozenset(_instant(value) for value in wanted) if is_date else frozenset(wanted)
        compare = lambda actual: actual in wanted
    elif op == "range":
        bounds = tuple((bound, _instant(value) if is_date else value) for bound, value in wanted.items())

        def compare(actual):
            for bound, value in bounds:
                if bound == "gte" and actual < value:
                    return False
                if bound == "gt" and actual <= value:
                    return False
                if bound == "lt" and actual >= value:
                    return False
                if bound == "lte" and actual > value:
                    return False
            return True
    else:
        raise AnalyticsError("unsupported_operation", f"Unsupported fixture predicate: {op}")

    def matches(record):
        actual = record.get(field)
        return actual is not None and compare(_instant(actual) if is_date else actual)

    return matches


def _haversine(lat1, lon1, lat2, lon2):
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    dlat = lat2 - lat1
    dlon = math.radians(lon2 - lon1)
    square = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_008.7714 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, square))))


def _inside_polygon(lat, lon, points):
    vertices, center = _prepare_polygon(points)
    return _inside_prepared_polygon(lat, lon, vertices, center)


def _prepare_polygon(points):
    # Unwrap consecutive longitudes so a polygon crossing +/-180 remains local.
    vertices = []
    previous = points[0]["lon"]
    for point in points:
        x = point["lon"]
        while x - previous > 180:
            x -= 360
        while x - previous < -180:
            x += 360
        vertices.append((x, point["lat"]))
        previous = x
    center = sum(x for x, _ in vertices) / len(vertices)
    return tuple(vertices), center


def _inside_prepared_polygon(lat, lon, vertices, center):
    lon += 360 * round((center - lon) / 360)
    inside = False
    for i, (x1, y1) in enumerate(vertices):
        x2, y2 = vertices[(i + 1) % len(vertices)]
        cross = (lon - x1) * (y2 - y1) - (lat - y1) * (x2 - x1)
        if abs(cross) <= 1e-10 and min(x1, x2) - 1e-10 <= lon <= max(x1, x2) + 1e-10 and min(y1, y2) - 1e-10 <= lat <= max(y1, y2) + 1e-10:
            return True
        if (y1 > lat) != (y2 > lat):
            crossing = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < crossing:
                inside = not inside
    return inside


def _geo_matches(record, geo):
    return _prepare_geo(geo)(record)


def _prepare_geo(geo):
    if not geo:
        return lambda record: True
    if geo["type"] == "radius":
        center_lat, center_lon, distance = geo["lat"], geo["lon"], geo["distance_m"]
        compare = lambda lat, lon: _haversine(lat, lon, center_lat, center_lon) <= distance
    elif geo["type"] == "bbox":
        top, bottom = geo["top_left"], geo["bottom_right"]
        north, west, south, east = top["lat"], top["lon"], bottom["lat"], bottom["lon"]

        def compare(lat, lon):
            longitude = west <= lon <= east if west <= east else lon >= west or lon <= east
            return south <= lat <= north and longitude
    elif geo["type"] == "polygon":
        vertices, center = _prepare_polygon(geo["points"])
        compare = lambda lat, lon: _inside_prepared_polygon(lat, lon, vertices, center)
    else:
        raise AnalyticsError("unsupported_operation", "Unsupported fixture geometry")

    def matches(record):
        point = record.get("location")
        return bool(point) and compare(point["lat"], point["lon"])

    return matches


def _bucket_start(instant, interval, zone):
    local = instant.astimezone(zone)
    local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if interval == "week":
        local -= timedelta(days=local.weekday())
    elif interval == "month":
        local = local.replace(day=1)
    return local


def _percentile(values, fraction):
    return _sorted_percentile(sorted(values), fraction)


def _sorted_percentile(values, fraction):
    if not values:
        return None
    index = (len(values) - 1) * fraction
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


class FixtureBackend:
    """Exact small-data oracle; always bounded by scan, group and time budgets."""

    def __init__(self, config, catalog, manifest):
        self.config, self.catalog, self.manifest = config, catalog, manifest
        self.path = Path(config.get("fixture_path", Path(__file__).resolve().parents[1] / "fixtures" / "requests.jsonl"))
        self.budgets = config.get("budgets", config.get("limits", {}))
        self.max_rows = self.budgets.get("max_fixture_rows", 100_000)
        self.max_groups = self.budgets.get("max_groups", 50_000)
        self.deadline_seconds = self.budgets.get("deadline_seconds", 30)

    def iter_records(self, spec, *, deadline=None, source_fields=None):
        """Stream the full selected cohort, rejecting an oversized source."""
        source_fields = validate_source_fields(source_fields)
        deadline = time.monotonic() + self.deadline_seconds if deadline is None else deadline
        bounds = spec.get("time")
        lower, upper = (_instant(bounds["gte"]), _instant(bounds["lt"])) if bounds else (None, None)
        periods = [(_instant(period["gte"]), _instant(period["lt"])) for period in spec.get("periods", {}).values()]
        count = 0
        try:
            predicate = _prepare_predicate(spec.get("filters"))
            geometry = _prepare_geo(spec.get("geo"))
            with self.path.open("rb") as source:
                while True:
                    if time.monotonic() > deadline:
                        raise AnalyticsError("budget_exceeded", "Fixture execution exceeded its deadline")
                    line = source.readline(MAX_LINE_BYTES + 1)
                    if len(line) > MAX_LINE_BYTES:
                        raise AnalyticsError("budget_exceeded", "Fixture JSONL line exceeds the 10 MiB limit")
                    if not line:
                        break
                    if not line.strip():
                        continue
                    count += 1
                    if count > self.max_rows:
                        raise AnalyticsError("budget_exceeded", f"Fixture scan exceeds {self.max_rows} records; use Elasticsearch for larger datasets")
                    record = json.loads(line.decode("utf-8"))
                    if not isinstance(record, dict):
                        raise ValueError("A normalized record must be an object")
                    if bounds:
                        value = record.get(bounds["field"])
                        if value is None or not lower <= _instant(value) < upper:
                            continue
                    if periods:
                        created = _instant(record["created_date"])
                        if not any(start <= created < end for start, end in periods):
                            continue
                    if predicate(record) and geometry(record):
                        yield record if source_fields is None else {field: record[field] for field in source_fields if field in record}
        except AnalyticsError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
            raise AnalyticsError("backend_unavailable", "Fixture is missing or contains invalid normalized records") from exc

    def execute(self, spec, *, deadline=None):
        deadline = time.monotonic() + self.deadline_seconds if deadline is None else deadline
        warnings = ["Synthetic bounded fixture; results are development evidence, not NYC findings or scale measurements."]
        if spec["operation"] == "records":
            rows, total = [], 0
            for record in self.iter_records(spec, deadline=deadline):
                total += 1
                if len(rows) < spec.get("preview_limit", DEFAULT_PREVIEW_ROWS):
                    rows.append(record)
            if time.monotonic() > deadline:
                raise AnalyticsError("budget_exceeded", "Fixture execution exceeded its deadline")
            return {"rows": rows, "total": total, "approximate": False, "warnings": warnings}
        if spec["operation"] != "aggregate":
            raise AnalyticsError("unsupported_operation", "Fixture backend expects records or aggregate; period comparison is orchestrated by the service")
        grouping = spec.get("group_by", [])
        metrics = spec.get("metrics", ["count"])
        need_durations = bool(set(metrics) & {"mean_closure_hours", "median_closure_hours", "p90_closure_hours"})
        need_percentiles = bool(set(metrics) & {"median_closure_hours", "p90_closure_hours"})
        need_closed = need_durations or bool(set(metrics) & {"closed_count", "open_count"})
        zone = ZoneInfo(spec.get("timezone", "America/New_York"))
        date_groups = [(i, group) for i, group in enumerate(grouping) if "interval" in group]
        if len(date_groups) > 1:
            raise AnalyticsError("unsupported_operation", "Only one calendar grouping is supported")
        if date_groups and (not spec.get("time") or date_groups[0][1]["field"] != spec["time"]["field"]):
            raise AnalyticsError("unsupported_operation", "Calendar grouping requires a time window on the same field")
        accumulators = {}
        total = 0

        def accumulator(key):
            if key not in accumulators:
                if len(accumulators) >= self.max_groups:
                    raise AnalyticsError("budget_exceeded", "Fixture aggregation exceeds the complete-group budget")
                accumulators[key] = {"count": 0, "closed_count": 0, "durations": [] if need_durations else None}
            return accumulators[key]

        for record in self.iter_records(spec, deadline=deadline):
            total += 1
            key = []
            for group in grouping:
                value = record.get(group["field"])
                if "interval" in group and value is not None:
                    value = _bucket_start(_instant(value), group["interval"], zone).isoformat()
                key.append(value)
            current = accumulator(tuple(key))
            current["count"] += 1
            if need_closed:
                closed = record.get("is_closed") is True
                current["closed_count"] += closed
                if need_durations and closed:
                    duration = record.get("closure_hours")
                    if isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0:
                        current["durations"].append(duration)
        if not grouping:
            accumulator(())
        # The service fills calendar domains once, identically for both backends.
        # This executor returns observed groups, including explicit null buckets.
        rows = []
        for key, values in accumulators.items():
            if time.monotonic() > deadline:
                raise AnalyticsError("budget_exceeded", "Fixture execution exceeded its deadline")
            durations = values["durations"]
            mean = math.fsum(durations) / len(durations) if "mean_closure_hours" in metrics and durations else None
            if need_percentiles:
                durations.sort()
            row = {"group": {group["field"]: value for group, value in zip(grouping, key)}, "count": values["count"]}
            for metric in metrics:
                if metric == "count":
                    continue
                if metric == "closed_count":
                    row[metric] = values["closed_count"]
                elif metric == "open_count":
                    row[metric] = values["count"] - values["closed_count"]
                elif metric == "mean_closure_hours":
                    row[metric] = mean
                elif metric == "median_closure_hours":
                    row[metric] = _sorted_percentile(durations, 0.5)
                elif metric == "p90_closure_hours":
                    row[metric] = _sorted_percentile(durations, 0.9)
                else:
                    raise AnalyticsError("unsupported_operation", f"Unsupported fixture metric: {metric}")
            rows.append(row)
        if time.monotonic() > deadline:
            raise AnalyticsError("budget_exceeded", "Fixture execution exceeded its deadline")
        return {"rows": rows, "total": total, "approximate": False, "warnings": warnings}
