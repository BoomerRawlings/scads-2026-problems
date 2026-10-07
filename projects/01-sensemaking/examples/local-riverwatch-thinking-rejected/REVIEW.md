# Riverwatch08: accepted by software, rejected by source review

Independent AI review of a known, authored development fixture; not human gold,
a held-out evaluation, or evidence of general accuracy. Review followed the
[predeclared protocol](../../evaluations/local-pilot/REVIEW-PROTOCOL.md), inspecting
all cited source text, the source PNG, and independently decoded video frames.

The original [report JSON](report.json), [metadata](run-metadata.json),
[trace](tool-trace.json), and [ledger](evidence-ledger.json) are copied byte-for-byte
from `runs/local-riverwatch-08/`. Only [Markdown](report.md) source links were
rerendered. Analytic wording is unchanged. Original report SHA256:
`5d437ecad6acaee29210c45717150cbd9f329c130332b2b77d7b0a0812b4903c`.

## Why rejected

- The final limitation says `video-tx-001` lacks raw media and only transcript
  text was provided. This is false for this run: the ledger links the MP4,
  `inspect_media` and `read_media` succeeded, and the report itself transcribes
  three decoded frames. Absence of independent real-world footage does not mean
  the attached synthetic video is absent.
- The actual missing source pixels belong to `img-note-002`, an authored
  inspection-tag annotation with no attached image. The report cites that source
  but omits this gap. It also omits that video inspection sampled three frames,
  rather than examining every frame. Both limitations were explicit review
  criteria.

## Claim-by-claim review

| Report element | Review |
| --- | --- |
| Scope | Correct Riverwatch target and connected Silt/Northline dependencies; no arts-event decoy or institute-wide delay asserted. |
| Summary | Correct September 3 ready versus September 5 delayed source claims and supported supplier path. “Currently” pending should remain tied to the September 4 fixture records. Lack of independent corroboration is correct; it must not be confused with lack of attached video. |
| Finding 1 | Cited sources assert delayed on September 5. Wording presents that as the established state, while finding 2 says reconciliation remains unresolved. Prefer explicitly attributed source claims; the dated conflict has not established which status is correct. |
| Finding 2 | Correct dated register claim and unresolved reconciliation, supported by `tbl-003`. |
| Finding 3 | Field-deployment dependency supported by `memo-001` and `memo-003`. The summary also gives the supported Northline supplier link. Supplier's external status is omitted, but no false hierarchy membership is asserted. |
| Finding 4 | All three cited sources record pending acceptance. Shared-origin limitation correctly prevents treating their agreement as independent corroboration. No defect inference is made. |
| Readiness conflict | Actual disagreement and both record dates preserved; correct sources cited. |
| Shipping conflict | Correct September 2 register/September 14 arrival versus September 5 notice/September 19 revision, supported by `tbl-006` and `memo-004`. Expected/revised terminology does not claim receipt, but the explicit source qualification that both dates are plans and neither proves delivery is omitted. |
| PNG observation | Exact visible board text matches source pixels. |
| Video observations | All three transcriptions match independently decoded pixels, including the crucial “have not established” at 00:29. No invented speaker-role or audio observation. |
| Limitations 1, 3, 4 | Correct synthetic provenance, limits of authored role labels, and nonindependence of repeated acceptance claims. |
| Limitation 2 | No audio processing was performed, and this attached caption-only fixture has no audio. |
| Limitation 5 | False missing-video claim; decisive rejection above. |
| Follow-up | Reconcile existing readiness and shipping records; a separately qualified real-entity application is appropriate future work. These tasks do not externally verify fictional Riverwatch. |

The report has four findings and two conflicts, meeting the requested counts.
Its narrative contains 314 whitespace-separated words, excluding title, IDs,
and field labels; this Riverwatch question imposed no 200-word cap.

## Workflow and provenance checks

- Twelve successful MCP calls: identity search, target-rooted traversal,
  unfiltered inventory for all three returned entities, five individual evidence
  reads, two media inspections, and two media reads. The inventory returns full
  records: all nine connected evidence records were retrieved, including both
  graph-edge proofs. Structural coverage is complete; analytic adequacy is separate.
- Image and MP4 source hashes match. Video requested seeks were 0, 14.5, and 29
  seconds; actual source timestamps were 0, 15, and 29 seconds. Report locators
  correctly use returned timestamps. The 00:29 observation no longer converts
  “not established delayed” into “not delayed.”
- All nine ledger locators, dates, and text hashes match the corpus. Dataset
  fingerprint is `7328e186691e7956ac440b1acd28391b6a2e022292b2c28c0104af6d0139cd67`.
  All six implementation hashes in run metadata match the saved
  [v7 source snapshot](../../evaluations/local-pilot/implementation-v7/README.md).
- Qwen3.5-4B Q4_K_M used the pinned
  [candidate launch profile](../../evaluations/local-pilot/runtime-profile-qwen35-01.json).
  Report synthesis requested a 1,024-token thinking budget. Private reasoning is
  not saved. The profile records operator settings, not independent server attestation.
- Fifteen total actions, 1,028.406 seconds: twelve MCP calls, one rejected finish
  intent before the remaining video inspection, an accepted finish intent, and
  one report generation. No analytic report rejection occurred in software.

Runtime guards accepted this report, but they did not detect its false account
of available media. This preserved failure must not be presented as an accepted
analytic showcase.
