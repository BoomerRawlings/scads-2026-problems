# Public NCI 02: report-request timeout review

Verdict: **no public analytic acceptance**. The run failed with `model_timeout`
during report action 15 after 4,859.516 seconds. Its report request passed the
configured context admission check, then reached the request wall-clock deadline.
No final report, rejected report candidate, evidence ledger or media observation
was saved. This is an execution failure, not a semantic rejection of an answer.

Separate AI review completed 2026-10-07 under the unchanged
[public protocol](../PROTOCOL.md). This is a known, source-inspected development
case, not a held-out test, human-gold evaluation or general accuracy result.
No model was called during review. Original artifacts remain unchanged;
request/tool reconstruction used the frozen implementation and temporary local
MCP execution. Reconstructed requests were not saved as original network logs.
No private reasoning, raw prompts or token arrays were added to these artifacts.

## Originals and failure state

The original run directory contains exactly these three files. The preserved
copies were compared byte-for-byte with their originals after the run failed.
Metadata records `status=failed`, `phase=report`, `steps=15`; the failure path
retains its last phase, so there is no successful `phase=finished` to await.

| Original artifact | Bytes | SHA256 |
| --- | ---: | --- |
| [failure.json](failure.json) | 103 | `41cda7aa94a40f4d2e0b366bf750cd7867c06da81a884b3de48398623059555f` |
| [run-metadata.json](run-metadata.json) | 72,310 | `3447ef1bed3dae5d8819307b32202b413aca80eebefb38c020c9c4d96a82752c` |
| [tool-trace.json](tool-trace.json) | 2,261 | `58e6d945e1fb6f013959aaad7eba3f2d3f14185350f13067c7048d9034eb7998` |

Start: `2026-10-07T13:20:07.561564+00:00`. Recorded duration: 4,859.516 seconds.
Fourteen decision generations completed: twelve successful MCP calls and two
finish intents. The first finish intent was rejected for four missing full edge
proofs; the second passed structural preflight. One report generation was
attempted, with no completed response or usage record. Report rejections,
pre-MCP scope rejections and invalid actions are zero. The report's intended
status was `complete`; the run itself never achieved that status.

## Frozen reproduction and input bindings

The [v14 snapshot](../implementation-v14/snapshot.json), SHA256
`b83be396e34763732485d261f2923b0c823ee46836c8837a1b204bde02f7c6ef`,
is the review/replay implementation. All 13 frozen file hashes and all eight
run-recorded implementation hashes match. The replay imported and launched the
MCP server from this frozen directory, independent of later live-source changes.
Use its [reproduction instructions](../implementation-v14/README.md) for the
recorded invocation. This review does not assert that future live code stays
identical to the snapshot.

The target is `ror:040gcmg81`. The metadata question matches the snapshot and
the first protocol blockquote exactly, including line breaks. The reviewer's
source map was not appended to the question. Reconstructed system prompt SHA256:
`5f0fffeac5633dbf0310fa32cc39e009655aef29bfcd62c1a346909aaa635c59`.
Protocol SHA256:
`cc7bc6723ed026ad88cb667b07392988d801fab1840a68a252dc6bf14a0f4837`.

The complete dataset metadata/file map matches a fresh fingerprint:
`6f73d422781738700473016818d3e3de011f1082b5ba4b4df1b54481e4f72aa5`.
All 172 files listed by the
[import manifest](../../../datasets/public-research/imported-statements/import-manifest.json)
match their exact sizes and SHA256 hashes. Import-manifest SHA256:
`bf051f384b4fba6d944f470464995a437f6c953067fc577529f3f7ec1944a580`.
No live public-source refresh was used.

