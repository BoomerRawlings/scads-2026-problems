# Riverwatch13: 9B investigation rejected by source review

Separate AI review of the known, authored development fixture under the
[unchanged protocol](../../evaluations/local-pilot/REVIEW-PROTOCOL.md).
The software accepted the report; source review rejects an unsupported
qualification in finding 4. This is not human labeling, held-out evaluation,
or a general-accuracy result.

The [report JSON](report.json), [metadata](run-metadata.json),
[trace](tool-trace.json), [ledger](evidence-ledger.json), report Markdown and
both isolated observation files are byte-identical copies from
`runs/local-riverwatch-13/`. Copying occurred only after rechecking
`phase=finished`, `status=complete`. No original text or JSON was edited;
Markdown links already resolve from this example location. Report SHA256:
`8a753eb3f955a96f81cd24b75e0eeffdf7937bee4f59aa7e94e7417219e32613`.
Metadata SHA256:
`7188f937e688100e31c44ff85d3c05b6a5b5d3c7eff55b163ee1bf54f89b06f0`.

## Verdict and remaining gaps

Finding 4 says pending acceptance establishes **"only a procedural delay."**
Its cited `tbl-005` and `memo-003` establish pending acceptance and a calibration
requirement before field release. They explicitly caution that pending acceptance
does not establish defective components. They do not establish that the delay is
exclusively procedural or rule out substantive causes. The qualification adds
unsupported certainty to an otherwise supported pending-status finding.

The report also leaves two requested distinctions incomplete:

- Finding 3 explains Riverwatch → Silt, but no finding explains the Silt →
  Northline supplier relation or Northline's external status. Both are available
  in retrieved, cited `memo-003` and the actual graph. Retrieval and a source link
  do not themselves complete the narrative synthesis of the full path.
- Shipping retains both values and supporting source IDs, and its predicate is
  `expected_arrival`. The narrative never explicitly states that these are plans
  and neither source establishes physical receipt. This is a qualification
  omission, **not an invented claim that delivery occurred**.

Readiness attribution improves: findings 1 and 2 now describe what dated sources
record, retain both ready/delayed claims, and state that reconciliation remains
unresolved. That improvement and the correct fixed overview do not repair the
unsupported "only" in finding 4 or the remaining synthesis gaps.

## Claim-by-claim review

| Report element | Review |
| --- | --- |
| Scope and identity | Correct Riverwatch target and relevant Silt/Northline scope. No unrelated arts-event status, institute-wide halt or supplier misconduct is imported. |
| Fixed overview: scope | Nine actually retrieved eligible records, three returned/inventoried entities and zero exclusions. Exact counts and source lineage match reconstruction. |
| Fixed overview: differences | Ready/delayed and both expected-arrival values retain source IDs and record dates. The host describes unresolved structured-assertion candidates, without adjudicating truth or interpreting all source prose. |
| Finding 1 | Correctly attributes delayed readiness to later sources and identifies September 5. The cited annotation, memo and transcript support that record-level claim. It does not adopt delayed readiness as independently established current truth. |
| Finding 2 | Correct September 3 ready register, earlier date and explicitly unreconciled status. Both dated readiness claims remain available for review. |
| Finding 3 | `memo-001` and `memo-003` support Riverwatch's field-deployment dependency on Silt acceptance. The remaining supplier edge is not synthesized. |
| Finding 4 | Pending acceptance is supported by `tbl-005` and `memo-003`; lack of proof of defects is also supported. "Only a procedural delay" is unsupported, because it narrows the cause beyond those sources. Decisive rejection above. |
| Readiness conflict | Correct dates, differing values and citations. No recency-based correction or resolution is claimed. |
| Shipping conflict | Correct September 19 versus September 14 values and source IDs; source dates remain in the fixed overview. Expected-arrival predicate provides some context, but explicit planned/no-receipt qualification is missing. No actual receipt is asserted. |
| PNG observation | Caption text, date and synthetic provenance match actual pixels. Cosmetic shorthand says the text is black on a light background; body/footer text is dark green, with white header text on dark green. Original wording remains unchanged; this does not drive rejection. |
| Video 00:00 | All quoted captions/footer match independently decoded pixels, including the release hold until Silt passes acceptance. |
| Video 00:15 | Correct captions and September 5 footer. The observation does not import the register's September 3 date into the pixels. |
| Video 00:29 | Correct captions/footer; preserves "have not established" about other activities without converting uncertainty into a denial of delay. |
| Limitations | All five host-derived entries match handling: actual PNG/MP4 pixels, sampled frames, no audio, no declared/available inspection-tag image, bounded scope and shared synthetic provenance. |
| Follow-up | Empty under the declared-synthetic host policy, not model-authored recommendations. |

Four findings and two conflicts meet the requested counts. Findings,
qualifications and conflict descriptions contain 104 whitespace-separated words;
the fixed overview, pixel observations and host limitations are additional.

## Source, pixel and construction verification

- Fifteen successful MCP calls retrieved all nine connected records and both
  graph-edge proofs. Inventories cover `riverwatch`, `silt_sensors` and
  `northline`; no inventory/proof obligations remain. The unrelated arts source
  is absent.
- Twenty-one actions, 2,042.890 seconds: 15 MCP calls, two rejected finish
  intents requiring remaining media inspection, one accepted intent, two isolated
  observation requests and one report synthesis. No software report rejection.
