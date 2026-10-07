# Riverwatch09: accepted by software, rejected by source review

Independent AI review of a known, authored development fixture, following the
[unchanged predeclared protocol](../../evaluations/local-pilot/REVIEW-PROTOCOL.md).
This is not human gold labeling, a held-out evaluation, or evidence of general
accuracy. Every claim, qualification, conflict, observation, limitation, and
follow-up was compared with cited text, source PNG pixels, independently decoded
video frames, and this run's actual trace/provenance.

The [report JSON](report.json), [metadata](run-metadata.json),
[trace](tool-trace.json), and [ledger](evidence-ledger.json) are byte-identical
copies from `runs/local-riverwatch-09/`. Only [Markdown](report.md) source links
were rerendered. Model wording is unchanged. Original report SHA256:
`31f0a6e1dfb04140ad35564ca31af538ee548f3fdf0e60546e9a05c617dadbae`.

## Why rejected

- The 00:15 media observation says the frame references the `2026-09-03`
  register. The pixels say “The register still says ready. Show that dated entry
  next to the dependency review when preparing the status report.” The only
  visible calendar date is the frame footer, `2026-09-05`. September 3 comes
  from other text records; identifying that specific dated register is a
  cross-source inference, not something directly observed in this frame. The
  observation does not distinguish those sources.
- The missing raw inspection-tag image (`img-note-002`) remains unreported.
  Its annotation was retrieved and is relevant to sensor acceptance; the run's
  facts explicitly say no attachment was declared. The protocol required this
  genuine media gap to remain visible. Correctly mentioning sampled video does
  not cover the missing image.
- The first limitation calls all evidence synthetic fixture *text*, despite
  actual PNG/MP4 inspection. All sources are synthetic and share authored
  provenance; their modalities are not all text. The explicit false claim that
  the video is absent from Riverwatch08 is gone, but the account of evidence
  modalities is still inaccurate.
- Follow-ups ask to verify physical sensor calibration and determine whether
  the shipping revision implies supplier fault. These are invented entities and
  events; appropriate work is fixture consistency checking or a separately
  qualified real-data case. The source explicitly says pending acceptance does
  not prove a defect and the shipping notice does not establish a fault rate.
  The report does not assert supplier fault as fact, but this follow-up is
  unsupported and unsuitable for verifying this synthetic case.

## Claim-by-claim review

| Report element | Review |
| --- | --- |
| Scope | Correct target and connected Riverwatch/Silt/Northline scope. No arts-event contamination or institute-wide delay claim. |
| Summary | Correct source dates, ready/delayed disagreement, pending acceptance, and external supplier. “Sources indicate” and explicit unresolved reconciliation preserve attribution better than a bare status conclusion. |
| Finding 1 | Cited September 5 sources assert delay; qualification retains the conflicting September 3 ready claim. Supported as attributed fixture claims, not a verified readiness state. |
| Finding 2 | Riverwatch's dependency on Silt is supported by `memo-001` and `memo-003`; `tbl-005` supports the acceptance/release requirement, not independently the Riverwatch relationship. Graph and source text agree. |
| Finding 3 | `memo-004` reports the revised expected September 19 arrival; `tbl-006` provides the older September 14 alternative. Both source dates are correct. Expected-arrival wording does not claim delivery, but the explicit “both are plans; neither confirms receipt” qualification is omitted. |
| Finding 4 | Board and first video caption state the release hold. “Confirm delay status” should be understood as reading authored caption claims, not independently establishing delay; the qualification does not make that distinction clearly. It repeats finding 1. |
| Readiness conflict | Actual disagreement, both dates, and supporting citations are correct. |
| Shipping conflict | Actual dated register/notice difference is correctly retained. |
| PNG observation | Correct visible DELAYED text and pending-acceptance release hold. |
| 00:00 observation | Correct caption meaning: delayed and release held pending acceptance. |
| 00:15 observation | Ready-register caption meaning is correct; specific September 3 date is imported from other evidence without being labeled as inference. |
| 00:29 observation | Correctly retains “not established” for other institute activities. Does not reverse uncertainty into “not delayed.” |
| Limitation 1 | Synthetic/shared authorship is correct; “all evidence ... text” is inaccurate. “No independent corroboration exists” should be scoped to the supplied fixture. |
| Limitations 2–4 | Correct no-audio processing, sampled-caption coverage, unresolved dated readiness claims, and fictional entities/events. |
| Follow-up 1 | Reconciliation of the existing dated readiness claims is appropriate. |
| Follow-ups 2–3 | Physical verification and supplier-fault inquiry are not valid external verification of fictional events; see rejection reasons. |

Northline's external status and the Riverwatch-to-Silt dependency are correctly
stated. The full Silt-to-Northline supplier path is supported by cited `memo-003`,
but the findings do not explicitly spell out that second relation. There is no
claim that Northline belongs to the institute or that pending sensors are defective.

Four findings and two conflicts satisfy the requested counts. Narrative length:
263 whitespace-separated words, excluding title, IDs, and field labels. This
question imposed no 200-word cap.

## Workflow and provenance checks

- Twelve successful MCP calls: identity, rooted traversal, unfiltered inventory
  of all three returned entities, five individual source reads, two media
  inspections, and two media reads. The inventory supplied all nine full source
  records, including both graph-edge proofs. No disconnected citation was used.
- PNG and MP4 hashes match the inspected source assets. Requests at 0, 14.5, and
  29 seconds returned actual timestamps 0, 15, and 29. Every report locator uses
  a returned timestamp. Review compared those frames directly; no audio or
  natural-scene understanding was demonstrated.
- All nine ledger source locators, dates, and text hashes match. Dataset SHA256:
  `7328e186691e7956ac440b1acd28391b6a2e022292b2c28c0104af6d0139cd67`.
  All six recorded implementation hashes match the
  [v8 snapshot](../../evaluations/local-pilot/implementation-v8/README.md).
- Metadata's `synthesis_facts` correctly records inspected PNG/MP4, actual frame
  locators, undeclared tag-image attachment, no processed audio, and sampled-only
  video. Accurate supplied provenance did not guarantee accurate report wording.
- Same [Qwen3.5-4B candidate profile](../../evaluations/local-pilot/runtime-profile-qwen35-01.json),
  question and settings as Riverwatch08. Report synthesis requested 1,024 thinking
  tokens, temperature 0.6, seed 0. Private reasoning was not saved. Profile settings
  are operator-recorded, not independent server attestation.
- Fifteen actions in 946.297 seconds: twelve successful tool calls, one rejected
  finish intent requiring remaining media inspection, one accepted finish intent,
  and one report generation. No analytic report rejection occurred in software.

This run improved media-availability wording and disclosed sampled video coverage,
but it still fails the predeclared source/pixel review. Runtime acceptance is
separate from analytic acceptance; this is a preserved failure, not an accepted
free-runtime showcase.