The run used the [4B/48k text profile](../runtime-profile-qwen35-4b-text-48k-01.json),
SHA256 `d4dd4cbbdc8d49af59acb9216c7aeab8034294e628832e01caed1b6036a31a56`,
and the [frozen 4B manifest](../implementation-v14/runtime-candidate-qwen35.json),
SHA256 `d69ec69654b82e4510898b99a5a0a1d744cdf2db6e7de3f8099b5f92405765e6`.
Model alias: `Qwen3.5-4B-Q4_K_M`; Unsloth revision:
`e87f176479d0855a907a41277aca2f8ee7a09523`; language-weight SHA256:
`00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`.
Runtime: llama.cpp b11457, Windows ARM64 CPU; archive SHA256:
`fab992671bd26ba4117da4f70f330fe1b9fe69eb8ce952281cabf4c5c5f2a17e`.
These are manifest/profile bindings, not a fresh installed-weight hash or
independent server attestation.

Operator-recorded runtime settings: one 49,152-token slot, eight generation/batch
threads, batch 128 / microbatch 32, Q8 KV caches, flash attention, mmap, disabled
weight repacking/context shift/optional saved-prompt caches, no projector or GPU
offload. Invocation bounds: 60 actions, 7,200 seconds total, 1,200 seconds/request,
262,144 serialized request bytes, 49,152 tokens. Catalog retrieval, grounded media,
compact synthesis and evidence overview were enabled. This local catalog profile
is text-only; enabling grounded-media construction did not supply any pixels.

Planning used temperature 0, seed 0, disabled thinking and 512 output tokens.
The report request used temperature 0.6, seed 0, 4,096 maximum output tokens,
1,024 reasoning-budget tokens, top-p 0.95, top-k 20, min-p 0 and presence penalty 0.
Model, quantization, context and budgets differ from NCI01; this is not an isolated
causal comparison of models or settings.

## Actual traversal, catalog and full reads

1. Exact-ID entity search resolved the ROR NCI node. Directed traversal at
   `max_hops=3` returned NCI plus four captured ROR children: `ror:00vkwep27`
   (DCEG), `ror:03v6m3209` (Frederick), `ror:05bjen692` (CCR), and
   `ror:05n6zrm60` (SWOG). Four outgoing `contains` edges declared eight proof IDs.
2. MCP call 3 cataloged those five nodes with empty query, `max_items=100`,
   `max_bytes=65536`, null initial cursor. It returned all 39 matching metadata
   cards in one terminal page. This completed inventory, not source retrieval.
3. Calls 4–7 read NCI's four complete child-relationship records. Decision 8
   attempted `finish/complete`; the guard correctly rejected it because the four
   reciprocal child-side proof records remained unread.
4. Decision 9 / MCP call 8 cataloged the four child nodes with the same empty
   query/page limits. This returned 25 cards in one terminal page, creating a
   second valid receipt. These cards overlap the first inventory; there are
   39 distinct discovered source IDs, not 64 distinct sources.
5. Calls 9–12 read all four reciprocal parent-relationship proof records.
   Decision 14's finish intent passed the structural workflow guard; action 15
   then attempted report synthesis and timed out.

Actual-response reconstruction matches both complete, snapshot-bound catalog
receipts, including page/binding hashes, call indices, exact scope and options.
There are no incomplete cursor chains, missing inventory entities or missing
edge proof IDs. Eight complete records were read; 31 discovered IDs remain
unread. All read records are ROR relationships. No full Wikidata statement,
crosswalk, external-ID or identity record was read. A discovered Wikidata card
and four crosswalk cards do not grant citation/proof credit or merge identities.

The saved `workflow_coverage.complete=true` describes returned graph inventory
and proof coverage only. It does **not** establish that the broader question
about Wikidata qualifications, identity and hierarchy was answered. That
question-wide adequacy remains unestablished, and there is no final narrative
whose limitations or source claims can be accepted. No current institutional
hierarchy, independent corroboration or institution-wide completeness follows
from these counters.

## Eight retrieved source records

Eight literal relationship fragments were compared with their exact JSON
pointers in five captured raw ROR files. Each provenance hash/size and projected
edge direction matches. The four NCI-side `child` records and the four
child-side `parent` records support the same four captured source-assertion
directions, NCI→child. They are not eight independent relationship observations.
The reciprocal records share the ROR upstream origin.

