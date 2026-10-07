# Elastic feasibility research

Checked 2026-10-06. Research only; no running cluster, version selection, performance evidence, or verified integration yet.

## Recommendation

Build a provider-neutral analytics service: typed query specification → validated Query DSL → bounded results and evidence. Expose the same operations through MCP/JSON CLI; add HTTP only when needed. Keep the agent outside ingestion, statistical definitions, query budgets, CSV paging, and Kibana URL construction. These are project recommendations, not Elastic requirements.

Use one immutable, versioned dataset/index for the first demonstration. Resolve relative dates once into absolute bounds. Query, CSV, and map must share dataset version and filters; a Kibana page querying current data does not automatically share an Elasticsearch PIT snapshot.

## Existing work worth imitating

Elastic Agent Builder offers parameterized ES|QL tools, scoped index-search tools, and external MCP tools. Its built-ins inspect mappings, search data, generate/execute ES|QL, and create visualizations. Imitate the small domain-specific tool catalog; keep Agent Builder an optional adapter. Access requires an appropriate subscription/tier; documentation marks the API tutorial Stack GA 9.3+. Verify chosen deployment capabilities later. [Custom tools](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/tools/custom-tools), [built-ins](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/tools/builtin-tools-reference), [prerequisites](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/get-started), [API tutorial](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/agent-builder-api-tutorial).

Agent Builder exposes `/api/agent_builder/mcp`, with Space-aware paths and permission-bound access. The older standalone Elasticsearch MCP repository is deprecated; use it as a reference, not the foundation. [MCP endpoint](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/mcp-server), [deprecated repository](https://github.com/elastic/mcp-server-elasticsearch).

## Data and query contract

Proposed explicit mapping: identifiers, complaint type, borough, agency, status, ZIP and neighborhood ID as `keyword`; created/closed timestamps as `date`; validated location as `geo_point`; derived elapsed closure seconds as numeric. Preserve missing/invalid-field counters. Do not equate closure duration with first-response time. Neighborhood IDs require separately verified geographic enrichment.

`geo_point` supports distance, bounding-box and polygon queries, plus spatial grids. Prefer `{lat, lon}` input to avoid coordinate-order ambiguity. [Geopoint mapping](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/geo-point).

Compile filters, grouped metrics, time histograms, proximity and period comparisons from allowlisted fields/operators. Precompute closure duration to avoid agent-authored scripts. Calendar buckets should specify `America/New_York`; DST changes bucket duration. [Date histograms](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-datehistogram-aggregation).

ES|QL is useful for optional analytical tools, including spatial calculations. It defaults to 1,000 output rows, with a configurable 10,000 maximum; this limits output, not documents processed. Avoid using it for complete row exports. Spatial types cannot be direct sort keys; sort calculated distance instead. [Limitations](https://www.elastic.co/docs/reference/query-languages/esql/limitations), [distance function](https://www.elastic.co/docs/reference/query-languages/esql/functions-operators/spatial-functions/st_distance).

Top-N `terms` counts can be approximate across shards. Exhaustive groups need `composite` pagination with the returned `after_key`; Elastic explicitly recommends load testing it. Percentiles are approximate. Expose these distinctions in evidence. [Terms](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-terms-aggregation.html), [composite](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-composite-aggregation), [percentiles](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-metrics-percentile-aggregation.html).

Use the configurable budgets in the [build plan](build-plan.md#query-and-output-guarantees); measure before tuning. Reject unsupported queries; surface timeout/shard failure/truncation. Elasticsearch's default bucket ceiling is 65,536, not a sensible UI target. [Search settings](https://www.elastic.co/docs/reference/elasticsearch/configuration-reference/search-settings).

CSV exports: background streaming job; PIT + `search_after`; stable sort; latest PIT ID; close PIT on completion/cancellation. Do not raise result-window limits or use deep offsets. Include filter/dataset manifest, row count and completion state; a capped export must say partial. [Pagination](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results).

## First milestone: prove Kibana map parity

Create a saved dashboard containing a Maps layer, configured data-view time field, and enabled global search/time filtering. Test categorical, absolute-time and spatial filters against service counts. Maps supports these filters, but layers can opt out. [Map search](https://www.elastic.co/docs/explore-analyze/visualize/maps/maps-search), [spatial filters](https://www.elastic.co/docs/explore-analyze/visualize/maps/maps-create-filter-from-map).

Candidate integration: documented `POST /api/short_url` with the deployed locator's validated parameters. It is Technical Preview and does not validate locator parameters. Source currently defines `MAPS_APP_LOCATOR` with `mapId`, `filters`, `query`, `timeRange`; provided filters/query replace saved values. This is source evidence, not proof of a stable Maps HTTP contract. [Short URL API](https://www.elastic.co/docs/api/doc/kibana/operation/operation-post-url), [locator types](https://github.com/elastic/kibana/blob/68622be1b80860de47659aa6f22964fb2cda3b10/x-pack/platform/plugins/shared/maps/public/locators/map_locator/types.ts), [locator definition](https://github.com/elastic/kibana/blob/68622be1b80860de47659aa6f22964fb2cda3b10/x-pack/platform/plugins/shared/maps/public/locators/map_locator/locator_definition.ts).

Fallbacks: dashboard locator enclosing the saved map; then a small version-specific Kibana bridge using the official plugin locator contract. A custom map preview can aid debugging but does not satisfy the required Kibana integration. Avoid hand-built `_a`/`_g` state. [Navigation guidance](https://www.elastic.co/docs/extend/kibana/key-concepts/platform-architecture/routing-navigation-and-url).

Use clusters for broad results. Documents layers default to 10,000 features; vector tiles can also omit excess features per tile. Never describe all displayed points as complete coverage. [Layer scaling](https://www.elastic.co/docs/explore-analyze/visualize/maps/vector-layer).

Export a working dashboard/map/data-view bundle with `includeReferencesDeep`; preserve opaque NDJSON and migration metadata. Reimport into a clean compatible instance. Imports support same version, newer minor within the major, or next major—not older versions. [Export API](https://www.elastic.co/docs/api/doc/kibana/operation/operation-post-saved-objects-export), [compatibility](https://www.elastic.co/guide/en/kibana/current/saved-object-ids.html).

Remaining gates: link/filter/snapshot parity; clean asset import and Space permissions; closure/neighborhood semantics; full CSV completeness; measured million-record latency, heap and disk; deployment license/version availability. Select versions only when these checks can run.
