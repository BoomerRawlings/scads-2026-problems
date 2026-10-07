# Public NCI 01: bounded execution failure review

Verdict: **no public analytic acceptance**. The run failed during decision step 10
with `context_token_limit` after 2,049.031 seconds. No finish intent, final report,
evidence ledger, media observation, compact synthesis, or host overview was
produced. This is a preserved runtime failure, not a rejected semantic report.
The failure is not evidence that the source claims were disproved.

Separate AI review, completed 2026-10-07 under the unchanged
[public protocol](../PROTOCOL.md). This remains a known, source-inspected
development case, not a held-out test, human-gold label or general accuracy
benchmark. No model was called during this review. Original artifacts are
unchanged; reconstructed tool results and request bodies were used in memory,
not added as purported original logs. Private reasoning was not saved.

## Originals and final state

The original directory contained exactly the three files below. Before copying,
`run-metadata.json` was rechecked: `status=failed`, `phase=decision`, `steps=10`.
The failure path deliberately retains its last phase; there is no successful
`phase=finished` report to await. Every copied byte and hash was compared with
the source directory after copying.

| Original artifact | Bytes | SHA256 |
| --- | ---: | --- |
| [failure.json](failure.json) | 127 | `50bbbe48513efd567baf74f617306f32bb17da44b692f9bee54c1b5d0bb9d76b` |
| [run-metadata.json](run-metadata.json) | 43,635 | `875711afe2aa5342f04435818742fbcc5149d38d49c3a0c20d48faf94b0cba6a` |
| [tool-trace.json](tool-trace.json) | 1,608 | `ce18943cccecd23bdf8d06570147a24834d82132aac2b926b460a33f66b463c6` |

Start: `2026-10-07T12:39:33.601944+00:00`. Recorded duration: 2,049.031 seconds.
There are nine completed decision generations, nine attempted MCP calls
(eight successful, one failed), and five successful complete source reads.
No finish/report rejection or pre-MCP action rejection is recorded. Runtime
status never reached `complete` or `insufficient_evidence`; no abstention report
was synthesized.

## Reproduction and provenance bindings

The [v13 snapshot](../implementation-v13/snapshot.json) has SHA256
`0025c6760daa2b30b500a10688b71874cc591fe7c15e91f46f434e675d3f13ba`.
All 13 frozen source/origin byte pairs and hashes were checked against the live
files during review. All eight implementation hashes recorded by the run match
that snapshot. The [snapshot reproduction instructions](../implementation-v13/README.md)
remain the invocation reference. Later implementation changes do not alter this
frozen binding.

The exact target is `ror:040gcmg81`. The metadata question matches the snapshot
and only the first protocol blockquote verbatim, including line breaks; the
reviewer's source map was not appended to the question. The original system
prompt hash, reconstructed with the actual tool schemas, is
`5f0fffeac5633dbf0310fa32cc39e009655aef29bfcd62c1a346909aaa635c59`.

The statement dataset fingerprint is
`6f73d422781738700473016818d3e3de011f1082b5ba4b4df1b54481e4f72aa5`.
The complete run-recorded dataset metadata/file map matches a fresh fingerprint.
All 172 files listed by its [import manifest](../../../datasets/public-research/imported-statements/import-manifest.json)
match sizes/hashes. Import-manifest SHA256:
`bf051f384b4fba6d944f470464995a437f6c953067fc577529f3f7ec1944a580`.
The frozen protocol SHA256 remains
`cc7bc6723ed026ad88cb667b07392988d801fab1840a68a252dc6bf14a0f4837`.
No live public-source refresh was used.

