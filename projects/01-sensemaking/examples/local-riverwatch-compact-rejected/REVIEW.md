# Riverwatch11: compact synthesis, still rejected by source review

Separate AI review of the known, authored development fixture under the
[unchanged protocol](../../evaluations/local-pilot/REVIEW-PROTOCOL.md).
The software accepted the report; substantive source review rejects its summary.
This is not human labeling, held-out evaluation, or a general-accuracy result.

The [report JSON](report.json), [metadata](run-metadata.json),
[trace](tool-trace.json), [ledger](evidence-ledger.json) and both isolated
observation files are byte-identical copies from `runs/local-riverwatch-11/`.
Copying occurred only after `phase=finished`, `status=complete`. Markdown was
rerendered for the example location and remains byte-identical too. No analytic
wording was edited. Report SHA256:
`cbfcb76104267b8a6cbd7806f5d81c5ea187ded621e7fb789136e0aead58015c`.

## Why rejected

The summary says multiple synthetic records **establish** delayed readiness.
The source material supports a September 5 delayed claim and a September 3 ready
claim whose reconciliation remains explicitly unresolved. Several shared-origin
fixture records do not settle which claim should be adopted as the final state.
The report itself retains that unresolved status in finding 3, so its opening
conclusion is stronger than its evidence and qualifications.

The earlier text-only misdescription is gone, and shipping now explicitly says
no physical delivery is confirmed. The pixels, missing inspection-tag image,
sampled-video limitation and synthetic provenance are correctly represented.
Those improvements do not repair the summary's substantive overstatement.

## Claim-by-claim review

| Report element | Review |
| --- | --- |
| Scope and identity | Correct Riverwatch target and connected Silt/Northline scope. No unrelated arts event, institute-wide delay, supplier misconduct or sensor-defect conclusion. |
| Summary: readiness | Unsupported adjudication of unresolved dated claims; decisive rejection above. Pending acceptance is supported as the delayed source's explanation, not independently verified current truth. |
| Summary: dependencies | The source chain links Riverwatch deployment to the Silt batch supplied by Northline. The summary compresses this to shipping-schedule dependence; no delivery or institute membership is invented. |
| Finding 1 | Correctly says delayed is **recorded**, with qualification attributing it to synthetic annotations/text. Sources and citations support that record-level statement. |
| Finding 2 | `memo-001` and `memo-003` support the Silt acceptance dependency and release condition. No defect inference is made. |
| Finding 3 | `tbl-003` supports the September 3 ready entry, its earlier date and unreconciled status. This finding conflicts with the summary's stronger certainty. |
| Finding 4 | Register/notice support the revised expected dates. Qualification explicitly preserves September 14 versus September 19 and states no physical delivery is confirmed. Correct plan-versus-receipt distinction. |
| Readiness conflict | Correct ready/delayed difference, both source dates and supporting citations. No proof of correction is supplied or established. |
| Shipping conflict | Correct September 2 register/September 14 plan versus September 5 notice/September 19 revised plan. Finding 4 supplies the explicit no-receipt caveat. |
| Video 00:00 | Quoted captions and footer match independently decoded pixels, including the release hold pending acceptance. |
| Video 00:15 | Captions/footer match. The visible calendar date is September 5; the observation does not import the register's September 3 date into the pixels. |
| Video 00:29 | Correct caption and footer; preserves "have not established" about other activities without turning uncertainty into a denial of delay. |
| PNG | All quoted text/date/provenance matches. Cosmetic error remains: footer is pale green, not dark green. This does not drive the analytic rejection; original wording remains unchanged. |
| Limitations | All five host-derived entries match actual handling: PNG/MP4 inspected, no audio, sampled frames, no declared/available inspection-tag image, bounded scope, and shared synthetic origin. |
| Follow-up | Empty under the declared-synthetic host policy, not model-authored recommendations. |

