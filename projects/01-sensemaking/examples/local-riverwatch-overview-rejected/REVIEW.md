# Riverwatch12: fixed overview, model finding still rejected

Separate AI review of the known, authored development fixture under the
[unchanged protocol](../../evaluations/local-pilot/REVIEW-PROTOCOL.md).
The software accepted the report; substantive source review rejects finding 1.
This is not human labeling, held-out evaluation, or a general-accuracy result.

The [report JSON](report.json), [metadata](run-metadata.json),
[trace](tool-trace.json), [ledger](evidence-ledger.json) and both isolated
observation files are byte-identical copies from `runs/local-riverwatch-12/`.
Copying occurred only after `phase=finished`, `status=complete`. Markdown was
rerendered for the example location and remains byte-identical too. No analytic
wording was edited. Report SHA256:
`c4646e5cbd0d8beca8a0cd91878bcfc591c1b1ce4ebf5474b9e956a40f7d6ea5`.

## Why rejected

Finding 1 states **"Riverwatch Pilot readiness is delayed pending sensor
acceptance."** Its qualification identifies synthetic text and the absence of
independent corroboration, but does not qualify the disputed readiness state.
The sources support a September 5 delayed claim alongside a September 3 ready
claim whose reconciliation remains unresolved. Synthetic provenance alone does
not justify adopting one of those claims as the analytic finding.

The fixed overview, finding 4 and readiness-conflict entry retain the competing
claims. Finding 1 nevertheless presents delayed readiness as settled. The same
source-review boundary that rejected the earlier overconfident summaries applies
to model-authored findings. Correct host construction does not certify the rest
of the report.

The report also leaves the full supplier path implicit: the actual graph and
cited `memo-003` support Riverwatch → Silt Sensor Batch → Northline, but the
narrative does not expressly connect Northline as the Silt supplier or describe
its external status. That synthesis remains incomplete. No false hierarchy
membership, supplier misconduct or sensor-defect conclusion is asserted.

## Claim-by-claim review

| Report element | Review |
| --- | --- |
| Scope and identity | Correct Riverwatch target and connected Silt/Northline scope. No unrelated arts event or institute-wide delay is imported. |
| Fixed overview: scope | Nine actually retrieved eligible sources; target-rooted and inventoried scope both contain Riverwatch, Silt and Northline. Zero excluded records. Counts and eligibility match reconstruction. |
| Fixed overview: differences | Exact supplied ready/delayed values and both expected-arrival values retain source IDs and record dates. Differences remain unresolved candidates; recency does not adjudicate truth. The overview explicitly limits itself to structured assertions. |
| Finding 1 | Unsupported adoption of delayed readiness as the analytic state. Its cited sources contain that claim, but the qualification does not preserve the unresolved readiness dispute. Decisive rejection above. |
| Finding 2 | `img-note-002`, `memo-003` and `tbl-005` support pending acceptance and calibration before release. The qualification correctly says pending is not proof of defects. Citing authored inspection-tag text is not a claim that its missing image was inspected. |
| Finding 3 | `memo-004` and `tbl-006` support the revised expected dates. The explicit qualification correctly distinguishes planned arrival from physical delivery. |
| Finding 4 | Correct September 3 ready register and later delayed source claim; qualification preserves both for review. It does not resolve their disagreement and therefore does not repair finding 1. |
| Readiness conflict | Correct values, both source dates and supporting citations. No correction of the older register is established. |
| Shipping conflict | Correct September 2 register/September 14 plan and September 5 notice/September 19 revised plan. Finding 3 supplies the no-delivery caveat; a later source may explain the difference without proving receipt. |
| Dependency path | Actual traversal and retrieved edge proofs cover both edges. Narrative only partially synthesizes that path; supplier relation/external status remain implicit in cited source text. |
| Video 00:00 | Quoted captions/footer match independently decoded pixels, including the hold pending Silt acceptance. |
| Video 00:15 | Quoted captions/footer match. Visible date is September 5; the observation does not import the register's September 3 date into the pixels. |
| Video 00:29 | Correct text/footer; preserves "have not established" about other institute activities without converting uncertainty into a denial of delay. |
| PNG | All quoted text, date and synthetic provenance match. Cosmetic error: footer is pale green, not dark green. Original wording is preserved; this does not determine analytic rejection. |
| Limitations | All five host-derived entries match actual handling: PNG/MP4 inspected, no audio, sampled frames, no declared/available inspection-tag image, bounded scope and shared synthetic origin. |
| Follow-up | Empty under the declared-synthetic host policy, not model-authored recommendations. |

