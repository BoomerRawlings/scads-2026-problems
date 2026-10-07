# Riverwatch10: accepted by software, rejected by source review

Separate AI review of the known, authored development fixture, following the
[unchanged review protocol](../../evaluations/local-pilot/REVIEW-PROTOCOL.md).
This is not human labeling, held-out evaluation, or a general-accuracy result.
Every summary claim, finding, qualification, conflict, observation and limitation
was checked against cited source text, the original PNG, independently decoded
MP4 frames, and actual run provenance.

The [report JSON](report.json), [metadata](run-metadata.json),
[trace](tool-trace.json), [ledger](evidence-ledger.json), and both original
isolated observation files are byte-identical copies from
`runs/local-riverwatch-10/`. Copying occurred after metadata reached
`phase=finished`, `status=complete`. Markdown was rerendered for the example
location; its bytes also remain identical because the relative links are unchanged.
No model wording was edited. Report SHA256:
`3e9f77d1306b0e96020d3c270bad50566c71f20e9dd020567d6f3a46c8670935`.

## Why rejected

- The summary says sources **establish** delayed readiness. The September 5
  materials assert delay, while the September 3 register asserts ready and
  explicitly says reconciliation is unresolved. Mentioning the older entry
  does not establish that its claim is false or corrected. Finding 1's
  attribution and finding 2's reconciliation caveat are better scoped, but
  they do not repair the stronger opening conclusion.
- The summary calls all evidence "synthetic fixture text," despite successful
  source PNG and MP4 inspection and the report's own four pixel observations.
  Shared synthetic authorship is correct; collapsing the actual evidence
  modalities into text is not. The host-authored limitations correctly state
  the inspected pixels, so the report contradicts its own provenance.
- The shipping conflict preserves both dates and is labeled `expected_arrival`,
  but omits the source's explicit qualification that both are plans and neither
  confirms physical receipt. No delivery is falsely asserted; this is a missing
  protocol qualification alongside the substantive summary errors above.

## Claim-by-claim review

| Report element | Review |
| --- | --- |
| Identity and scope | Correct Riverwatch target and connected Silt/Northline scope. No arts-event decoy, institute-wide delay, supplier misconduct or defective-sensor conclusion. |
| Summary: readiness | Overstates unresolved source claims as an established delayed state; see rejection reason. |
| Summary: dependency and shipping | Riverwatch → Silt Sensor Batch → Northline is supported by `memo-001` and `memo-003`; conflicting expected arrivals by `tbl-006` and `memo-004`. Northline's external status is omitted, but no organizational membership is invented. |
| Summary: evidence origin | Synthetic provenance and absent independent real-world verification are correct. "All ... text" misdescribes actual PNG/MP4 inspection. |
| Finding 1 | Its qualification correctly attributes delayed readiness to September 5 sources and preserves disagreement. Read together, claim and qualification are supported as source assertions, not verified current truth. |
| Finding 2 | `tbl-003` explicitly records ready on September 3 and unresolved reconciliation. Both claim and qualification are supported. |
| Finding 3 | Both cited memos support Riverwatch's Silt dependency. Multiple fixture records do not imply independent corroboration; the limitations correctly retain that distinction. |
| Finding 4 | `memo-003` and `tbl-005` support pending acceptance and calibration before release. No defect inference is made. The finding could more clearly retain the records' September 4 date. |
| Readiness conflict | Correct opposing claims, source dates and citations. Recency is not offered as explicit proof of correction in this conflict entry. |
| Shipping conflict | Correct September 2 register/September 14 plan versus September 5 notice/September 19 revision. Explicit planned-versus-received qualification is absent. |
| Video 00:00 | All quoted captions and footer text match the actual frame, including the release hold pending acceptance. |
| Video 00:15 | All quoted text matches. The only visible date is September 5 in the footer; no September 3 date was imported from the register into this observation. |
| Video 00:29 | Caption and footer match. "Have not established" remains uncertainty about other activities, not a factual denial of their delay. |
| PNG | All quoted caption/date/provenance text matches. Minor cosmetic error: the footer is pale green, not the claimed dark green. This does not affect the readiness analysis, but the original wording remains uncorrected. |
| Limitations | All five host-authored entries match this run: inspected pixels, sampled frames/no audio, missing inspection-tag image, bounded graph/inventory scope, synthetic/shared-origin evidence. |
| Follow-up | Empty under the declared-synthetic host policy. No model-authored recommendations are claimed. |

Four findings and two conflicts satisfy the requested counts. The substantive
summary/findings/qualifications/conflicts contain 135 whitespace-separated words;
the full report is longer because it includes isolated transcriptions and fixed
provenance limitations. The model-authored summary remains the decisive unresolved
quality problem.

## Grounded construction and verification

- Seventeen successful MCP calls retrieved all nine connected source records
  and both graph-edge proofs. The scope is exactly `riverwatch`, `silt_sensors`
  and `northline`; no missing inventory/proof IDs remain. One repeated inventory
  is recorded as exact-result reuse, not new independent evidence.
- Twenty-three actions in 1,372.782 seconds: 17 MCP calls, two rejected finish
  intents requesting remaining media inspection, one accepted finish intent,
  two isolated observation generations and one report generation. No final
  report rejection occurred in software.
- Independently decoded/viewed video frames at 0, 15 and 29 seconds. `ffprobe`
  confirms source PTS 0, 245760 and 475136 with time base `1/16384`. Requested
  seeks were 0, 14.5 and 29 seconds; the report uses actual returned timestamps.
  The source PNG was inspected directly. This is simple caption media, not
  natural-scene or audio validation.
- All nine ledger IDs, source locators, dates and indexed-text hashes match the
  current source records; both attached-media hashes match source bytes.
  All 15 dataset-file hashes and the aggregate dataset fingerprint match:
  `7328e186691e7956ac440b1acd28391b6a2e022292b2c28c0104af6d0139cd67`.
- All six implementation hashes in metadata match the
  [v9 snapshot](../../evaluations/local-pilot/implementation-v9/README.md).
  All eight snapshot files also match their declared hashes and the current
  frozen code/schema/requirements/candidate manifest.
- Both [video](media-observation-01.json) and [image](media-observation-02.json)
  JSON output hashes match metadata. Their source-call numbers resolve to actual
  successful `read_media` calls, and their source/locator order matches returned
  media. All four observation objects are reused exactly in the final report.
  Fixed limitations and empty follow-up also match the declared host constraints.
  Exact reuse establishes consistency, not correctness.
- Input request fingerprints are recorded, but original HTTP request bodies
  and encoded images were not persisted. This review checks actual source pixels,
  saved outputs, hashes and lineage; it does not claim a complete request replay.
- Qwen3.5-4B Q4_K_M used the recorded
  [candidate profile](../../evaluations/local-pilot/runtime-profile-qwen35-01.json).
  Planning and isolated observations used disabled reasoning, temperature 0,
  seed 0. Report synthesis requested 1,024 thinking tokens, temperature 0.6 and
  seed 0; returned usage records 10,129 prompt/2,378 completion tokens. Private
  reasoning text was not saved. Launch settings are operator records, not
  independent server attestation or proof of loaded weights.
- The [resource observation](../../evaluations/local-pilot/resource-probe-riverwatch10.json)
  is one shared-host sample. Run duration excludes downloads/startup; neither
  latency nor memory establishes an isolated benchmark or minimum specification.

Grounded media corrected the earlier pixel/date contamination and made actual
media gaps explicit. It did not prevent an overstated readiness summary or a
contradictory account of evidence modalities. This is a preserved rejected
development run, not an accepted free-local analytic showcase.