The run used the [9B text profile](../runtime-profile-qwen35-9b-text-01.json),
SHA256 `dc25a6cb0b97449b5623124b89adf738d270ce3bd8ade8b357d311b17f641558`,
and [pinned runtime manifest](../../../docs/runtime-candidate-qwen35-9b.json),
SHA256 `b355b525da2840eb5c2b72a3ee612277f5554657db34b243fcd506fabdfdc43f`.
Model alias `Qwen3.5-9B-Q3_K_M`; Unsloth revision
`3885219b6810b007914f3a7950a8d1b469d598a5`; language-weight SHA256
`8fed90306e4f019e2bf35f3766470b7bc59ea1a9dae00f5ceb20b43cb5514393`.
Runtime llama.cpp b11457, Windows ARM64 CPU; runtime archive SHA256
`fab992671bd26ba4117da4f70f330fe1b9fe69eb8ce952281cabf4c5c5f2a17e`.
The projector was disabled. This review verifies manifest/profile bindings, not a
fresh multi-gigabyte installed-weight hash or independent server attestation.
The operator's profile records one 16,384-token slot, eight threads, batch 128 /
microbatch 32, Q8 KV caches, mmap, no repacking, no context shift, and disabled
optional saved-prompt caches. These settings differ from earlier media runs;
this is not a controlled resource or model comparison.

Invocation bounds: 40 actions, 3,600 seconds total, 1,200 seconds/request,
131,072 serialized request bytes, 16,384 tokens. Opt-ins: catalog retrieval,
grounded media, compact synthesis and evidence summary. Grounded-media enabled
does not mean pixels were supplied: local catalog mode is explicitly text-only.
Planning: temperature 0, seed 0, disabled thinking, 512-token generation allowance.
The configured 4,096-token report allowance/1,024 thinking budget was never used.

## Actual tool sequence and incomplete coverage

1. Exact-ID entity search resolved the ROR NCI node.
2. Directed traversal, max_hops 3, returned NCI plus four captured ROR children:
   `ror:00vkwep27`, `ror:03v6m3209`, `ror:05bjen692`, `ror:05n6zrm60`.
   Four outgoing `contains` edges declared eight source proof IDs.
3. The unfiltered catalog request used these five IDs, `max_items=100`, and the
   default `max_bytes=8192`. Its first page returned 21 metadata cards out of 39
   matching items, with a non-null continuation cursor. Page byte bounds, not
   the requested item ceiling, limited this page.
4. The next catalog call supplied only that cursor. Omitting the original scope
   changed `entity_ids` to null; omitting `max_items` changed 100 to 20. The tool
   correctly rejected it: `Cursor does not match dataset, query, scope and options`.
   This failed call neither returned evidence nor completed the original chain.
5. Calls 5–9 read the five complete records listed below. There was no retry of
   the catalog continuation, further traversal, or tenth tool call.

Reconstruction through the frozen coverage logic yields zero complete catalog
receipts and one incomplete chain containing call 3 only. All five graph-scope
entities lack completed inventory. Three of the eight declared proof records
were actually read; five remain missing:

- `relationship-ror-040gcmg81-1432a8d62794148e0f4c`
- `relationship-ror-040gcmg81-573adb44d1c211ec21bb`
- `relationship-ror-040gcmg81-d7313ad93a187159052d`
- `relationship-ror-05bjen692-dca7654da50b94c9e61c`
- `relationship-ror-05n6zrm60-02bb9bb1c26a8574e10d`

The reconstructed `complete` coverage flag is false. This calculation is a
review reconstruction; the run did not reach finish preflight and therefore
has no saved `workflow_coverage` object. There are 29 observed eligible source
IDs: 21 metadata-card IDs plus 8 graph-proof IDs. Observed IDs are not full reads
or citation credit. Only five complete source records receive retrieval credit.
The retrieved crosswalk associates `wikidata:q664846` with the connected source
scope; that is relevance, not an identity merge, traversal or completed inventory
of that Wikidata node. Nested referenced IDs gain no standalone read/citation
credit from appearing in a record.

## Five retrieved sources

The following hashes are indexed source-text/file hashes, not independent truth
certificates or counts of independent origins. Four underlying raw source files
were verified: ROR NCI, DCEG, Frederick and Wikidata Q664846. Six literal fragments
were compared with their raw JSON pointers; three crosswalk decision references
were checked against existing source units/raw pointers and source hashes.
Dates on these indexed units are capture dates, not relationship validity dates.