Four findings and two conflicts meet the requested counts. The model-authored
findings, qualifications and conflict descriptions contain 96 whitespace-separated
words. The fixed overview, observations and limitations are additional.

## Evidence and construction checks

- Seventeen successful MCP calls retrieve all nine connected sources and both
  graph-edge proofs. Inventories cover all three returned scope entities; no
  inventory/proof obligations remain. Repeated inventory is not independent
  corroboration.
- Twenty-three actions, 1,049.781 seconds: 17 MCP calls, two rejected finish
  intents requiring remaining media inspection, one accepted intent, two isolated
  observation requests and one final synthesis. No software report rejection.
- Original PNG and independently decoded MP4 frames at 0/15/29 seconds were
  inspected. Requested seeks were 0/14.5/29; actual source PTS are
  0/245760/475136 under time base `1/16384`. Caption handling does not establish
  natural-scene or audio accuracy.
- All nine ledger IDs, source locators, dates and indexed-text hashes match;
  both source-media hashes match. All 15 dataset-file hashes and aggregate
  fingerprint match the frozen dataset:
  `7328e186691e7956ac440b1acd28391b6a2e022292b2c28c0104af6d0139cd67`.
- All six metadata implementation hashes match the
  [v11 snapshot](../../evaluations/local-pilot/implementation-v11/README.md).
  All eight snapshot code/schema/requirements/manifest files match their saved
  hashes and current frozen files. Runtime and fixture files were not edited.
- Both [video](media-observation-01.json) and
  [image](media-observation-02.json) input fingerprints were reconstructed from
  the frozen source pixels, audited locators and isolated request construction.
  Both output hashes match metadata; all four observations are reused exactly
  in the report. Host limitations and empty follow-up also match their declared
  constraints. Exact reuse establishes consistency, not correctness.
- Offline tool reconstruction from frozen files and the actual trace reproduces
  all compact record/graph hashes, call lineage, scope and current-run facts.
  Metadata accounts for 25 full-record occurrences reduced to nine distinct
  exact records, two identity/graph results, zero errors and four omitted raw
  image blocks. The original planner/isolated observers received pixels;
  compact final synthesis received fixed observations and handling facts.
- Reconstructed canonical report messages match SHA256
  `6c0123166a600f037cff081a6f5c3d9003a611ed129bde292ee3e6dadc8aeaa4`
  and 18,579 UTF-8 bytes. This is reproducible message construction from the
  saved trace/fingerprints, not replay of a persisted raw HTTP conversation.
  The hash excludes response schema, model/settings and HTTP envelope.
- The overview reconstructs exactly from the same nine eligible records:
  nine complete string-valued assertions, two differing groups, zero malformed
  entries, zero records without assertions and zero excluded records. Both
  actual returned edge-proof IDs and every record/assertion reference match.
  Exact overview SHA256 is
  `def60ea13d6106a125e3e86498149cbcb7c2311c4574543853e2c7162cabb602`;
  its 1,333 UTF-8 bytes are below the 4,096-byte cap. The final summary matches
  that reconstruction byte-for-byte. Frozen source confirms the response-schema
  constant and post-response equality guard. These checks do not verify the
  semantics of model-authored findings.
- Same [recorded Qwen3.5-4B profile](../../evaluations/local-pilot/runtime-profile-qwen35-01.json)
  and question as Riverwatch11; this run additionally enables
  `--evidence-summary`. Report synthesis requests 1,024 thinking tokens,
  temperature 0.6 and seed 0. Usage records 5,042 prompt/2,736 completion tokens;
  private reasoning text was not saved. Operator-recorded settings and the
  advertised model alias are not independent loaded-weight/server attestation.
- The [resource probe](../../evaluations/local-pilot/resource-probe-riverwatch12.json)
  is one shared-host observation. Its recorded peak includes startup and this
  run; it is not an isolated investigation benchmark or minimum-RAM requirement.
  Downloads/startup are excluded from runner elapsed time. This run provides no
  general latency, scale or analyst-time-saving estimate.

The host overview repairs one output surface. The preserved model finding still
fails the unchanged source-review criterion. This development run is not an
accepted free-local analytic showcase.