The full Riverwatch → Silt → Northline path is supported by cited `memo-003`
and the actual graph, but the narrative does not spell out the second supplier
relation or Northline's external status. No false hierarchy membership is
asserted. Four findings and two conflicts meet the requested counts. The
model-authored summary/findings/qualifications/conflicts contain 125
whitespace-separated words; fixed observations/limitations are additional.

## Evidence and construction checks

- Seventeen successful MCP calls; all nine connected records and both graph-edge
  proofs retrieved. Inventories cover `riverwatch`, `silt_sensors` and `northline`;
  no missing inventory/proof IDs remain. Repeated inventory is not additional
  independent corroboration.
- Twenty-three actions, 988.485 seconds: 17 MCP calls, two rejected finish intents
  requiring remaining media inspection, one accepted intent, two isolated
  observation requests and one final synthesis. No software report rejection.
- Original PNG and newly decoded MP4 frames at 0/15/29 seconds were inspected.
  Requested seeks were 0/14.5/29; actual source PTS are 0/245760/475136 under
  time base `1/16384`. Report locators identify returned frames. Caption handling
  is not natural-scene or audio validation.
- All nine ledger IDs, source locators, dates and indexed-text hashes match;
  both source-media hashes match. All 15 dataset-file hashes and aggregate
  fingerprint match the frozen dataset:
  `7328e186691e7956ac440b1acd28391b6a2e022292b2c28c0104af6d0139cd67`.
- All six metadata implementation hashes match the
  [v10 snapshot](../../evaluations/local-pilot/implementation-v10/README.md).
  All eight snapshot code/schema/requirements/manifest files match their saved
  hashes and current frozen files. Runtime and fixture files were not edited.
- Both original [video](media-observation-01.json) and
  [image](media-observation-02.json) output hashes match metadata; source-call
  numbers and locator ordering match actual successful media calls. All four
  observations are reused exactly in the final report. Host-authored limitations
  and empty follow-up also match their declared constraints. Exact reuse is
  consistency evidence, not semantic validation.
- Compact metadata accounts for 25 full-record occurrences reduced to nine
  distinct exact records, two identity/graph results, zero errors, and four
  omitted raw image blocks. Record/graph hashes and call lineage were checked
  through offline reconstruction against frozen sources and the actual trace.
  Reconstructed compact messages match the saved SHA256:
  `ac61d0f4b14b8a068cb9e23dce1291e0d5b74e4e85c52bb95294c47f0176d2ab`,
  and 16,929 canonical UTF-8 bytes. This validates reproducible message
  construction; it is not a replay of a persisted raw HTTP conversation.
- The metadata explicitly scopes that hash/count to canonical **report messages
  only**. It excludes response schema, model/settings and HTTP envelope; it is
  not a wire-byte measurement. The synthesis receives exact retrieved source
  records, identity/graph results, current-run facts and fixed isolated outputs.
  The planner and isolated observers received original pixels; compact final
  synthesis did not. No observations are attributed to that final step.
- Same [recorded Qwen3.5-4B profile](../../evaluations/local-pilot/runtime-profile-qwen35-01.json)
  and question as Riverwatch10; this run additionally enables
  `--compact-synthesis`. Report synthesis requested 1,024 thinking tokens,
  temperature 0.6 and seed 0. Usage records 4,640 prompt/2,347 completion tokens;
  private reasoning text was not saved. Operator-recorded settings and the
  advertised model alias are not independent server/loaded-weight attestation.
- The [resource probe](../../evaluations/local-pilot/resource-probe-riverwatch11.json)
  is one observation during shared-host work, not an isolated memory benchmark
  or minimum specification. Downloads/startup are excluded from elapsed time.
  A smaller reported context than Riverwatch10 does not establish a general
  latency gain or quality improvement.

Compact synthesis preserved provenance and reduced this report's input size.
The unresolved readiness claim still became an overconfident summary. This
preserved development failure is not an accepted free-local analytic showcase.