| Complete retrieved record | Indexed text SHA256 |
| --- | --- |
| [crosswalk-0ae56f2abe9915b040ed](../../../datasets/public-research/imported-statements/evidence/crosswalk-0ae56f2abe9915b040ed.json) | `e21b5b3d5f8fb19e8085b84f3a6e475d75981c34e75ec14bacb5cc871c70e304` |
| [external-id-ror-040gcmg81-fa16bede6b326acd5c3e](../../../datasets/public-research/imported-statements/evidence/external-id-ror-040gcmg81-fa16bede6b326acd5c3e.json) | `fc3927d9e46bc701106a1332b033f8681bb350e16f2cc094244f733d4fb30746` |
| [relationship-ror-00vkwep27-faa3d6c20428c9c5200b](../../../datasets/public-research/imported-statements/evidence/relationship-ror-00vkwep27-faa3d6c20428c9c5200b.json) | `2ae4ab3e4fa80a1ac0c2f3f6edbf71419306ff6bff666b3fba2ffa07d3780a83` |
| [relationship-ror-03v6m3209-6ade712716c7a627e2ee](../../../datasets/public-research/imported-statements/evidence/relationship-ror-03v6m3209-6ade712716c7a627e2ee.json) | `eb767f4a1c654e46f7df0832ee26c7c1cbb1318c72879d54cd7b6ff8b9d4bef9` |
| [relationship-ror-040gcmg81-6f1ec97a766504fc55f2](../../../datasets/public-research/imported-statements/evidence/relationship-ror-040gcmg81-6f1ec97a766504fc55f2.json) | `8e0b2a5534e607106baae08e69c9d00fea427ec376d612aaee2753205ad66431` |

- `crosswalk-0ae56f2abe9915b040ed`: reciprocal NCI ROR/Wikidata identifier
  assertions, `merged=false`, status `reciprocal_candidate_requires_identity_review`.
  Preserves the full embedded ROR identifier group and Wikidata P6782 statement,
  plus endpoint/P31 decision references. Those referenced standalone units were
  not themselves read. Reciprocity does not establish independent corroboration.
- `external-id-ror-040gcmg81-fa16bede6b326acd5c3e`: the captured NCI ROR
  `/external_ids/3` group points to Q664846 with `preferred=null`.
- `relationship-ror-00vkwep27-faa3d6c20428c9c5200b`: DCEG's captured ROR
  `/relationships/0` asserts NCI as parent; the projected direction is NCI→DCEG.
- `relationship-ror-03v6m3209-6ade712716c7a627e2ee`: Frederick's captured ROR
  `/relationships/0` asserts NCI as parent; projected direction NCI→Frederick.
- `relationship-ror-040gcmg81-6f1ec97a766504fc55f2`: NCI's captured ROR
  `/relationships/0` asserts Center for Cancer Research as child.

These are a review of retrieved content, not an analytic report authored by the
model. The run did not retrieve the standalone qualified Wikidata P749 hierarchy
statements, a complete child-proof set, or full inventory. No claims about their
absence in the corpus, present-day hierarchy, institution-wide completeness or
successful reconciliation follow from this failure. No raw media was read;
there is no multimodal acceptance or pixel observation to review.

## Context admission and exact request reconstruction

All nine completed generations have identical saved preflight and reported
actual prompt-token counts. Recorded completion/total counts are arithmetically
consistent. There is no tenth generation response: the preflight rejected it
before `/chat/completions` could be invoked. The tenth prompt alone had 16,823
tokens; reserving 512 output plus 128 safety tokens required 17,463, exceeding the
16,384 limit by 1,079. Request bytes 53,061 remained below 131,072; the failure was
the explicit token guard, not an observed HTTP timeout, byte limit or model OOM.

