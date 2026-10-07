# Live local model smoke test

One real local extraction completed the ingestion → extraction → publication → graph
retrieval workflow. This is a development smoke test on two simple fictional sentences;
it is not an extraction-accuracy, entity-resolution, or scaling evaluation.

Run started `2026-10-07T03:52:09Z`. Sanitized evidence is in
[`runs/local-model-smoke.json`](../runs/local-model-smoke.json); the local SQLite file
`runs/local-model-smoke.sqlite3` preserves ingestion, preparation, publication, and query
records. The ignored `runs/` directory is local execution output, not a committed fixture.

| Configuration | Value |
| --- | --- |
| Runtime | llama.cpp b11457; dedicated Project 5 loopback server |
| Model | Qwen3-VL-2B-Instruct Q4_K_M; alias `p5-qwen-local` |
| Declared model revision | `52d6c8ffea26cc873ac5ad116f8631268d7eb503` |
| Context / generation threads | 2,048 tokens / 1 |
| Sampling | Temperature 0; seed 0 |
| Request / pipeline deadline | 120 / 125 seconds |
| Maximum generated tokens / assertions | 600 / 4 |
| Source | 73 characters; authored fictional note; not pump-history gold |

Source text:

> Mira Labs operates Harbor Station. Mira Labs plans to lease Willow Annex.

`Engine.extract_job` made one real model request, with no cache hit. The client validated
two proposals, generated mention IDs and exact offsets, and staged them as
`local-model-v1`. The engine then published a graph-capable snapshot. The `Harbor Station`
query returned the first sentence as `reported`; a subsequent `Willow Annex` query
returned the second as `planned`. Both retained null dates and unknown temporal bounds.
Publication followed successful validation; fixture assertions were not substituted.

The extraction/publication/first-query sequence took **29.39 seconds**, excluding model
startup. The model HTTP call took 28.65 seconds. Server-reported usage: 257 input tokens,
184 output tokens, 441 total. These are one-run observations on the current device under
concurrent local workload, not isolated throughput or latency benchmarks.

Eight recorded checks passed: real model call, local preparation method, graph
publication, retrieval of a local assertion, exact cited span, unknown dates in the first
query, preservation of planned modality, and unknown dates across both queries. The
mention-scoped IDs intentionally do not merge the two occurrences of `Mira Labs`.

An additional embedding request on that same chat-configured server failed with
**HTTP 501** in 0.274 seconds. That failure is retained in the JSON attempt list;
no vector was fabricated and no cloud fallback was attempted.

After the owner restarted the isolated Project 5 runtime with `--embedding --pooling
last`, a second phase completed in **2.44 seconds**, excluding restart/loading. It used
the same decoder weights only to establish plumbing; this is not an optimized embedding
model or evidence of semantic retrieval quality. `Engine.build_vector_index` made one
real embedding request and published three vectors: one source chunk and two extracted
assertions. All three have 2,048 finite components and nonzero norms.

`Engine.search_local` then queried `Mira Labs` in hybrid and graph modes. Each request
made one real query embedding, returned eligible source evidence, and saved an evidence
bundle whose excerpts resolved to immutable source spans. Eight vector-phase checks
passed. Results and index fingerprints are in the same JSON report; bundles are
`runs/local-model-smoke-hybrid-export/` and `runs/local-model-smoke-graphrag-export/`.
The exact cosine index contains only three rows: no scale, ANN, or ranking-quality claim
follows from this run. Server pooling/context are recorded separately from the client
request profile.

The profile includes a declared weight digest from the existing pinned runtime manifest;
the server alias itself does not attest to loaded bytes. Saved metadata contains hashes,
counts, validated excerpts, and safe errors, excluding raw prompts, raw responses, local
installation paths, and server logs. No other project's process or inference endpoint
was used for this test.
