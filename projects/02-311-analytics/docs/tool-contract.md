# Agent tool contract

Implemented version 1 through the Python service, JSON CLI and MCP stdio adapter. Local behavior is tested; Elasticsearch/Kibana integration still requires a live deployment. See [verification status](acceptance.md).

The agent interprets intent, asks necessary clarifying questions, calls tools, and explains results. The service validates semantics, computes results, and produces artifacts. No provider credentials, SDKs, prompt format, or agent framework belong in the analytical core.

## Tools

| Tool | Input | Output |
| --- | --- | --- |
| `describe_dataset` | Optional exact field name | Snapshot coverage, field types, category families, metrics, limits, request-building guide and examples. |
| `validate_analysis` | `AnalysisSpec` | Normalized spec, compiled DSL, warnings, validation errors. No query execution. |
| `run_analysis` | `AnalysisSpec` | Result ID, bounded rows/metrics, counts, completeness, provenance. |
| `get_result` | Result/job ID; opaque page cursor | Saved result or export status; next bounded page when available. |
| `export_csv` | Result ID; `records` or `aggregates`; allowed columns; explicit `cohort_scope`; group IDs when selecting groups | Export job ID, then local file, SHA256, row/byte counts and completeness. No automatic expiry yet. |
| `cancel_export` | Export job ID | Cancellation request/status; poll until the worker reports cancelled and cleanup completes. |
| `create_map_link` | Result ID; `requests` or `neighborhood_trends`; explicit `cohort_scope`; group IDs when selecting groups | Kibana link, represented filters/layer, mapped count/exclusions, limitations. |

Version 0.5 exports expose `stage`, `stage_started_at`, `last_progress_at`, `elapsed_seconds`, and row/byte counters through `get_result`. Workers add `started_at` and `deadline_at`. Stages identify validation, streaming, source cleanup, verification and publication; final failures include `stopped_stage`. A separate `cleanup_error` preserves cleanup problems without replacing an earlier cancellation or source error. These fields describe the last persisted work, **not a heartbeat, completion estimate or proof that a process is alive**. Counters update at most once per second while rows advance; transitions persist immediately. A blocked read cannot publish new progress until it returns. [Recovery and diagnostics](reliability.md).

`AnalysisSpec` selects one operation: `records`, `aggregate`, or `compare_periods`. Version 1 supports bounded `all`/`any`/`not` filters; equality/set/range/existence tests; category families; radius/bounding-box/polygon geography; up to three ordered grouping dimensions; day/week/month time buckets; approved counts and closure-duration metrics. Bound recursive filter depth, predicate count, polygon complexity, buckets, and cardinality. Unimplemented combinations return `unsupported_operation`, never a silently simpler query.

Records default to a five-row preview (or a lower configured cap). Explicit
`preview_limit` values remain supported from 1 to 100 within that cap. Exact matching
totals, saved cohort membership, Maps and full CSV exports remain independent of
preview size. Count-only analyses should use `aggregate`, `metrics:["count"]` and
an empty `group_by` to avoid retrieving unneeded individual requests.

`compare_periods` uses two explicit non-overlapping periods, the same non-time filters and grouping domain, and returns both counts, exposure days, daily rates, absolute change, and nullable relative change. Metric definitions, minimum sample threshold, and ranking rule are explicit. Rank after evaluating all eligible groups.

Both periods require complete source/extraction coverage. Otherwise return `coverage_gap` without comparative metrics or rankings. Unobserved dates are not zero-count buckets. Version 1 does not support partial-period comparisons; small fixtures remain explicitly labeled tests.

## Worked request

Runnable against the default development profile. `fixture-v1` is synthetic; replace it with the discovered immutable dataset version for Elasticsearch. The category catalog expands `noise`; it is not a wildcard chosen by the LLM.

```json
{
  "schema_version": "1",
  "dataset_version": "fixture-v1",
  "operation": "records",
  "as_of": "2026-01-01T12:00:00-05:00",
  "timezone": "America/New_York",
  "time": {
    "field": "created_date",
    "gte": "2025-12-01T00:00:00-05:00",
    "lt": "2026-01-01T00:00:00-05:00"
  },
  "filters": {
    "all": [
      {"field": "borough", "op": "eq", "value": "BROOKLYN"},
      {"category_family": "noise"}
    ]
  },
  "preview_limit": 100
}
```

This example uses a historical demo `as_of`. Live questions default to actual request time. The service rejects an unavailable snapshot and warns on incomplete date coverage. Date predicates are start-inclusive/end-exclusive. `time.preset: "last_month"` resolves through the shared timezone library; the saved normalized specification contains absolute boundaries. Arbitrary natural-language date phrases remain the agent's responsibility.

Each result carries `result_id`, normalized spec, compiled DSL templates, dataset manifest, catalog hash, bounded rows, exact matching total, truncation/approximation flags, coverage, execution completeness and timings. Page-specific PIT IDs and cursors are execution details rather than saved DSL templates. Types/units come from the discovery catalog. Ingestion quality counts live in the manifest; map tools add geographic exclusion counts. **An empty complete result differs from a failed or partial query.**

`create_map_link` and `export_csv` consume that saved result. For records they reproduce the full query selection, not the preview. For aggregate analysis, `aggregates` exports the computed table; `records` exports the source cohort and is labeled accordingly. Neighborhood trend maps must visualize the comparison metric or explicitly return unsupported; showing underlying complaint points alone does not satisfy that request.

Comparative record exports use the union of the two periods and exclude any gap. Both artifact tools require `cohort_scope` to choose `all_matching` or `selected_groups`; never infer it from a displayed top-N table. The latter requires group IDs validated against the complete saved result. Each artifact manifest preserves the chosen scope and IDs. `all_matching` aggregate exports include all computed eligible groups, not merely the preview. Maps use that same selection and disclose geometry exclusions. Trend-map publishing uses a bounded derived-result index plus the NTA boundary join described in the build plan; only the artifact writer receives those limited write privileges.

From version 0.6, `export_csv` returns `budget_exceeded` immediately when the exact saved cohort exceeds `max_export_rows`; no job or capacity reservation is created. Admitted export jobs include `planned_rows`, distinct from completed `rows_written`. For comparison records this includes both periods; aggregate exports count table rows. Selected CSV columns also restrict backend source retrieval, without changing selection, sorting or pagination. Admission does not guarantee completion; stream-time byte/row/deadline and identity checks remain active.

## Adapter behavior

MCP exposes tool argument/output schemas and `structuredContent`, plus text serialization. `spec` is an object whose detailed rules and examples come from `describe_dataset.analysis_guide`; the same strict runtime validator handles all callers. CLI accepts the same JSON through stdin or a file and emits the same result envelope. Transport uses the official MCP SDK. [MCP tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

Errors use stable codes: `invalid_spec`, `needs_clarification`, `unsupported_operation`, `coverage_gap`, `budget_exceeded`, `backend_unavailable`, `partial_execution`, `result_expired`. Include a short actionable explanation without raw credentials or infrastructure details. A recoverable warning remains separate from an execution failure.

Agent instructions require discovery before unfamiliar queries, a clarification when ambiguity materially changes the answer, evidence IDs for numeric claims, visible limitations, and links to requested artifacts. An agent can chain analyses using returned group IDs. Agent summaries are evaluated separately from deterministic tool correctness.

CLI/MCP equivalence and actual stdio protocol tests are implemented. Two-agent-client comparison and the held-out natural-language evaluation remain release gates. Replay alone proves adapter compatibility, not autonomous reasoning.