| Step | Preflight prompt tokens | Reported actual prompt tokens | Output tokens | Reserved total | Admission |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 2,326 | 2326 | 26 | 2,966 | admitted |
| 2 | 2,509 | 2509 | 36 | 3,149 | admitted |
| 3 | 3,918 | 3918 | 84 | 4,558 | admitted |
| 4 | 8,693 | 8693 | 143 | 9,333 | admitted |
| 5 | 8,897 | 8897 | 38 | 9,537 | admitted |
| 6 | 12,216 | 12216 | 48 | 12,856 | admitted |
| 7 | 13,275 | 13275 | 49 | 13,915 | admitted |
| 8 | 14,443 | 14443 | 50 | 15,083 | admitted |
| 9 | 15,643 | 15643 | 50 | 16,283 | admitted |
| 10 | 16,823 | No generation | None | 17,463 | blocked |

For independent reconstruction, saved actions were replayed through actual local
stdio MCP against the bound dataset. Model transport was replaced with a
non-network replay object that returned only the recorded action sequence; its
`request` method rejected any model call. The frozen local runner rebuilt its
normal tool schemas, complete results, error feedback, progress and planner
messages. All ten canonical full-generation-request SHA256 values, canonical
byte counts and serialized-wire byte counts exactly match the original saved
admissions, including blocked step 10. The original trace, observed/retrieved IDs,
source progress and initial prompt hash also match. Temporary replay checkpoints
were discarded; originals were never overwritten.

| Step | Canonical request bytes | Serialized request bytes | Canonical full-request SHA256 |
| --- | ---: | ---: | --- |
| 1 | 13,119 | 13,303 | `1d5891a7f2904e760223452d0643f7e2c0874451d38a4821bf547a2897ee35d5` |
| 2 | 13,825 | 14,024 | `23c27f128ba8622f0fbf209d4a00b58317a196b0169f790185a319e2f1e95085` |
| 3 | 18,775 | 19,022 | `4b8c3bc90b1bc6eee6baf0573fcd0cfdae53bfe60e74266da0a3313687f4339c` |
| 4 | 29,241 | 29,524 | `a778c93c4d8dc4bc7af55cfe1842a323006f910671f194cf286c2a72a958cf7d` |
| 5 | 29,789 | 30,087 | `9af8b526608f2d8ad375cc1076a13a564bc10d022981d6b56133b5522edf0205` |
| 6 | 39,530 | 39,842 | `df99a733fb02ad68045dadb71afafdc7c5e8634a8bfa6ea7bb702a080120c865` |
| 7 | 42,578 | 42,904 | `063e4e49885ae09316c23a43892846c6bbaf2ff5e1ebdb96fdd4c0488799b7ce` |
| 8 | 45,955 | 46,295 | `16ccde445b2b55529488691eab0deacca00544a269ba2dc50cedd30e6b42a91e` |
| 9 | 49,337 | 49,691 | `9332d8f7a1b075c40d7d1941aeca35d296cef2d531796521bb4a2a169756744e` |
| 10 | 52,693 | 53,061 | `3e9ba04635a8bfc00e2bedd83a2f3b767b9adf3b5583d9a319ea709bf3dd9a8e` |

These fingerprints cover the canonical generation request including messages,
response schema, model and settings. They differ from the earlier compact-report
messages-only fingerprint policy; compact report construction did not run here.
The rendered-prompt hashes and token counts remain the original runtime's
records. No independent tokenizer/server call was made in review, and no raw
HTTP capture or hidden reasoning is claimed. Exact reconstruction establishes
input/result consistency, not analytic correctness.

The [resource point](../resource-probe-nci01-finished.json) records 5,026,734,080B
working set and 5,087,371,264B startup-inclusive peak, including the neutral probe
and this run on a shared host. It is not a per-run isolated benchmark, minimum
RAM requirement or proof that memory pressure caused the context rejection.
The [neutral probe](../context-probe-9b-01.json) previously matched 35 tokens;
that narrow compatibility result did not establish capacity for this workload.

## Acceptance boundary

The guards visibly rejected an invalid cursor and an oversized context without
silently dropping source content. This is useful execution evidence. The actual
question remains unanswered by this run. Public analytic acceptance, complete
inventory/proof coverage, claim reconciliation, repeatability, broader scale,
human time savings and general model accuracy remain unestablished. Future
trials require their own unchanged-protocol review; a different model/context
profile is not an isolated causal comparison.
