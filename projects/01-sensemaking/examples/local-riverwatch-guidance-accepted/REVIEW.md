# Riverwatch14 — accepted known-fixture development run

**Verdict: accepted under the unchanged local source-review protocol, with the
wording and cosmetic caveats below.** The software accepted the report; a separate
AI reviewer checked its original claims, sources, decoded pixels and construction.
This is one inspected, agent-authored synthetic development case, not held-out
evaluation, independent human labeling, general model accuracy or project-wide
acceptance. Earlier rejected runs remain rejected.

Review date: 2026-10-07. Governing [protocol](../../evaluations/local-pilot/REVIEW-PROTOCOL.md)
SHA256: `bf7029ad042e4b8803482800df6e8618dd791d6919d629a6864fb52018688436`.
No criterion was changed for this run. The original [report JSON](report.json),
[report Markdown](report.md), [trace](tool-trace.json), [evidence ledger](evidence-ledger.json),
[final metadata](run-metadata.json) and both isolated observations were copied
byte for byte only after metadata read `phase=finished`, `status=complete`.
No model claim or observation was corrected. Both original and saved Markdown
already have valid source links; no rerender was necessary.

## Claim-by-claim decision

| Element | Source review |
| --- | --- |
| Scope and identity | Correct Riverwatch Pilot, Silt Sensor Batch and Northline scope. No unrelated arts-event status, institute-wide halt or supplier misconduct is imported. |
| Fixed overview | Nine actual eligible source IDs, three returned/inventoried entities, two differing assertion groups and zero exclusions match reconstruction. It retains dated ready/delayed and expected-arrival values as unresolved candidates; it does not resolve truth by recency. |
| Finding 1 | “Readiness is recorded as delayed” attributes the claim to the records. The qualification retains the September 3 ready register and September 5 delayed sources. The cited `memo-001` itself states the earlier register's date/value; the register is also cited in the conflict and host overview. Together these preserve the disagreement rather than assert independently established current readiness. |
| Finding 2 | `memo-001` and `memo-003` support the complete Riverwatch deployment → Silt Sensor Batch → Northline Instruments path, with distinct dependency and supply relations and pending acceptance. The report does not assert organizational containment or control. |
| Finding 3 | `memo-004` reports a revised **expected arrival** of September 19; `tbl-006` reports September 14. The qualification explicitly calls both plans and denies confirmed delivery. The record dates and IDs remain in the overview/source list. “Revised shipping date” is imprecise terminology: the source establishes expected arrival, not a dispatch date. In this report the overview and conflict predicate explicitly identify `expected_arrival`; no shipment or receipt event is asserted. This wording caveat does not overturn the preserved planning-versus-event distinction. |
| Finding 4 | `memo-003` and `tbl-005` explicitly support pending acceptance, required calibration and the absence of an established defect inference. The report no longer turns this into an exclusive “only procedural” explanation. It neither declares sensors defect-free nor invents a defect rate/count. |
| Readiness conflict | Correct dated disagreement and supporting IDs. The overview explicitly leaves it unresolved. No later-record correction is asserted. |
| Arrival conflict | Both source IDs and `expected_arrival` predicate are correct. “Shipping dates” shares finding 3's terminology caveat; the differing plans may reflect a revision, not necessarily incompatible current truths. The host overview calls these unresolved candidates rather than adjudicated contradictions. |
| PNG observation | Visible caption, date and synthetic provenance match pixels. “Text is black on a light background” is cosmetic shorthand: body/footer text is dark green, header text white on dark green. Original wording is preserved; it does not change the analytic evidence. |
| Video 00:00 | Correct visible release-hold and acceptance caption, header, September 5 date and synthetic/no-audio footer. |
| Video 00:15 | Correct ready-register caption and September 5 frame footer. No September 3 document date is imported into these pixels. |
| Video 00:29 | Correct deployment scope and “have not established” uncertainty about other activities. It does not convert missing evidence into a denial of other delays. |
| Limitations | All five host-authored entries match the actual handling: source PNG/video pixels, sampled frames, no audio, missing inspection-tag attachment/pixels, bounded scope and shared synthetic provenance. |
| Follow-up | Empty under the declared-synthetic host policy; not model-authored recommendations. |

The report omits the explicit word “external” from its supplier finding.
[The supply memo](../../data/documents/sensor_supply_note.txt) establishes that
Northline is outside the institute's hierarchy. Including that fact would improve
the presentation; the original report makes no contrary hierarchy inference, and
the protocol's cited dependency-path requirement is satisfied. This acceptance
does not claim every useful detail was repeated or every word was ideal.

