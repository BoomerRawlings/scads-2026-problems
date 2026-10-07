# NYC 311 data: verified findings and ingestion plan

Research date: **2026-10-06, America/Los_Angeles**. Public metadata, small samples, and aggregate queries only; no bulk dataset downloaded. Recommendations below are design decisions, not implemented behavior.

## Sources and measured scope

NYC split its former 2010–present dataset in December 2025. The original ID now covers 2020 onward; the historical archive has a new ID. NYC intends to limit each dataset to ten years, so coverage must be discovered rather than hardcoded indefinitely. [Official change notice](https://www.nyc.gov/opendata/news/all-news/311-Service-Requests-Updates)

| Official source | ID | Rows measured today | Created-date range measured |
|---|---|---:|---|
| [2020–present metadata](https://data.cityofnewyork.us/api/views/erm2-nwe9.json) | `erm2-nwe9` | 22,703,288 | 2020-01-01–2026-10-05 |
| [2010–2019 metadata](https://data.cityofnewyork.us/api/views/76ig-c548.json) | `76ig-c548` | 22,613,917 | 2010-01-01–2019-12-31 |

Measurements used `SELECT count(*), min(created_date), max(created_date)` against each official `/resource/{id}.json` endpoint. Current metadata reported a daily refresh; archive metadata says historical/nonautomated despite its generic description saying daily.

**Recommended demonstration snapshot:** 2024–2025, all categories and boroughs: **7,111,811 rows** measured by the [official bounded count query](https://data.cityofnewyork.us/resource/erm2-nwe9.json?$select=count%28%2A%29%20as%20count&$where=created_date%20%3E%3D%20%272024-01-01T00%3A00%3A00%27%20AND%20created_date%20%3C%20%272026-01-01T00%3A00%3A00%27). This permits matching-month year-over-year comparisons. A smaller first milestone, 2025 alone, returned **3,655,041 rows**. These are source row counts, not verified distinct-key counts or downloaded records. Recheck uniqueness after ingestion. Counts change with corrections.

## Fields the agent must understand

The current source has 44 public columns. Metadata also exposes synthetic region columns; do not treat those generated IDs as neighborhood names. [Live field metadata](https://data.cityofnewyork.us/api/views/erm2-nwe9.json)

| Meaning | Actual API fields | Proposed handling |
|---|---|---|
| Request identity | `unique_key` | Text/keyword; never infer numeric type |
| Problem hierarchy | `complaint_type`, `descriptor`, `descriptor_2` | Keywords; preserve original values |
| Agency/status | `agency`, `agency_name`, `status` | Keywords; discover vocabulary from snapshot |
| Event dates | `created_date`, `closed_date` | Preserve raw timestamps; normalized dates plus quality flags |
| Agency update | `resolution_action_updated_date` | Agency action timestamp; not a complete ingestion watermark |
| Expected update | `due_date` | Expected agency update under SLA; not guaranteed resolution deadline |
| Administrative geography | `borough`, `community_board`, `council_district`, `police_precinct`, `incident_zip` | Keywords; separate geographic units |
| Coordinates | `latitude`, `longitude`, `location` | Validated `geo_point`; retain missing-geometry counts |

Display labels changed to **Problem** and **Problem Detail**, but API names remain `complaint_type` and `descriptor`. “Additional Details” maps to `descriptor_2`. Accept both old/new vocabulary. [Change notice](https://www.nyc.gov/opendata/news/all-news/311-Service-Requests-Updates)

A two-row probe confirmed `location` is GeoJSON Point, coordinates **longitude, latitude**; do not reuse older tutorials expecting a latitude/longitude object. Request data may omit fields.

## Geography and statistical meaning

No native neighborhood field exists. **Recommendation:** point-in-polygon enrichment from [2020 NTA boundaries](https://data.cityofnewyork.us/City-Government/2020-Neighborhood-Tabulation-Areas-NTAs-/9nt8-h7nd), pinned to a recorded release/hash; metadata currently names version **26b**. Store `nta2020`, `ntaname`, `ntatype`, boundary version, and join outcome. NTAs approximate neighborhoods; parks/airports and other nonresidential areas are separate types. Missing or ambiguous geometry stays unknown. ZIP analysis is valid before enrichment but must be called ZIP analysis.

**Time to close is not response time or repair time.** NYC explicitly distinguishes administrative closure from actual fulfillment. Recommend median/p90 nonnegative closure duration, closed-valid sample size, open fraction, and rejected-duration count. Compare like complaint categories and creation cohorts; recent cohorts disproportionately exclude unresolved requests. Never replace missing closure dates with zero. [NYC reporting definitions](https://www.nyc.gov/site/311reporting/faq/faq.page)

Source dates are floating timestamps without offsets. **Assumption pending confirmation:** interpret as `America/New_York`, retain originals, flag ambiguous/nonexistent DST times. “Last month” needs explicit resolved dates and dataset coverage; current-time questions may exceed a frozen snapshot. [Timestamp specification](https://dev.socrata.com/docs/datatypes/floating_timestamp.html)

## Ingestion build sequence

1. Record metadata, schema, source update time, selected interval, per-month counts, and vocabulary. Fix a snapshot ID and manifest format.
2. Stream selected columns by complete month into immutable compressed raw files. Existing `/resource/erm2-nwe9.json` and `.csv` support SoQL; anonymous GET probes worked. Start modest pages with explicit ordering and a `(created_date, unique_key)` cursor; checkpoint each page. Avoid deep offsets. [Ordering](https://dev.socrata.com/docs/queries/order.html), [paging costs](https://dev.socrata.com/docs/queries/page.html)
3. Hash files; reconcile counts and keys; flag source changes during capture. This creates a reproducible captured snapshot, not a guarantee that the upstream mutable API provided transaction isolation.
4. Normalize and enrich; bulk upsert under deterministic IDs. Publish an index only after counts, duplicates, date/geometry quality, borough/category distributions, and sample answers pass reconciliation.
5. Freeze initial evaluation data. Add daily refresh later: system `:updated_at` exists, but replacements can mark every record changed. Overlap the watermark, upsert, and periodically reconcile deletions/old records. A created-date-only append pipeline misses closures and corrections. [System fields](https://dev.socrata.com/docs/system-fields.html)

SODA3 `/query` and `/export` require user authentication or an application token; that future ingestion choice is independent of any AI provider. No credential setup is needed for planning. [SODA3 documentation](https://dev.socrata.com/docs/queries/)

**Unresolved:** exact timezone policy, correction/deletion behavior, schema/vocabulary drift, missing-geometry rates, unique-key collisions, disk/index size, ingestion throughput, and resource requirements. Measure during the first bounded ingestion; do not estimate benchmark results from row counts. Report complaint growth as reporting growth, not proof that underlying conditions worsened.
