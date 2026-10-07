"""Validate effective resource limits and snapshot declarations before execution."""
from datetime import datetime

from .errors import AnalyticsError


# default, minimum, maximum; limits are deliberately explicit, never auto-sized.
BUDGETS = {
    "max_fixture_rows": (100000, 1, 1000000),
    "max_groups": (50000, 1, 1000000),
    "page_size": (500, 1, 5000),
    "deadline_seconds": (30, 1, 3600),
    "max_preview_rows": (100, 1, 100),
    "max_filter_depth": (12, 1, 50),
    "max_filter_nodes": (100, 1, 10000),
    "max_filter_values": (1000, 1, 10000),
    "max_polygon_points": (100, 3, 1000),
    "max_export_rows": (1000000, 1, 1000000000000),
    "max_export_bytes": (268435456, 1, 1000000000000000),
    "export_deadline_seconds": (300, 1, 86400),
    "max_concurrent_exports": (2, 1, 64),
    "max_map_groups": (5000, 1, 100000),
}


def effective_budgets(value):
    if not isinstance(value, dict) or set(value) - BUDGETS.keys():
        raise AnalyticsError("invalid_configuration", "budgets must contain only documented resource limits")
    result = {}
    for key, (default, low, high) in BUDGETS.items():
        number = value.get(key, default)
        if type(number) is not int or not low <= number <= high:
            raise AnalyticsError("invalid_configuration", f"{key} must be an integer from {low} to {high}")
        result[key] = number
    return result


def validate_manifest(value):
    if not isinstance(value, dict) or not isinstance(value.get("dataset_version"), str) or not 1 <= len(value["dataset_version"]) <= 128:
        raise AnalyticsError("invalid_configuration", "Manifest needs a nonempty dataset_version of at most 128 characters")
    if "row_count" in value and (type(value["row_count"]) is not int or value["row_count"] < 0):
        raise AnalyticsError("invalid_configuration", "Manifest row_count must be a nonnegative integer")
    coverage = value.get("coverage", {})
    if not isinstance(coverage, dict) or type(coverage.get("complete", False)) is not bool:
        raise AnalyticsError("invalid_configuration", "coverage.complete must be a boolean, never a string or number")
    if coverage.get("complete") or "gte" in coverage or "lt" in coverage:
        try:
            dates = []
            for key in ("gte", "lt"):
                raw = coverage[key]
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if "T" not in raw or dt.tzinfo is None or dt.utcoffset() is None:
                    raise ValueError()
                dates.append(dt)
            if dates[0] >= dates[1]:
                raise ValueError()
        except (KeyError, AttributeError, TypeError, ValueError, OverflowError):
            raise AnalyticsError("invalid_configuration", "Manifest coverage requires ordered, offset-aware gte/lt timestamps") from None
    if "warnings" in value and (not isinstance(value["warnings"], list) or any(not isinstance(v, str) for v in value["warnings"])):
        raise AnalyticsError("invalid_configuration", "Manifest warnings must be a list of strings")
