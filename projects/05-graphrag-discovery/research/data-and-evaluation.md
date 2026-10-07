# Data interface and evaluation plan

Status: real-data evaluation design, 2026-10-06. No real dataset selected, downloaded, indexed, or evaluated. The authored pump fixture now validates a subset of software behavior; see [implementation status](../docs/implementation-status.md). Fixture results do not establish discovery quality or scale.
Purpose: define what a later dataset must supply and how to test the system without making its architecture corpus-specific.

## Dataset adapter requirements

Start with a local JSONL document-version adapter. Source-specific acquisition belongs behind that interface.
The following are conceptual fields; the project integration contract controls their final names.

| Record | Required information |
| --- | --- |
| Corpus manifest | Corpus ID; source URLs; acquisition/version identifiers; rights and attribution notes; language; checksum; inclusion/exclusion rules |
| Document version | Stable document ID; immutable revision ID; predecessor when known; original text or retained source reference; content hash; source URL |
| Time metadata | Source availability timestamp when known; first local ingestion timestamp; source precision/time zone; explicit unknown values |
| Optional validity | Event/valid-from/valid-to dates only when supported; evidence spans; uncertainty; no timestamp substitution |
| Lifecycle event | Stable event ID; document/revision ID; append, supersede, correction, or source withdrawal; event and observation times |
| Chunk | Version ID; chunk ID; normalized text; offsets into retained normalized source; tokenizer/chunker versions; original-source locator |
| Derived assertion | Endpoint mentions; free-text relationship; supporting chunk/spans; extractor version; extraction time; optional validity; resolution provenance |

Keep raw-source hashes separate from normalized-text hashes. A parser change must not silently change citations.
Repeated imports are idempotent. New revisions preserve prior versions; source withdrawal invalidates affected current retrieval entries and caches.
Retraction preserves historical evidence when permitted; it does not silently erase what an earlier snapshot contained.
Initial scope is public-only. Access revocation/mandatory erasure and their cache/history tests belong to a separately specified future extension; source withdrawal is not access deletion.
Dataset adapters provide documents and lifecycle events, never the supposedly correct graph used as evaluation truth.
An optional entity dictionary can assist extraction; disclose its source and restrict it to the applicable time cutoff.
Declare coverage: complete version history, sampled snapshots, append-only records, or current-only records.
Current-only sources cannot establish reliable historical text; disable unsupported temporal claims instead of fabricating history.
Reject/quarantine malformed records with reasons. Report missing text, unknown dates, duplicate ratios, and parser loss.
Persist a manifest and stable partition assignment so every retrieval system receives identical eligible evidence.

## Time semantics and baseline comparisons

Three clocks have distinct meanings: when a document became available, when this system received it, and when its claims apply.
Query visibility adds a processing/publication boundary: strict system-history evidence must also have an eligible source/processing activation; derived assertions need their own activated interpretation. Durable receipt alone does not make an unpublished record searchable.
For example, a report published in June describing a January event was not available to a February analyst.
An as-of query must state its clock: source-published-by or known-to-this-system-by.
Historical replay may simulate ingestion from source availability; tag that as a simulation, never recovered observation history.
Unknown source availability excludes a record from strict published-by evaluation unless an independently supported upper bound qualifies it.
Use UTC internally, preserve source precision, and define interval boundaries once; date-only records remain date-only uncertainty.
Define a saved baseline by corpus snapshot, document versions, query/scope, time filter, and retrieval/extraction configuration.
Compare baseline and follow-up under one fixed extraction/resolution configuration; otherwise separate source changes from model changes.
Knowledge comparisons preserve both snapshot boundaries. World-state comparisons evaluate V0/V1 in one analysis snapshot at fixed K, using baseline scope but keeping the original saved belief separate from retrospective reconstruction.
Change labels distinguish new evidence, corrected/retracted evidence, explicitly changed relationships, and unresolved contradiction.
Deletion of a sentence establishes a document edit; it alone does not prove the real-world relationship ended.
Entity alias merges can change the displayed graph without new source evidence; report that as a resolution change.
Report both incremental findings and what remains supported from the saved baseline, with citations on both sides.

## Proposed scales and workload

Scales are configurable targets, not completed results or promises that a single machine can support them.
Count unique active chunks at the snapshot separately from all retained version chunks, assertions, entities, and embeddings.

