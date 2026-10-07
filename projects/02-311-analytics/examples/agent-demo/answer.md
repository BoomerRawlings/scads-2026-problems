Authored CLI smoke evaluation; not a held-out accuracy test or complete-solve claim. Default profile: fixture-v1, 32 authored synthetic requests, fixture_only. Complete coverage means the authored fixture, not NYC. These results do not validate Elasticsearch, Kibana, citywide findings, or scale.

**1. Brooklyn noise last month; Jan 2 2026 reference date**

December 2025, America/New_York: **4 requests**. Preview:

| Request | Created | Complaint | Status | Closure hours |
|---|---|---|---|---:|
| FIX-021 | 2025-12-03 20:00 -05:00 | Noise - Residential | Closed | 2 |
| FIX-022 | 2025-12-09 20:00 -05:00 | Noise - Street/Sidewalk | Open | null |

Preview truncated to 2. Export complete: **all 4 matching records**, 681 bytes, [CSV](brooklyn-noise.csv). Analysis `0cee016ca3fe4c7391b9732a6298c0f5`; export job `4e49baa60cb84769b9ef4f78c3f4d1f1`. SHA-256 `ba7c22b1effcd036aea35031df3d0c6edfe8274a8d9aa911a7ddd0c461b29381`.

**2. November-December 2025 rodent complaints by neighborhood**

**17 requests; 6 groups**. Ranked by December daily rate minus November daily rate; 30 and 31 calendar days respectively. Minimum combined count 1 excluded 0 groups.

| Neighborhood label | Nov count | Dec count | Rate change, requests/day | Nov mean closure h | Dec mean closure h |
|---|---:|---:|---:|---:|---:|
| FIXTURE-BK-B | 1 | 2 | 0.03118279569892473 | null | 48.0 |
| FIXTURE-QN-A | 1 | 2 | 0.03118279569892473 | null | 24.0 |
| FIXTURE-MN-A | 1 | 1 | -0.0010752688172043015 | 72.0 | 96.0 |
| Missing neighborhood | 1 | 1 | -0.0010752688172043015 | null | null |
| FIXTURE-BK-A | 2 | 2 | -0.002150537634408603 | 36.0 | 18.0 |
| FIXTURE-BX-A | 2 | 1 | -0.034408602150537634 | 18.5 | 72.0 |

BK-B and QN-A tie for largest increase. Unchanged counts decline slightly per day because December is longer. Neighborhoods are synthetic labels, not official NTA assignments. Descriptive reported-request rates; no incidence, causality, or significance claim. `null` means no usable duration, not zero hours. Result `861194e12cc047e58b8e386503683c97`.

**3. Brooklyn agency closure durations**

Full available creation window: Nov 1 2025 inclusive-Jan 1 2026 exclusive. **14 requests**:

| Agency | Requests | Closed | Open | Mean h | Median h | P90 h | Closed missing duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| DOHMH | 7 | 6 | 1 | 31.2 | 24.0 | 48.0 | 1 |
| NYPD | 7 | 5 | 2 | 3.6 | 2.0 | 6.4 | 0 |

DOHMH's observed closure durations are longer. Closure means administrative created-to-closed time; not first response, confirmed resolution, or repair time. Metrics exclude missing durations; closed counts retain those requests. DOHMH's mean uses 5 valid durations despite 6 closed requests. Open status is administrative, not proof a request remains actionable. Different request mixes prevent causal agency-performance conclusions.

Both agency_name values were null. Fixture result: `approximate=false`; Elasticsearch percentiles may be approximate. Main result `b58ec92a6e3c41878a3f7c0f0aa58b5e`; missing-duration check `85fb938320a34a38bc6e498b3fe14ea0`.

**4. Citywide rodent trends: January-February 2026**

Unavailable. Both validate and run failed with exit code 2, `coverage_gap`: "Comparisons and calendar buckets require complete creation-date coverage; unobserved dates cannot become zeros". Coverage ends Jan 1 2026; no zero-count or trend claim.

**5. Open Brooklyn noise results on a Kibana map**

Could not open. Map command failed with exit code 2, `unsupported_operation`: "Fixture results cannot produce a real Kibana map; use an indexed immutable dataset". No map URL returned.

Evidence: [trace](trace.json); request JSON files alongside it. Discovery used CLI help/describe. No source, fixtures, tests, existing example files, or acceptance docs inspected. Each analytical request validated before run. Export queued, then polled through result to complete. CLI reports formula-like CSV text escaped with an apostrophe; numeric values unchanged.
