# Qualification of observed comparison periods

The project distinguishes complete enumeration of an **observed public-data corpus** from a transactional provider snapshot and from complete reporting of conditions in New York City. Neither equal counts nor local index freezing proves the latter two. A successful ordinary API capture retains `coverage.complete=false`.

`analytics311.qualification` provides a narrower certificate, `scope=reconciled_observed_snapshot`. It enables reproducible comparisons *within the captured reporting corpus* when the following evidence agrees:

1. The official capture adapter's source, window, initial/final metadata, unique counts and revision observations reconcile. The artifact has a recorded SHA256, byte count and row count.
2. Normalization verifies the input/output byte hashes and preserves every record. Raw, unique and normalized counts agree; there are no rejected records or unusable creation timestamps. Missing closure timestamps and missing geography remain visible quality exclusions, not zero durations or invented neighborhoods.
3. Ingestion consumes exactly the qualified normalized artifact into one concrete index. Completed ingestion's hash, processed count and index UUID match the normalized manifest and the frozen index's exact count.
4. The requested comparison periods fit wholly inside the qualified NYC-local creation window. Qualification never widens the window or creates observations on unobserved dates.

Certificates retain `transactional_source_snapshot=false` and `population_complete=false`. `coverage.complete` remains false. Answers must carry the observed-corpus warning, distinguish reporting growth from underlying conditions, and identify geography and closure-duration exclusions. A certificate is deterministic integrity metadata, **not a cryptographic signature or independent proof from the provider**. Trusted local operators still control manifests. Callers must verify bytes before invoking the qualification functions; the functions validate the retained evidence, not files or remote services themselves.

## Integration contract

After `normalize_file` has verified source and output hashes, use `qualify_normalized_capture(capture_manifest, normalized_manifest)` and attach its result as `comparison_qualification`. Qualification failure must leave ordinary normalization unqualified; never turn it into a coverage assertion.

Before ingestion creates or writes an index, validate an attached certificate with `comparison_qualification(staged_manifest)`. For every hash-matched staged source, reconcile the staged count to processed rows and call `freeze_index(..., expected_count=staged_manifest['row_count'])`, whether or not full coverage was requested. Then attach `qualify_frozen_index(staged_manifest, ingestion, frozen_snapshot, bounds)` to the published index manifest. Requested bounds must retain `complete=false` for this scope.

Runtime `comparison_qualification(index_manifest)` revalidates the chain, count and index binding. An absent certificate returns `None`; a modified/malformed certificate fails closed. Comparisons may use a valid certificate's bounds while continuing to report `coverage_complete=false` and the specific qualified scope. Existing authored fixture coverage remains a separate mechanism.

## Practical first real corpus

A bounded official aggregate on 2026-10-07 reported **2,133,268 rows and distinct keys** for `[2025-04-01, 2025-11-01)` NYC-local creation dates. This seven-month window contains complete calendar months and avoids both 2025 daylight-saving clock transitions. That reduces one known source of unmappable creation timestamps without inventing a timezone offset. Other invalid timestamps or rejected records still prevent qualification.

[Source observation](../examples/evidence/source-april-october-2025.json) records the initial scope query and matching revision observations; that observation alone is not a captured dataset. The subsequent [captured manifest](../examples/evidence/captured-manifest.json) and [full local byte/ID verification](../examples/evidence/captured-local-verification.json) establish actual acquisition of 2,133,268 unique records. The [executed acceptance ledger](acceptance.md) records normalization, frozen-index and independent SQLite count reconciliation. Its neighborhood comparison uses June versus October, with daily-rate normalization for the unequal month lengths. Future captures must repeat these checks; the historical qualification cannot certify newly retrieved bytes.

## Official neighborhood boundaries

The official DCP [NTA dataset](https://data.cityofnewyork.us/City-Government/2020-Neighborhood-Tabulation-Areas-NTAs-/9nt8-h7nd) currently identifies release **26b**. A bounded actual GeoJSON download preserved all **262 unique NTA features**, including **197 residential type-0 NTAs**. The remaining 65 represent parks, airports, cemeteries and other special areas. A neighborhood analysis should select the pinned residential NTA code list, or explicitly describe the broader NTA scope. Preserve all boundary features for auditing; do not silently drop missing/ambiguous joins.

The ignored local artifact is `data/nta2020-26b.geojson`: 4,532,381 bytes, SHA256 `5049760a4d0936e1d3dbf70d745e2cee4286bd163b11c702f15fa28db46a001e`. [Receipt](../examples/evidence/official-nta2020-26b.json) records official HTTPS origin, before/after metadata, response observations, type counts and residential code list. All 262 polygons passed the existing Shapely validity checks; no real request enrichment is claimed by that check. Use this exact artifact hash for enrichment and the matching map layer. NTA definitions approximate neighborhoods and are not exhaustive definitions of locally understood neighborhoods.

## Provider guarantees and alternatives

Socrata documents `Last-Modified` and `ETag` as cache-validation information. Its [response documentation](https://dev.socrata.com/docs/response-codes) warns that other headers can change without notice. The capture's additional truth/replica headers are therefore conservative drift observations, **not documented snapshot tokens**.

Socrata's [dataset archiving](https://support.socrata.com/hc/en-us/articles/9486838238743-Introducing-Dataset-Archiving) can export a historical revision when the dataset is enrolled; noneditors may export available archived versions. An applicable 311 archive export was not verified here. If one becomes available, retain its exact revision/export identity and validate counts/bytes before defining a stronger qualification scope. Do not relabel ordinary query output as an archived revision.

[SODA3 guidance](https://support.socrata.com/hc/en-us/articles/43491231777047-Using-the-SODA3-API) distinguishes query and export formats; the [endpoint documentation](https://dev.socrata.com/docs/endpoints) requires authentication or an application token for SODA3. Existing anonymous SODA2 capture remains supported; switching endpoints alone does not establish cross-page isolation.