- Image call 12 produced [observation 01](media-observation-01.json); video call
  15 produced [observation 02](media-observation-02.json). Original PNG pixels
  and independently decoded MP4 frames at 0/15/29 seconds were visually reviewed.
  Requested seeks were 0/14.5/29; actual PTS are 0/245760/475136 with time base
  `1/16384`. Report locators identify returned frames, not just requested seeks.
- Both isolated input fingerprints reconstruct from source pixels, audited
  labels, observation schema and generation settings. Both saved output hashes
  match metadata. All four observations are reused exactly in the final report;
  host limitations and empty follow-up match their declared constraints.
  Exact reuse is consistency evidence, not semantic verification.
- All nine ledger source IDs, locators, record dates and indexed-text hashes
  match; both source-media hashes match. All 15 dataset-file hashes and aggregate
  fingerprint match:
  `7328e186691e7956ac440b1acd28391b6a2e022292b2c28c0104af6d0139cd67`.
- All six implementation hashes recorded by the run match the frozen
  [v11 snapshot](../../evaluations/local-pilot/implementation-v11/snapshot.json).
  All eight files in that historical snapshot verify against its manifest.
  The current working core matched those hashes during the completed-run review;
  later development does not change this run's historical implementation.
- Offline reconstruction using frozen files and the actual 15-call trace matches
  every compact source/graph hash and call-lineage entry, scope and current-run
  fact. Sixteen returned full-record occurrences reduce to nine distinct exact
  records, with seven duplicates, two identity/graph results, zero errors and
  four omitted raw image blocks. Original planner/isolated requests received
  pixels; compact final synthesis used the fixed observations and handling facts.
- Reconstructed canonical report messages match SHA256
  `3cf2a04e4ecb8557d774dc09023361b957f527ff2613c383dfce0b98c9170542`
  and 18,203 UTF-8 bytes. This validates reconstruction from saved
  trace/fingerprints, not replay of a persisted raw HTTP conversation. The hash
  covers messages only, excluding response schema, model/settings and HTTP
  envelope.
- The host overview reconstructs exactly: nine eligible records, nine complete
  string-valued assertions, two differing groups, zero malformed assertions,
  zero missing assertion lists and zero exclusions. Both returned proof IDs,
  all full-record hashes and every assertion reference match. Final summary
  SHA256 is
  `def60ea13d6106a125e3e86498149cbcb7c2311c4574543853e2c7162cabb602`,
  with 1,333 UTF-8 bytes under the 4,096-byte cap. Frozen v11 constructs the
  response-schema constant and checks equality. This does not establish the
  correctness of model-authored findings.

## Reproduction binding and limits

This run combines **v11 core code with the separately pinned 9B assets and
launch profile**. The v11 snapshot's saved 4B manifest and README invocation
describe Riverwatch12, not Riverwatch13. Reproduction needs all three bindings:

- [v11 core snapshot](../../evaluations/local-pilot/implementation-v11/README.md),
  with `local_agent.py` SHA256
  `a364043ac0617bab8d94ef21f4fabe79e9096ba67b9456c8fb2b457f11f86d82`.
  Use its seven code/schema/requirements files and the unchanged dataset.
- [9B asset manifest](../../docs/runtime-candidate-qwen35-9b.json), SHA256
  `b355b525da2840eb5c2b72a3ee612277f5554657db34b243fcd506fabdfdc43f`.
  It selects Unsloth Qwen3.5-9B Q3_K_M/F16 at revision
  `3885219b6810b007914f3a7950a8d1b469d598a5`, with pinned asset sizes/hashes and
  the b11457 Windows ARM64 CPU runtime. Select `--profile candidate-9b` in
  [runtime setup](../../docs/local-runtime.md).
- [9B launch profile](../../evaluations/local-pilot/runtime-profile-qwen35-9b-01.json),
  SHA256 `85171f4064be8398c268c52b1dcab15d27d97376747ca8fa4eb28645742613da`.
  It records 16,384 context tokens, eight CPU threads, one slot, batch/microbatch
  128/32, q8_0 KV cache, memory mapping, disabled repacking (`--no-repack`), and
  64–256 image tokens. Its settings are operator-recorded, not server attestation.

With that server/profile running, the investigation invocation is:

```powershell
.\.venv\Scripts\python.exe local_agent.py riverwatch --question "What do the sources establish about readiness and dependencies? Keep the report concise: at most four findings, two conflicts, and short explanations." --base-url http://127.0.0.1:18571/v1 --model Qwen3.5-9B-Q3_K_M --max-steps 24 --timeout 2700 --request-timeout 1200 --report-thinking-budget 1024 --grounded-media --compact-synthesis --evidence-summary --output-dir runs/reproduced-riverwatch-13
```

Planning and isolated observations use non-thinking temperature 0/seed 0.
Report synthesis requests 1,024 thinking tokens at temperature 0.6/seed 0;
usage records 4,971 prompt and 2,619 completion tokens. Private reasoning text
was not saved. The advertised model alias does not independently attest to
loaded weights. Matching inputs does not guarantee identical or correct output.

The [resource observation](../../evaluations/local-pilot/resource-probe-riverwatch13.json)
is one shared-host sample during a decision step. Its peak includes startup and
the earlier source-only probe; it is not an isolated investigation benchmark or
minimum-RAM specification. Downloads/startup are excluded from runner elapsed
time. Model, quantization, batch/repacking settings and time budget differ from
the preceding 4B run, so this is not an isolated causal comparison.

This completed known-fixture investigation demonstrates preserved retrieval and
media provenance plus improved readiness attribution. It still fails substantive
source review. It establishes neither accepted free-local analytic quality nor
real-world accuracy, natural-scene/audio performance, scale or analyst time savings.