| Complete record | Raw JSON pointer | Indexed text SHA256 |
| --- | --- | --- |
| [NCI→DCEG](../../../datasets/public-research/imported-statements/evidence/relationship-ror-040gcmg81-d7313ad93a187159052d.json) | NCI `/relationships/3` | `436b9c200a76109af1f023f2db02ca65cec5c3493bd2e9a544f095a4b1c8eb55` |
| [NCI→Frederick](../../../datasets/public-research/imported-statements/evidence/relationship-ror-040gcmg81-1432a8d62794148e0f4c.json) | NCI `/relationships/1` | `eda92d0ea0c9b31d1518e5246f8a0c9755a785b4ece09afdcce11a7d7efe7763` |
| [NCI→CCR](../../../datasets/public-research/imported-statements/evidence/relationship-ror-040gcmg81-6f1ec97a766504fc55f2.json) | NCI `/relationships/0` | `8e0b2a5534e607106baae08e69c9d00fea427ec376d612aaee2753205ad66431` |
| [NCI→SWOG](../../../datasets/public-research/imported-statements/evidence/relationship-ror-040gcmg81-573adb44d1c211ec21bb.json) | NCI `/relationships/2` | `28e63f1cad07bc349aa7034d7cda53c79d81323a56977bb33098f7faa198f856` |
| [DCEG parent assertion](../../../datasets/public-research/imported-statements/evidence/relationship-ror-00vkwep27-faa3d6c20428c9c5200b.json) | DCEG `/relationships/0` | `2ae4ab3e4fa80a1ac0c2f3f6edbf71419306ff6bff666b3fba2ffa07d3780a83` |
| [Frederick parent assertion](../../../datasets/public-research/imported-statements/evidence/relationship-ror-03v6m3209-6ade712716c7a627e2ee.json) | Frederick `/relationships/0` | `eb767f4a1c654e46f7df0832ee26c7c1cbb1318c72879d54cd7b6ff8b9d4bef9` |
| [CCR parent assertion](../../../datasets/public-research/imported-statements/evidence/relationship-ror-05bjen692-dca7654da50b94c9e61c.json) | CCR `/relationships/0` | `dd76da25aa42779c24cb1df9c9c17a9d4c9ede2751312942b3293c419e0c5e47` |
| [SWOG parent assertion](../../../datasets/public-research/imported-statements/evidence/relationship-ror-05n6zrm60-02bb9bb1c26a8574e10d.json) | SWOG `/relationships/0` | `865468494ad1179060c2350b611b96b88d9ebbdb76415d6d83968216c429c086` |

These hashes cover indexed source text. Compact-synthesis lineage separately
hashes the complete returned record objects; the two hash scopes differ.
All indexed record dates are capture dates, `2026-10-07`, not relationship
validity dates. Captured ROR `record_modified` is `2024-12-11` for NCI, DCEG,
Frederick and SWOG; CCR is `2026-07-20`. No live update or current-truth check was
performed. Raw file hashes/revisions remain in each linked source's provenance.
This source inspection is review evidence, not a substitute model-authored answer.

## Exact request replay and admitted report timeout

The replay substituted the recorded short actions and original usage metadata
for generation, disabled every model HTTP request, and executed the twelve
recorded calls against the frozen MCP server. Finish intents at decisions 8
and 14 reconstructed the recorded guard feedback and report schema. All fifteen
canonical full-request SHA256 hashes, canonical byte counts and HTTP-body
serialization byte counts match the recorded admission entries exactly.

All admission arithmetic was checked. The fourteen completed decisions' recorded
preflight counts equal their actual reported prompt-token usage. The tokenizer
was not called again during review; these usage comparisons use original
metadata, not independently retokenized prompts. The final report has preflight
counts only, with no completed response usage to compare.