Four findings and two conflicts meet the requested counts. Findings,
qualifications and conflict descriptions total 104 whitespace-separated words;
the host overview, isolated pixel observations and host limitations are additional.

## Sources and pixels

The reviewer checked every finding and conflict against its cited records,
including the [dependency review](../../data/documents/riverwatch_dependency_review.txt),
[supply memo](../../data/documents/sensor_supply_note.txt),
[arrival notice](../../data/documents/northline_shipping_notice.txt),
[dated registers](../../data/records.csv),
[authored image annotation](../../data/annotations/riverwatch_planning_board.txt)
and [authored transcript](../../data/transcripts/riverwatch_coordination.txt).
Record text and attached caption pixels remain separate evidence modalities with
shared authored origin; agreement is not independent corroboration. Authored
annotation/transcript headers do not negate this run's actual pixel calls.

The [source PNG](../../data/media/riverwatch-board.png) and independently decoded
[source video](../../data/media/riverwatch-review.mp4) frames were visually checked.
A separate ffmpeg decode plus ffprobe inspection confirmed frames at 0, 15 and
29 seconds, PTS `0`, `245760`, `475136`, time base `1/16384`. Those decoded RGB
pixels match the previously independently viewed frames from the same immutable
source. Requested offsets were 0, 14.5 and 29 seconds; the middle observation
correctly uses the returned 15-second frame. These are caption fixtures, not
natural-scene understanding, speech recognition or full-video review.

Source-media SHA256 values:

- PNG: `48c53e82faa004de5e1f1784913208b78f335980d8e75fe8af05a570f9376678`.
- MP4: `12570bc12c69eb2ef39e1097aeacbcac95b708b7bcba9c949f25f256239086d9`.

All nine ledger source/date/indexed-text hashes and both media hashes match the
current frozen corpus. Indexed text hashes and raw file hashes are distinct
measurements where text loading normalizes newlines. The genuine `img-note-002`
gap is preserved: authored inspection-tag text was retrieved, but no attachment
was declared, inspection reported unavailable, and no pixels were returned.

## Actual run and constrained construction

The actual 15-call trace was replayed offline against the verified frozen tool
implementation; this reconstruction made no model request. Trace, returned graph
coverage, source records and current-run facts matched the saved metadata.
All nine connected records and both edge proofs (`memo-001`, `memo-003`) were
retrieved; inventories covered `riverwatch`, `silt_sensors` and `northline`.
The unrelated arts record was absent.

The run used 21 actions and 2,538.563 seconds: 15 MCP calls, two rejected finish
intents requiring remaining media inspection, one accepted finish intent, two
isolated observations and one report synthesis. There were no report rejections
or invalid actions. Final report usage was 5,044 prompt tokens and 2,607 completion
tokens. Private reasoning was returned during synthesis but is not saved here.

Image call 12 produced [observation 01](media-observation-01.json); video call 15
produced [observation 02](media-observation-02.json). Both original files are
byte-identical to reviewed trial13 observations and were reused exactly in the
final report. Their pixel-only input fingerprints were independently reconstructed
from actual returned pixels, source/locator labels, observation schema and settings:

| Observation | Input SHA256 | Original output SHA256 |
| --- | --- | --- |
| PNG | `92d3bf2540fc6a63f96f98c63ba27315790c69cfa097da28963d0a420e728c1a` | `d387ae338da6b9bce08b5a432431c077f016d25859eea02397fd8618e51f8151` |
| Video | `696027c913b935fd3101a7da8ba1f763c51dfc09a6bbd7f2a153c0397e323538` | `5a55fb9f3faea987f1013f15efcf40f74320d447dd4f3543d786ab15c190f1e2` |

Compact synthesis retained 16 actual evidence occurrences as nine exact record
versions, removing seven identical duplicates. It retained two identity/graph
results, no tool failures and their call lineage. Four raw image blocks were
omitted only after retaining isolated observations and current-run media facts.
No unseen evidence or replacement source summary was inserted.

Reconstructed compact input: **18,621 UTF-8 bytes**, SHA256
`db7e32b5409b71f6a54461151cd154bf5e829346be74ba57aa0ccdeeeb3b7e71`.
The declared scope is `canonical_report_messages_only`: canonical message JSON,
excluding the response schema, model/settings and serialized HTTP envelope.
It is not a wire-byte or complete-request fingerprint.

The host overview is **1,333 UTF-8 bytes**, SHA256
`def60ea13d6106a125e3e86498149cbcb7c2311c4574543853e2c7162cabb602`.
Reconstruction verified all record/assertion indices, exact source dates/values,
nine eligible source IDs, nine comparable assertions, two differing groups and
zero exclusions. Eligibility uses actual target associations, returned graph
scope and retrieved edge proofs. It neither resolves disagreement nor substitutes
for this semantic review. Final overview equality/hash/length and all fixed
limitations, observations and follow-up fields were checked separately.