| Stage | Active chunk target | Purpose | Proposed update probes |
| --- | ---: | --- | --- |
| Contract fixtures | Dozens to hundreds | Replay, offsets, validity, rollback, malformed input | Explicit small event sequences |
| Pilot | 10,000 | Human label feasibility; retrieval and extraction diagnosis | 0.1%, 1%, 10% of active chunks affected |
| Medium | 100,000 | Degree skew, distractors, update locality, concurrent queries | Same fractions plus skewed entity updates |
| Scale experiment | 1,000,000 | Resource limits and quality/cost frontier | Same fractions; burst and steady arrival |

Use nested subsets from a declared sampling frame, retaining complete selected document histories where feasible.
Report actual document, token, byte, language, topic, revision, entity-degree, and duplicate distributions at every stage.
Sample whole document families; avoid filling larger stages with copies of existing chunks.
Maintain a fixed query panel to isolate distractor/scale effects, plus a separately reported scale-representative panel.
Synthetic fixtures establish software behavior. Synthetic expansion/load establishes resource behavior only.
Real discovery claims require independently labeled natural-language sources and genuine revisions or append events.
Progress only after estimating storage, embedding/extraction budget, and wall time from the prior stage.

## Retrieval comparisons

Include lexical, dense, and hybrid baselines: dense retrieval need not win across domains, as [BEIR's original study](https://arxiv.org/abs/2104.08663) demonstrates.
All arms share source versions, chunker, time eligibility, generator, answer prompt, and maximum evidence-token budget.

| Arm | Retrieval behavior | Main question |
| --- | --- | --- |
| Lexical | PostgreSQL full-text ranking over source chunks; optional separately labeled BM25 comparator | Does ordinary lexical matching suffice? |
| Dense | Embedding retrieval over the same chunks | Does semantic matching help? |
| Hybrid | Lexical+dense fusion; optional shared reranker | Strongest conventional retrieval baseline |
| Edge-text only | Retrieval over extracted relationship text; resolve to supporting chunks | Does extraction help without traversal? |
| Hybrid plus edge text | Same hybrid candidates plus assertion retrieval; no graph traversal | Does extracted text add value to the strongest conventional baseline? |
| Bounded GraphRAG | Same hybrid/edge candidates plus budgeted expansion and evidence ranking | Does topology add value beyond extracted text? |

Tune on development queries only. Predeclare fusion, reranking, ANN search, node/edge caps, hop count, and model versions.
Use equal-evidence-budget comparisons and separate equal-query-cost/latency comparisons; expose the resulting quality/cost curves.
Keep retrieval-only and full answering measurements separate so generator latency does not hide retrieval overhead.
Ablate entity resolution, graph expansion, temporal filtering, and high-degree pruning one at a time.
An ablation with temporal filtering removed is diagnostic and must never serve the strict as-of user path.
If global summaries are later added, version them by snapshot and include their build/update costs as a separate arm.

## Query labels and splits

Proposed initial real-data target: 240 reviewed queries, 40 per family; revise after a 30-query annotation pilot.
Families: local lookup, multi-document relationship, cross-topic discovery, historical as-of, baseline-to-current change, and unanswerable/conflicting evidence.
Discovery queries need an explicitly scoped source subset and a rubric for supported novel findings; no claim of exhaustive global recall.
Store query text, family, entities, time cutoff(s), baseline ID, answerability, required facts, acceptable evidence sets, and relevance grades.
Keep plausible distractors and alias/homonym cases. Include no-change, late-arrival, retraction, and corrected-date cases.
Label source passages and minimal sufficient evidence sets; a generated graph edge is not its own ground truth.
For extraction, annotate an independent stratified source sample exhaustively; judge free-text assertions by supported meaning, not exact wording.
Use two reviewers on the locked test set and disagreement cases; record adjudication and agreement before adjudication.
LLM suggestions may draft questions or grades; human review establishes final labels and confirms source support.
Proposed split: 60% development, 20% validation, 20% locked test, grouped by document/entity-topic family and paraphrase cluster.
Within evaluation groups, retain earlier baseline evidence and later update evidence; train/tune only on separate groups and earlier allowed periods.
Distinguish this from holding out documents from retrieval: test evidence belongs in the eligible search index when published by the query cutoff.
Keep near-duplicate passages and revision lineages in one partition; report unavoidable cross-group entity overlap.
Any trained component uses only the development partition; validation sets operating points once; test labels remain sealed.
Pool candidate evidence from every arm plus independent manual search; unjudged evidence remains unjudged, not automatically irrelevant.
Report labeling coverage and uncertainty; a small test set is a pilot, not a general performance claim.

## Measurements and gates

| Layer | Required measures |
| --- | --- |
| Extraction | Mention precision/recall; entity-resolution pair precision/recall; supported assertion precision/recall; time-field accuracy/abstention; citation-span correctness |
| Retrieval | Graded nDCG@k; evidence recall@k; complete evidence-set coverage; future-evidence rate; results by query family |
| Answers | Required-fact coverage; claim support; citation correctness/completeness; temporal correctness; calibrated abstention; contradiction handling |
| Change detection | Precision/recall by change type; false alerts on no-change cases; baseline support preserved; detection lag |
| Analyst use | Time to a supported finding; finding correctness; navigation actions; abandoned tasks; small blinded/counterbalanced comparison |
| Runtime | Retrieval and answer p50/p95; throughput; timeout/error rate; peak RAM/VRAM; disk/index bytes; candidates visited; truncation rate |
| Build/update | Parsing/extraction/embedding/index time and cost; tokens; affected chunks/edges; write amplification; update lag; recovery time |

Use the same hardware, concurrency, query order randomization, warm/cold conditions, timeout, and cache policy across arms.
Proposed load sweep: concurrency 1, 4, 16 where feasible; repeat at least three runs and report query counts plus confidence intervals.
Count failures and timeouts in service outcomes; show censored latency separately, not only successful-query percentiles.
Report per-query paired quality differences with intervals clustered by query family/document group, plus raw family scores.
Dollar estimates record pricing date; report token counts and compute/storage hours so estimates remain interpretable later.
Total scenario cost = initial ingestion + extraction + embeddings + indexes + retained storage + updates + Q queries; vary Q.
Measure append, correction, supersession, retraction/source withdrawal, late arrival, duplicates, and out-of-order delivery independently and in mixed traces.
Observe query quality during updates; record snapshot consistency, stale-cache exposure, and time until updates become searchable.
Invariant gate: all citations resolve; no future evidence in strict-cutoff fixtures; idempotent replay; bounded expansion/comparison; withdrawal invalidates affected current caches.
Quality gate: predeclare a minimally useful gain or justified new capability over hybrid before opening test labels.
Budget gate: declare target hardware, p95 latency, update delay, and maximum cost before the first large run; currently unresolved.
A useful negative result identifies the limiting stage, measured cost/quality tradeoff, and the largest verified scale.

## Time leakage tests

Insert later text containing a uniquely identifiable answer; earlier queries must not retrieve it or answer with its citation.
Apply cutoff eligibility before traversal, reranking, summarization, and answer context; generated descriptions may also leak later revisions.
Snapshot/version entity aliases, cached results, edge descriptions, embeddings, and summaries, not just raw document rows.
Test late-arriving old-event evidence: excluded from earlier knowledge snapshots, eligible later despite old event validity.
Test a later correction of an earlier claim; reproduce each historical answer without silently replacing its evidence.
Test duplicate revisions and rollback around an update batch; a query sees one committed snapshot.
Test source-only publication lag without graph extraction and relative-date extraction caches with identical text in different source contexts. Test run execution allowances separately from analyst idle time and cursor expiry.
Pretrained models may already know public answers; require eligible citations, use no-context controls, and report residual contamination risk.
Synthetic canaries reveal pipeline leakage; they do not establish absence of model memorization on real public data.

## Later corpus qualification: short candidate list

No selection now. After interface design, score candidates for usable text, history completeness, changes, rights, parsing effort, and annotation cost.

| Candidate | Relevant source capability | Qualification concern |
| --- | --- | --- |
| Wikipedia revision subset | XML content dumps contain text and revision metadata. [Wikimedia format](https://meta.wikimedia.org/wiki/Data_dumps/Dump_format) | Revisions support document history, not automatic event truth; full history is large; preserve [attribution/licensing](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content). |
| Public software issues/comments + versioned release notes | [Issue timelines](https://docs.github.com/en/rest/issues/timeline) supply events; [comments API](https://docs.github.com/en/rest/issues/comments) supplies bodies and timestamps. | Do not infer complete old text from current bodies; verify historical coverage. Public visibility alone does not settle redistribution rights; inspect [GitHub terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#d-user-generated-content) and corpus terms. |
| SEC filing subset | [Submissions API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) supplies filing history; [EDGAR resources](https://www.sec.gov/about/developer-resources) expose filings. | Acquire actual narrative filings, not only XBRL facts; distinguish reporting period from availability; assess boilerplate, amendments, rights, and access policy. |

Recommendation: implement the neutral adapter and evaluation harness first; qualify a small real corpus only afterward.
Dataset, representative query labels, analyst access, hardware, latency targets, and paid-model budget remain open decisions.