| Action | Phase | Prompt tokens | Output tokens returned | Canonical request bytes | Serialized body bytes |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | decision | 2,326 | 39 | 13,119 | 13,303 |
| 2 | decision | 2,509 | 36 | 13,825 | 14,024 |
| 3 | decision | 3,918 | 104 | 18,775 | 19,022 |
| 4 | decision | 12,227 | 50 | 36,820 | 37,113 |
| 5 | decision | 13,411 | 52 | 40,194 | 40,501 |
| 6 | decision | 14,609 | 50 | 43,573 | 43,894 |
| 7 | decision | 15,789 | 48 | 46,929 | 47,264 |
| 8 | rejected finish intent | 16,964 | 31 | 50,287 | 50,636 |
| 9 | decision | 17,201 | 92 | 51,074 | 51,431 |
| 10 | decision | 22,679 | 49 | 62,111 | 62,483 |
| 11 | decision | 23,847 | 50 | 65,488 | 65,874 |
| 12 | decision | 25,048 | 48 | 68,871 | 69,271 |
| 13 | decision | 26,210 | 50 | 72,231 | 72,645 |
| 14 | accepted finish intent | 27,393 | 31 | 75,593 | 76,021 |
| 15 | report attempt | 15,363 | unavailable | 44,787 | 44,963 |

For action 15: 15,363 prompt + 4,096 reserved output + 128 safety margin =
19,587 tokens, below the configured 49,152 limit by 29,565. Its 44,963-byte
serialized body is below 262,144. Canonical full-request SHA256:
`c1533f8def66e87eb947d9e23945de8eca46f8efb272f11e0c67cca171f2dad8`.
The recorded failure was the 1,200-second request deadline, not a token/byte
overflow. Admission does not guarantee generation latency, memory fit or output
quality. No completed report usage reveals how far generation progressed.

The compact report-message array reconstructs to 40,935 bytes, SHA256
`39525ed96968c9e4068c4c356c3836be5fb622d7da0b8dc69f61e2236e8b912c`.
Its scope is **canonical report messages only**: it excludes the separately
supplied response schema, model/settings and serialized HTTP envelope. The
packet retains all eight complete returned record variants, two identity/graph
results, actual coverage/current-run facts, and metadata-only catalog discovery.
There are no duplicate record variants, tool failures or omitted raw image
blocks. Exact record/result lineage and call numbers match the original metadata.

The optional host overview also reconstructs: 787 UTF-8 bytes, SHA256
`674b79cbd883a90873d33e832e018f42bf8e8c78497d4f163b309b03aa688b31`.
The attempted report schema constrains `summary` to that exact string. It counts
eight eligible records, zero comparable string-valued assertions, and eight
records without supplied assertion lists; it explicitly does not interpret all
source text or establish absence of real conflicts. All eight records are
scope-eligible and none excluded. This verifies host construction only; no model
returned a report adopting it. Source-JSON relationships remain complete evidence
even though this optional structured-assertion overview does not parse them.

## Resource and acceptance limits

The [finish resource sample](../resource-probe-nci02-finished.json), SHA256
`b32ab451384de59b3973b2bcbd81bb6d16a2df9a4a356dae000f84354ecba5e9`,
records process working set 3,546,710,016 bytes and startup-inclusive peak
4,383,703,040 bytes. The host had 1,121,204 KiB free physical memory out of
16,364,512 KiB visible at that sample. The peak includes startup, the neutral
probe, this run and concurrent development activity on a shared host; this is
not an isolated benchmark or minimum-RAM requirement. These observations do not
prove that memory pressure caused the timeout.

The run demonstrates exact recorded retrieval/provenance construction and a
visible bounded failure. It does not demonstrate a complete public analytic
workflow, cross-database reconciliation, verified current facts, a valid final
answer, human time savings or scalable performance. Media/pixel/audio coverage
is absent. A later attempt must preserve this failure and satisfy the unchanged
source and question-coverage criteria; an admitted request or complete structural
coverage counter cannot stand in for an accepted analytic product.
