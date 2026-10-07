# GraphRAG methods and design implications

Research checked 2026-10-06. Design research only; no package selected or benchmark run.
Dataset selection, implementation, and model setup remain later work.

## What this project means by GraphRAG

The brief proposes evidence-linked relationship descriptions, embeddings, query-selected edges, and temporal comparison.
That is a project design requirement; the GraphRAG name alone does not establish those capabilities.
Free-text relations reduce dependence on a closed predicate vocabulary. They still need stable entity identity,
provenance, time semantics, and rules for contradictions, duplication, and extraction uncertainty.

Microsoft's original GraphRAG instead emphasizes extracted entities, relationships, graph communities, and precomputed
community summaries for global questions. Its paper reports improved answer comprehensiveness/diversity on corpora
around one million tokens; this is evidence for that task and scale, not proof of million-document temporal discovery.
[Original GraphRAG paper, v2](https://arxiv.org/abs/2404.16130v2).

## Primary method comparison

| Method | Verified mechanism | Project role / limitation |
|---|---|---|
| Microsoft standard indexing | LLM entity/relation extraction; merged descriptions; community reports | Rich comparison index; ingestion and summary refresh require accounting. |
| Microsoft Local Search | Embed query against entity descriptions; collect related graph data and source chunks; fit context budget | Entity-centered baseline; not a documented edge-description nearest-neighbor temporal engine. |
| Microsoft Global Search | Map/reduce across reports from a community hierarchy level | Whole-corpus theme baseline; cost depends on report count/level. |
| Microsoft DRIFT | Relevant community reports generate primer and follow-up questions; local search refines answers | Exploratory baseline; branching and LLM use need explicit budgets. |
| Microsoft FastGraphRAG | NLP noun phrases and chunk co-occurrence; LLM community reports | Cheaper indexing comparator; co-occurrence is not an asserted semantic relationship. |
| LazyGraphRAG | Concept/co-occurrence index; defer LLM analysis to query time; relevance-test budget | Design inspiration for bounded lazy work; implementation availability must be qualified. |
| LightRAG | Vector matching of entity/relationship keys; neighborhood retrieval; incremental graph integration | Closest named comparator to query-selected entity/relation retrieval; temporal semantics require separate design. |
| HippoRAG 2 | Open triples and passage nodes; query-to-triple/passage matching; LLM triple filter; Personalized PageRank | Multi-hop evidence retrieval comparator; graph ranking adds its own compute and tuning. |

The standard/Fast descriptions follow current [Microsoft indexing methods](https://microsoft.github.io/graphrag/index/methods/).
Microsoft estimates extraction at roughly 75% of standard indexing cost and warns FastGraphRAG produces noisier graphs.
FastGraphRAG still precomputes reports; it is not LazyGraphRAG.

[Local Search documentation](https://microsoft.github.io/graphrag/query/local_search/) grounds the entity-embedding distinction.
Its context can include relationships, covariates, reports, and original chunks; relationship inclusion is not proof
that relationship embeddings drive candidate retrieval.

[Global Search documentation](https://microsoft.github.io/graphrag/query/global_search/) describes report map/reduce.
Deeper, more detailed hierarchy levels can increase time and LLM resource use.
Global report coverage and exact enumeration/counting are different operations; use structured queries for counts.

[DRIFT documentation](https://microsoft.github.io/graphrag/query/drift_search/) describes a community primer and local follow-ups.
Its exploration mechanism motivates an optional later discovery mode, after bounded single-query retrieval works.

## Claims worth testing, not importing as guarantees

**LazyGraphRAG:** Microsoft reports indexing at 0.1% of full GraphRAG cost, comparable global answer quality at
over 700-fold lower query cost in one configuration, and stronger results at 4% of global-search cost in another.
Evidence: 5,590 licensed AP articles, 100 synthetic questions, and LLM pairwise judgments of comprehensiveness,
diversity, and empowerment. These are vendor-reported results, not project latency, truthfulness, or scale guarantees.
The June 2025 note names Microsoft Discovery/Azure Local integrations; it does not establish a supported standalone
open-source LazyGraphRAG API. Its deferred summarization and relevance-test budget are useful design ideas regardless.
[Microsoft LazyGraphRAG report](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/).

**LightRAG:** its paper describes entity/relationship vector retrieval and one-hop expansion; graph union handles additions.
Evaluation corpora span about 0.62–5.08 million tokens but only 10–94 documents each.
The often-cited comparison of under 100 tokens versus 610,000 concerns retrieval-stage keyword generation versus
community processing on the legal corpus; it is not a complete answer-generation bill or a universal speedup.
Reported answer preference and synthetic queries do not establish temporal correctness or analyst discovery value.
[LightRAG paper, v3](https://arxiv.org/html/2410.05779v3).

Current LightRAG documentation also describes selective document deletion with affected graph regeneration from
cached extraction, citations, and several storage backends. Defaults use in-memory stores with file persistence,
documented for small testing, not production scale. Package behavior must be pinned separately from the paper.
[Maintainer repository](https://github.com/HKUDS/LightRAG).

**HippoRAG 2:** the authors report an average seven-point gain on associative tasks versus standard RAG, with
factual/discourse evaluations also included. Their experiment with progressively added knowledge still shows
multi-hop performance degradation as the corpus grows. Static QA gains and incremental additions do not establish
historical validity, correction handling, or change detection. Retain passage grounding even when triples guide retrieval.
[HippoRAG 2 paper, v2](https://arxiv.org/html/2502.14802v2).

## Temporal gap and evidence model

Microsoft outputs include document creation time, ingest periods for community updates, and optional claim start/end dates.
The documented relationship table has description, endpoints, weight, and source chunks, but no validity interval.
Those fields do not by themselves implement an as-of snapshot or baseline comparison.
[Documented GraphRAG output schema](https://microsoft.github.io/graphrag/index/outputs/).

**Proposed:** preserve individual evidence-backed assertions beneath any merged relationship description.
Keep valid/event time separate from publication time and system observation time; allow unknown/approximate dates.
Store corrections and retractions as versioned evidence, not silent replacement of history.
Record extraction/model version, source span, endpoint resolution, and modality: asserted, negated, uncertain, or inferred.
Embedding similarity ranks candidates; it cannot establish truth, temporal validity, or logical contradiction.

**Proposed:** an as-of query filters every retrieval route, neighborhood expansion, and summary dependency.
A historical answer must not inherit a current entity summary containing later facts.
Baseline comparisons must separate newly observed evidence from newly occurring events and changes in extraction.
Show supporting and opposing evidence; absence from top-k retrieval is not proof that a relation disappeared.

## Proposed implementation direction

1. Build the evidence/version contract first; keep relation text flexible and temporal fields explicit.
2. Start with PostgreSQL and pgvector as the proposed single backend; benchmark exact filtered search on the pilot.
3. Add approximate search only against exact filtered recall measurements; narrow time filters can change behavior.
4. Retrieve lexical/vector candidates from passages and assertions; fuse and deduplicate before graph expansion.
5. Expand only a bounded neighborhood; cap hubs, hops, visited assertions, rerank calls, context tokens, and elapsed time.
6. Preserve the source passages selected by graph reasoning; return citations and visible truncation/coverage limits.
7. Add cached community summaries only if global-question experiments justify their build and refresh costs.
8. Defer specialized stores and unrestricted agent exploration until measured bottlenecks justify them.

These are project proposals, not capabilities verified in a selected package. Dataset choice remains open.
Never equate a bounded answer context with bounded retrieval work: candidate generation, joins, PageRank, and
relevance testing must each have measured limits. Cold-start indexing cost remains part of total cost.

## Comparison and measurement plan

Use identical corpus snapshots, evidence permissions, embedding/generator versions, and answer budgets where feasible.
First compare lexical retrieval, vector retrieval, lexical/vector fusion, and fusion plus bounded assertion expansion.
Then compare LightRAG-style retrieval; add Microsoft local/global/DRIFT and HippoRAG 2 only for matching question classes.
Do not silently replace a vendor method with a custom approximation; label adaptations and unavailable comparisons.

Measure evidence recall/precision, citation support, contradiction handling, temporal leakage, change precision/recall,
and analyst-rated novelty/usefulness separately from fluent answer preference.
Report p50/p95 latency, extraction/embedding/query tokens, calls, memory/storage, refresh time, and concurrency.
Use corpus-size and update-rate sweeps; include high-degree entities, duplicate sources, late corrections, and narrow windows.
Report cost-quality curves plus failure cases. No large-scale success claim until measured on the declared workload.