## Reproduction binding

- Target: `riverwatch`.
- Exact question: “What do the sources establish about readiness and dependencies? Keep the report concise: at most four findings, two conflicts, and short explanations.”
- Started: `2026-10-07T11:15:41.553668+00:00`; final elapsed `2538.563` seconds. Metadata supplies no separate finish timestamp.
- Model alias: `Qwen3.5-9B-Q3_K_M`, obtained from the local `/v1/models` endpoint. Local loopback llama.cpp-compatible HTTP; no paid runtime API used.
- [Frozen v12 implementation](../../evaluations/local-pilot/implementation-v12/README.md): all eight snapshot files and six metadata-recorded core files verified. `local_agent.py` SHA256 `ac422d30296a19f4496e296141a5390850e6b7aeff7e5e617d5ba4f6af4`.
- [Snapshot manifest](../../evaluations/local-pilot/implementation-v12/snapshot.json) SHA256 `39eea79d339b8c4a205f9869cd19d3a49a7b5f72ad8151e830f98bff3d557378`.
- Dataset SHA256 `7328e186691e7956ac440b1acd28391b6a2e022292b2c28c0104af6d0139cd67`; all 15 recorded files verified. No fixture edit for this run.
- [9B runtime manifest](../../docs/runtime-candidate-qwen35-9b.json) SHA256 `b355b525da2840eb5c2b72a3ee612277f5554657db34b243fcd506fabdfdc43f`; pinned Unsloth revision `3885219b6810b007914f3a7950a8d1b469d598a5`, Q3_K_M weights and F16 projector, llama.cpp b11457 Windows ARM64.
- [9B launch profile](../../evaluations/local-pilot/runtime-profile-qwen35-9b-01.json) SHA256 `85171f4064be8398c268c52b1dcab15d27d97376747ca8fa4eb28645742613da`: 16,384-token context, eight CPU threads, one slot, no GPU, batch128/microbatch32, q8_0 KV cache, flash attention, image64–256 tokens, no context shift/repacking, mmap. These are operator-recorded launch settings, not independent server attestation or a qualified minimum-resource profile.
- Planning and isolated observations: temperature0, seed0, thinking disabled; decision cap512, isolated-observation cap1536. Report: temperature0.6, seed0, 4096-token cap, requested thinking budget1024, top_p0.95, top_k20, min_p0, presence_penalty0.
- Limits: 24 actions, 2700-second overall/1200-second request timeout; 2,097,152 response bytes, 8,388,608 result bytes, 25,165,824 context bytes.
- Optional policies: `--grounded-media --compact-synthesis --evidence-summary`; guidance `question-path-and-qualification-v12`, schema policy `evidence-overview-opt-in-v11`.

The frozen snapshot README provides the exact command and overlay instructions.
This case binds v12 and the 9B profile; an older snapshot's 4B invocation is not
this run. Identical settings do not guarantee identical output. Runtime elapsed
time includes shared-host workload and is not an isolated speed benchmark.
Installed model files, caches and private reasoning are not part of this example.

## Preserved artifact hashes

| File | Original/saved bytes | SHA256 |
| --- | ---: | --- |
| `report.json` | 6068 | `479c7bf7d1cd537d357bdd92697bdae85a2ba376ea8ccaec06786f4580846a8e` |
| `report.md` | 6018 | `a0450d3491eb699477f800fde07ed41e740938fc1577264e01b6fd02d3dc3df7` |
| `tool-trace.json` | 2070 | `6fb8aa176e560b1455290407d9d1f908eddf1d6b3832c0a776d8700382df160e` |
| `evidence-ledger.json` | 2031 | `5a717c0f29a38491bcfc084a31d868d959f5c128c86bdb7ad21d11f239b81eea` |
| `run-metadata.json` | 25631 | `b7fff638ed8cca49fda6776ed0ec5f1b385acda9b8ab90d64fa0d9d49ee333ee` |
| `media-observation-01.json` | 490 | `d387ae338da6b9bce08b5a432431c077f016d25859eea02397fd8618e51f8151` |
| `media-observation-02.json` | 1339 | `5a55fb9f3faea987f1013f15efcf40f74320d447dd4f3543d786ab15c190f1e2` |

All seven saved files were compared byte for byte with completed trial14 originals;
local Markdown targets were checked. This accepted example supports a bounded
end-to-end free local workflow demonstration. Public-data analytic quality,
held-out performance, repeatability, broader scale, natural-scene/audio accuracy,
analyst-time savings and actual sibling-project integration remain unestablished.
