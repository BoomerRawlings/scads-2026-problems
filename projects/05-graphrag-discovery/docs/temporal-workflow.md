# Temporal discovery workflow

Status: contract plus an implemented deterministic subset in the SQLite reference engine; see [implementation status](implementation-status.md). The full design remains backend-neutral and compatible with the proposed PostgreSQL claim ledger. Dates below are exercised by authored fixtures; no real corpus or model extraction has been evaluated.

## Evidence from existing systems

- Zep/Graphiti models episode, entity, and community layers, with separate event and ingestion timelines. Its paper describes LLM-based contradiction detection and prioritizing newer information for invalidation. This motivates a comparator, not automatic trust in the newest source. [Zep paper, §§2–3](https://arxiv.org/html/2501.13956v1)
- Zep calls edge facts derived claims; timestamps do not establish truth. It exposes `valid_at`/`invalid_at` for world-time bounds and `created_at`/`expired_at` for learning/invalidation time. [Zep facts](https://help.getzep.com/facts)
- Current Zep explicit datetime filtering applies to edges; node and episode searches ignore those filters. Therefore, an edge filter alone cannot establish cutoff safety for assembled context. This is a design inference, not a claim that all Graphiti versions share the cloud API behavior. [Zep search documentation](https://help.getzep.com/searching-the-graph)
- Bitemporal row versions and inclusive-start/exclusive-end intervals are established database patterns; XTDB documents both. We borrow semantics, without requiring XTDB. [XTDB concepts](https://docs.xtdb.com/concepts/key-concepts.html#temporal-columns-bitemporality)

## Time and provenance contract

| Field | Meaning |
|---|---|
| `source_available_at` | Nullable, publisher-asserted earliest availability; not proof of system observation. Preserve publication metadata separately when different. |
| `ingested_at` | Trusted first durable receipt of this exact source version. Preserve separate later processing time. |
| Source/processing `visible_from`, `visible_seq` | First query-visible activation, including source-only snapshots; strict system-history search requires this at/before cutoff. |
| `prepared_at` | Staging/processing time; never query-visible knowledge by itself. |
| `recorded_at`, `commit_seq` | Server-assigned query-facing ledger activation time and total ordering, assigned at atomic snapshot publication. Never backdate actual ingestion. |
| `valid_from`, `valid_to` | Claimed world-state interval, `[from,to)`; open end allowed only when explicitly modeled. |
| `event_time` / event interval | Time of an occurrence; preserve its precision rather than turning every event into a lasting state. |
| `knowledge_from`, `knowledge_to` | Conceptual view fields for interpretation visibility, `[from,to)`: start is `recorded_at`; end derives from supersession commit. Source history remains available. |
| `time_basis`, `precision`, `temporal_status` | Explicit date, relative-to-source date, inference; instant/day/month; each temporal bound known/open/unknown, with uncertainty retained separately. |
| `source_version_id`, `source_span`, `content_hash` | Immutable evidence identity, exact locator, duplicate/revision detection. |
| `claim_id`, `claim_version_id`, `supersedes_id` | Stable claim identity, immutable interpretation, explicit revision chain. |
| `extractor_version`, `prompt_hash`, `embedding_version` | Reprocessing lineage; extraction changes are not world changes. |

Store offsets and source timezone; normalize query boundaries to UTC. Resolve “last month” against a recorded reference time/timezone. Missing or uncertain dates stay explicit; never substitute receipt time for event time silently.

An open endpoint means “no asserted end,” not guaranteed persistence. An unknown endpoint is distinct from infinity. Strict point-in-time answers use only sufficiently supported intervals; return uncertain candidates separately. A day-granularity event remains a day interval, not an invented midnight instant.

## Append-only update workflow

1. Persist each source version before extraction; deduplicate identical content, retaining each observation and provenance link.
2. Extract attributed claims and temporal evidence spans. Keep the source assertion separate from the system's interpretation and analyst assessment.
3. Resolve entities using the mapping visible at the processing snapshot. Version aliases and merge/split decisions; retain original mention identifiers.
4. Retrieve possible duplicate, revision, and contradiction candidates within a bounded entity/event neighborhood. Record comparison coverage and unresolved candidates.
5. Stage decisions and new claim versions with processing times. Build replaceable projections; derive old version end-times from activated supersession events without rewriting immutable records.
6. Atomically activate query-facing ledger events and a snapshot when its declared ledger/entity/evidence/index watermarks agree. Assign `recorded_at` then; expose lag rather than treating staging as historical knowledge. Source-only generations may publish before graph capability exists.
7. Update only affected embeddings/summaries and record dependency versions. Rebuild a projection from the ledger to audit it.

| Incoming evidence | Required treatment |
|---|---|
| Repeated support | Add provenance; do not announce a newly discovered world event. Preserve source dependence/republication links. |
| Actual state transition | Add successor state/event; close predecessor validity only when evidence supports the transition and applicable scope. |
| Corrected date/text | Append corrected interpretation linked to the earlier version; preserve what the system previously believed. |
| Source retraction | Append withdrawal of that source's support; re-evaluate dependent claims. Retraction alone does not prove the opposite. |
| Conflicting report | Retain both attributed claims; add a disputed relationship. Recency alone cannot settle it. |
| Entity merge/split | Append reversible identity decision. Reproject affected relationships; classify resulting differences as identity revision. |
| New extraction/model | Append new interpretation and lineage. Classify new findings from old sources as processing discoveries. |

Conflicts require overlapping time, compatible scope, and mutually exclusive meaning. Free-text relationship similarity is only candidate evidence; multiple jobs or locations need not conflict. Unknown scope/temporal overlap yields a conflict candidate, not automatic invalidation.

## Query semantics

`search` pins `snapshot_id`, `knowledge_cutoff K`, optional `valid_time` (point V or event window `[A,B)`), evidence-status policy, and entity-map version. `compare` pins `baseline_id` and target snapshot. Pin a ledger sequence with K to resolve equal timestamps. Preserve question and interpreted temporal constraints in the response.

For a claim version with known bounds, the conceptual predicate is:

```text
visible(c,K) = c.knowledge_from <= K < c.knowledge_to
holds(c,V)   = c.valid_from <= V < c.valid_to
state(V,K)  = visible(c,K) AND holds(c,V) AND selected_status_policy(c)
events(A,B,K) = visible(c,K) AND event_interval(c) overlaps [A,B)
```

These are predicates over versioned interpretations, not a filter over today's mutated edges. Strict system-as-known mode additionally requires source `ingested_at <= K`, source/processing `visible_from <= K`, claim/extraction `recorded_at <= K` when applicable, and cutoff-safe dependencies. Source-only lexical/evidence reads enforce activation without needing a claim. Evidence-history mode also returns superseded/retracted versions with their statuses.
Published-history replay is a separately tagged reconstruction using `source_available_at` and a documented availability assumption; it cannot establish what this system actually knew then. A modern extraction of an old source is likewise not a historically recorded interpretation.

| Analyst intent | Operation |
|---|---|
| “What did we know then?” | Fixed historical K; query V/window independently. |
| “What do we now believe happened then?” | Latest complete K; historical V/window. |
| “What new information arrived?” | Source receipts in `(K0,K1]`, including late accounts of old events. |
| “What new information was interpreted?” | Claim/version commits in `(K0,K1]`; label processing lag and reprocessing. |
| “What changed in the world?” | Compare world states at V0/V1 using one fixed K; report evidence-supported transitions. |
| “What changed since my baseline?” | Compare saved baseline with current evidence; separate categories below. |

A baseline stores scope/query, K, valid-time window, snapshot/version identifiers, evidence IDs, findings, and retrieval budget. Its document and interpretation set is immutable. A reproducible comparison uses a fixed analysis policy; changing that policy is separately reported.

Baseline kind is separate from the comparison clock: `saved_findings` follows selected evidence/interpretation lineages; `entity_neighborhood` fixes seed IDs and a traversal/filter rule applied at each boundary. A saved canvas is not a complete baseline scope. New neighbors can enter the latter mode; truncated neighborhoods cannot establish disappearance.

Delta categories: `newly_observed_event`, `new_support`, `late_evidence`, `correction`, `retraction`, `unresolved_conflict`, `identity_revision`, `processing_discovery`, `coverage_change`.
One record may carry several labels. “Newly observed” refers to the analyst baseline; “actual change” additionally requires event-time evidence. Missing evidence or a changed top-k result is not proof that a relationship ended.
Compare the eligible evidence/claim set within declared scope; if only ranked samples are compared, label the result retrieval differences and report coverage limits.

Knowledge/source comparisons enumerate published commit events and reconcile baseline members. World-state comparisons at fixed K enumerate eligible validity/event boundaries and evaluate both state projections; no new ledger commit is necessary. Match explicit lineage before semantic candidates, and preserve uncertain matches. One publication batch may contain several event times; one event may be reported in many later batches.

World-state mode uses one compatible `analysis_snapshot_id` supporting K, with explicit V0/V1. The saved baseline contributes scope, not its older knowledge boundary; label its original findings separately from a retrospective V0 interpretation using later evidence. Knowledge/source mode instead keeps both historical boundaries.

## Worked synthetic example

Assume UTC dates and a fictional pump with one operator. Each source is promptly processed on its receipt date; this is a fixture assumption, not the production rule.

| Receipt/commit | Source statement | Ledger interpretation |
|---|---|---|
| 2025-01-05 | A operates Pump P from January 1. | A valid from January 1; no known end. |
| 2025-01-20 | B will replace A on February 1. | Projected A end/B start on February 1; preserve planned modality, with occurrence unconfirmed. |
| 2025-02-10 | Correction published February 4: handover actually February 3. | Supersede prior date interpretation; A ends February 3, B begins February 3. |
| 2025-02-12 | Independent report says C took over February 3. | Keep B and C claims, marked disputed; neither automatically wins. |
| 2025-02-15 | The February 12 publisher retracts its C report. | Withdraw C support; retain report and retraction in history. |

- `state(2025-02-02, K=2025-02-05)` returns B only as the planned operator, with actual handover unconfirmed; it cannot use the unreceived correction. A confirmed-state-only query abstains on who actually operates the pump.
- `state(2025-02-02, K=2025-02-11)` returns A under the corrected timeline, with correction provenance.
- `state(2025-02-04, K=2025-02-13)` returns disputed B/C claims, not a fabricated settled operator.
- Compared with a January 25 baseline, February 10 adds late evidence plus a corrected date. The receipt on February 10 is not a February 10 handover.
- At K=February 11, comparing world state January 31 versus February 4 supports A→B effective February 3; citation proves the reported transition, not independent truth.
- February 15 retracts support for C; it does not imply a C→B transition on February 15.

A's interpreted intervals are `[Jan1,∞)` at knowledge `[Jan5,Jan20)`, a projected `[Jan1,Feb1)` at `[Jan20,Feb10)`, and a retrospectively reported `[Jan1,Feb3)` at `[Feb10,∞)`. B's planned February 1 and reported February 3 start-date versions have the corresponding knowledge intervals. Modality is part of each interpretation: passing the scheduled date never confirms occurrence. Original source assertions remain immutable.

## Cutoff-safe retrieval and summaries

- Apply snapshot/temporal eligibility before evidence reaches expansion, reranking, summarization, or answer generation. Recheck canonical versions after approximate retrieval and before serialization.
- Every expansion hop uses the same K. Entity aliases, merge decisions, relevance features, counts, community membership, and summaries are versioned too; future structure can leak into candidate selection.
- Summary records carry exact transitive evidence/version dependencies, temporal scope, policy/model version, generation time, and snapshot ID. Use a summary only if all included material and interpretations are eligible for the requested scope/K; otherwise regenerate from eligible evidence or bypass it.
- Distinguish retrospective reconstruction from literal historical replay. A summary generated today from cutoff-safe evidence is a reconstruction; replay requires the actual historical artifact/configuration. Neither may cite later evidence.
- Index immutable claim-version IDs and verify temporal filtering semantics for the chosen backend. Future candidates can crowd out historical neighbors even when post-filtering removes them; measure recall against exact eligible-vector search, then use filtered search, snapshot partitions, or bounded oversampling with an explicit truncation flag.
- Strict replay also pins index/corpus statistics and model versions. Ground answers in allowed citations; model pretraining itself is outside corpus-cutoff guarantees, so unsupported recollections cannot become findings.
- Cache keys include K/snapshot, valid-time scope, status policy, entity-map version, retrieval configuration, and model versions. New evidence invalidates affected current caches, not saved baselines.
- Extraction caches also include source date/timezone, language, reference context, and processing profile. Identical “last month” text in differently dated sources must not reuse a resolved time interval.

## Future acceptance cases

Require exact expected evidence IDs/statuses for the worked example, out-of-order receipts, overlapping/unknown dates, scheduled future changes, corrections, retractions with other surviving support, independent conflicting sources, and merge/split reversals.
Plant distinctive future-only text in a source, entity summary, community summary, cache, and alias mapping: no historical query may retrieve, traverse, or cite it. Compare index retrieval with exact cutoff-filtered retrieval and audit every context dependency.
Separate timestamp/extraction accuracy, temporal eligibility violations, delta-label accuracy, eligible-evidence recall, and answer support. Require zero observed cutoff violations in deterministic fixtures; report sample size and failures separately on a real corpus.
LongMemEval distinguishes temporal reasoning, knowledge updates, and abstention, supporting separate evaluation dimensions; its conversational setting does not establish this project's large-corpus discovery performance. [LongMemEval paper](https://arxiv.org/abs/2410.10813)
