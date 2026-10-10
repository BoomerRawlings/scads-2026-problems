"""Compact request-building guidance for any tool-using agent."""

from .contracts import DEFAULT_PREVIEW_ROWS, FIELDS, METRICS
from .errors import AnalyticsError


def analysis_guide(dataset_version):
    """Return detached JSON-compatible rules and syntactically valid requests."""
    if not isinstance(dataset_version, str) or not dataset_version or len(dataset_version) > 128:
        raise AnalyticsError("invalid_spec", "analysis_guide requires a nonempty dataset version of at most 128 characters")
    common = {"schema_version": "1", "dataset_version": dataset_version,
              "timezone": "America/New_York", "as_of": "2026-01-02T12:00:00-05:00"}
    return {
        "schema_version": "1",
        "workflow": ["describe_dataset", "validate_analysis", "run_analysis", "get_result", "export_csv or create_map_link"],
        "rules": {
            "required": ["dataset_version", "operation"],
            "unknown_keys": "rejected; do not submit raw Elasticsearch DSL",
            "dataset_version": dataset_version,
            "operation": {
                "records": "Matching requests; no group_by, aggregate metrics, or minimum_count.",
                "aggregate": "Counts/metrics; empty group_by computes one overall group.",
                "compare_periods": "Two non-overlapping creation-date periods; use periods instead of time; no date grouping.",
            },
            "fields": dict(FIELDS),
            "dates": {
                "format": "ISO 8601 datetime with explicit offset; normalized to UTC",
                "bounds": {"gte": "inclusive start", "lt": "exclusive end"},
                "timezone": "IANA timezone; default America/New_York; governs calendar buckets and exposure days",
                "as_of": "Defaults to request time; anchors relative dates, not snapshot history or a data cutoff",
                "time": {"field": ["created_date", "closed_date"], "forms": [
                    {"field": "created_date", "gte": "2025-12-01T00:00:00-05:00", "lt": "2026-01-01T00:00:00-05:00"},
                    {"field": "created_date", "preset": "last_month"},
                ]},
                "last_month": "Previous complete calendar month relative to as_of; do not anchor to latest dataset record",
                "periods": {"baseline": "{gte, lt}", "current": "{gte, lt}"},
                "coverage": "Comparisons and date histograms require complete declared coverage or a validated comparison_qualification for a reconciled observed snapshot. Disclose comparison_scope and warnings; observed reporting growth is not proof of worsening underlying conditions. Unobserved dates are not zero counts",
            },
            "filters": {
                "combine": {"all": "nonempty array of filters", "any": "nonempty array of filters", "not": "one filter"},
                "predicate": {"field": "known field", "op": ["eq", "in", "range", "exists"], "value": "typed operand"},
                "eq": "One exact typed value; keyword matching is case-sensitive",
                "in": "Nonempty array of exact typed values",
                "range": "Date/number only; value has gt or gte and/or lt or lte",
                "exists": "Boolean value; false selects missing fields; null is not an equality value",
                "category_family": "{category_family: name}; use catalog.families; expands approved complaint_type values",
                "limits": "Use describe_dataset.limits for filter depth/node/value budgets",
            },
            "geo": {
                "forms": [
                    {"type": "radius", "lat": 40.68, "lon": -73.95, "distance_m": 1500},
                    {"type": "bbox", "top_left": {"lat": 40.75, "lon": -74.0}, "bottom_right": {"lat": 40.60, "lon": -73.85}},
                    {"type": "polygon", "points": [{"lat": 40.65, "lon": -73.98}, {"lat": 40.72, "lon": -73.98}, {"lat": 40.72, "lon": -73.90}]},
                ],
                "coordinates": "WGS84 latitude [-90,90], longitude [-180,180]; distance in meters",
                "restrictions": "One geometry; positive radius <=20040000m; simple nonzero-area polygon; no dateline-crossing bbox/polygon",
                "missing_location": "Excluded from geographic queries; disclose map exclusions",
            },
            "group_by": {
                "forms": [{"field": "borough"}, {"field": "created_date", "interval": "week"}],
                "maximum_dimensions": 3, "field_types": ["keyword", "boolean", "date"],
                "date_intervals": ["day", "week", "month"],
                "date_rule": "At most one date dimension; requires bounded time on the same field; weeks start Monday",
                "missing_values": "Preserved as null groups",
                "zero_fill": "Only covered calendar buckets; categorical combinations must be observed in the selected cohort",
            },
            "metrics": {
                "allowed": list(METRICS), "default": ["count"],
                "definitions": "See catalog.metric_definitions; closure is administrative time to closure, not first response",
                "missing_durations": "Excluded from closure-duration metrics; closed_count still includes closed requests without a duration",
                "percentiles": "Elasticsearch median/p90 are approximate; inspect result.approximate",
            },
            "minimum_count": {
                "integer_range": [0, 1000000], "default": 0,
                "aggregate": "Retain groups with count >= minimum_count",
                "compare_periods": "Retain groups with baseline_count + current_count >= minimum_count",
                "order": "Applied across complete groups before ranking; no significance claim",
            },
            "output_limits": {
                "preview_limit": f"Records preview 1..100, further bounded by configured max_preview_rows; default {DEFAULT_PREVIEW_ROWS}. Exact totals and full-cohort exports are independent of preview size.",
                "top_n": "Aggregate/comparison first-page rows 1..100; default 20; not the full export cohort",
                "rank_order": ["asc", "desc"], "rank_order_default": "desc",
                "rank_by_aggregate": ["count"],
                "rank_by_compare_periods": ["count", "absolute_change", "relative_change", "rate_change"],
                "rank_by_compare_default": "absolute_change",
                "comparison_count": "Current-period count",
                "absolute_change": "current_count - baseline_count",
                "relative_change": "(current_count - baseline_count) / baseline_count; fraction, null for zero baseline",
                "rate_change": "current_count/current_calendar_days - baseline_count/baseline_calendar_days; requests/day",
            },
            "artifacts": "Use saved result_id; explicitly choose all_matching or selected_groups and saved group_ids. Record exports use the full selected cohort, not the preview.",
        },
        "examples_note": "Illustrative historical dates and request parameters only; check actual snapshot coverage and catalog before execution. No expected findings are supplied.",
        "examples": {
            "records": {**common, "operation": "records", "time": {"field": "created_date", "preset": "last_month"},
                        "filters": {"all": [{"field": "borough", "op": "eq", "value": "BROOKLYN"}, {"category_family": "noise"}]},
                        "preview_limit": 10},
            "aggregate": {**common, "operation": "aggregate",
                          "time": {"field": "created_date", "gte": "2025-12-01T00:00:00-05:00", "lt": "2026-01-01T00:00:00-05:00"},
                          "filters": {"category_family": "noise"},
                          "group_by": [{"field": "created_date", "interval": "week"}, {"field": "borough"}],
                          "metrics": ["count", "closed_count", "mean_closure_hours"], "minimum_count": 5,
                          "top_n": 10, "rank_by": "count", "rank_order": "desc"},
            "compare_periods": {**common, "operation": "compare_periods",
                                "periods": {"baseline": {"gte": "2025-11-01T00:00:00-04:00", "lt": "2025-12-01T00:00:00-05:00"},
                                            "current": {"gte": "2025-12-01T00:00:00-05:00", "lt": "2026-01-01T00:00:00-05:00"}},
                                "filters": {"category_family": "rodent"}, "group_by": [{"field": "nta2020"}],
                                "metrics": ["count", "mean_closure_hours"], "minimum_count": 20,
                                "top_n": 10, "rank_by": "rate_change", "rank_order": "desc"},
        },
    }
