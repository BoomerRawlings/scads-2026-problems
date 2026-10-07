# Local interface verification

## Guided interface — 7 October 2026

Current source UI: **Equipment → Specification → Results**. Removed marketing hero, default algorithm selector, dense instructions and exposed diagnostic JSON. Plain local assets; no fonts, libraries or APIs fetched externally. Catalog choices come from an atomic released-metadata snapshot. Unsupported/missing observations remain searchable as unknown; the interface never invents values.

| Verification | Result |
| --- | --- |
| Automated API/search boundaries | 80 Python tests pass (`test_guidance.py`, `test_interfaces.py`, `test_search.py`). Includes new endpoint isolation, coverage restrictions and atomic snapshot reads. |
| Query/controller contracts | 23 Node tests pass (`test_guide.cjs`, `test_ui.cjs`). All 13 fields and compatible units compile through the actual Python parser. Covers invalid numbers, bounds, stale responses, interrupted searches, saved queries, empty and coverage catalogs. Controller tests use a small DOM double; they do not establish browser layout. |
| Guided coverage search | Generator → output voltage covered: M7 and HR-28 confirmed; four incomplete scopes remain separately visible. |
| Ambiguous numeric search | Generator → output voltage ≥125 V: no confirmed matches; six records require more detail. |
| Multiple requirements | HR-28 + output voltage ≥30 V + output power ≥1.4 kW + DC: one confirmed match, with partial-processing notice. |
| Editing and validation | Back/Edit preserve quantities and conditions. `1e3` rejected without running a broader query. Text-search Edit returns to the original text. |
| Request export | Saved HR-28 from the coverage query, then ran a different numeric query. Actual downloaded JSON retained the originating query and assertion ID. [Captured export](guided-request-example.json). Download-event automation timed out; the generated local file was inspected directly. |
| Responsive inspection | Desktop and 390px viewport inspected; mobile numeric controls/results fit with no horizontal overflow. Step headings receive focus; fields have labels; no browser warnings/errors observed. Viewport restored afterward. |

Screenshots: [equipment](guided-search-desktop.jpg), [specifications](guided-search-specifications.jpg), [results](guided-search-results.jpg), [mobile](guided-search-mobile.jpg).

This is agent-operated engineering verification, not independent usability or accessibility certification. Frozen extraction/review records were not modified. Existing qualified 0.1.0 portable packages contain the previous interface; their hash reports remain evidence of that earlier snapshot.

## Earlier interface / packaged snapshot

Agent-operated browser check on the current Windows host, using the frozen five-document development catalog and private source workspace. This is engineering verification, not independent human usability evidence.

| Journey | Observed result |
| --- | --- |
| Private review | Five documents listed; Homelite shows 51 pages, five candidates, one pending, partial processing. Original scanned page renders with the candidate evidence highlight. |
| Existing correction | Accepted/corrected filter shows revised condition and recorded reviewer explicitly marked **agent**. No human review decisions were created during verification. |
| Constrained discovery | `model HR-28 and output power >= 1.4 kW and output voltage >= 30 V and condition "DC"` returns Homelite / HR-28, two supporting released assertion IDs, source revision and request reference. Partial-processing warning retained. |
| Missing conditions | `generators with output voltage at least 120 V` reports insufficient metadata, lists missing observations and released operating conditions. No unsupported positive matches. |
| Ambiguous role | `voltage above 100 V` requests input/output clarification. |
| Request preparation | Add-to-request changes count to one. Export produced `vopt-document-requests.json`; inspected file contains one HR-28 reference, catalog integrity/sequence, query and assertion IDs. No original or OCR content. Browser automation's download-event wait timed out, but the file itself was created and inspected. |

Screenshots: [discovery](discovery-ui.jpg), [private review](review-ui.jpg). Existing API/lifecycle tests cover stale corrections, simultaneous decisions and source-hash changes. Accessibility, mobile layout and an independent human operator remain unqualified.

Final source-binding hardening: review rendering hashes and opens the same in-memory PDF bytes. A regression replaces the source while preserving size and modification time; the server rejects it. This removes the earlier pathname/stat-cache race. Native review rasterization retains its pixel cap; the ingestion worker's hard deadline does not apply to this interactive rendering route.
