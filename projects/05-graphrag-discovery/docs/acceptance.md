# Acceptance scenarios

Status: target acceptance specification. The SQLite reference engine, authored fixtures, and unit suite cover a subset; [implementation status](implementation-status.md) maps tested portions and outstanding work. No real-data quality or scale result exists.
`S0`–`S8` refer to [roadmap stages](../ROADMAP.md); operation names refer to the [service contract](contracts.md).
These are proposed behavioral requirements. Numerical defaults in the architecture/evaluation plans are tuning proposals, not user-confirmed thresholds.
Each future check records fixture/version, request, expected IDs/statuses, actual result, trace, and pass/fail; never infer success from a screenshot alone.

## Fixture design

Use authored public-scope documents, deterministic ingestion/ledger clocks, fixed chunk offsets, and stubbed extraction/embedding outputs.
Specify expected evidence and temporal states independently of the code under test. Stub correctness does not validate a real extractor.

| Fixture | Contents and independent expectations |
| --- | --- |
| F1 Pump history | Reuse the [worked timeline](temporal-workflow.md#worked-synthetic-example): January 5 A report; January 20 planned B; February 10 corrected handover; February 12 conflicting C; February 15 C withdrawal. Give each source, revision, span, assertion, and commit a stable ID. |
| F2 Source dependence | Two independent supporting reports, one copied report, one explicit denial, and one source withdrawal; expected provenance groups and surviving support enumerated. |
| F3 Identity | Same name for distinct entities; explicit alias; later reviewed merge; reversal/split; original mention IDs retained. |
| F4 Pipeline failure | Duplicate batch, out-of-order revisions, conflicting hash, invalid span, unknown language/date, failed embedding, empty extraction, crash before publication. |
| F5 Retrieval | Hand-authored vectors with exact distances, ties, eligible past neighbors, future-only neighbors, high-degree hub, disconnected evidence, and negated/planned assertions. |
| F6 Change and interface | Baseline findings with unchanged support, extra corroboration, corrected support, unsupported ranking disappearance, and new evidence outside the initial top-k; enough events/results for several pages. |

## Deterministic behavioral acceptance

### A01 — Idempotent input and revision order (S1; `ingest`)
Given F4, replay the same batch and deliver an older explicit revision afterward: no duplicate durable version/assertion; no latest-state rollback from arrival order. Checkpoint advances only after durable receipt; retry preserves trusted first-ingestion time.
Same idempotency key with identical payload returns the saved outcome; changed payload returns `idempotency_conflict`. A pending reference is reported and never silently discarded.

### A02 — Invalid and unavailable evidence (S1/S3; `ingest`, extraction)
Conflicting immutable hashes, invalid offsets, unsupported scope, or malformed model output produce typed rejection/quarantine with record IDs. Valid records remain inspectable; rejected/missing records appear in coverage. Empty extraction is valid and distinguishable from failure.

### A03 — Readiness is mode-specific (S1–S3; `publish_snapshot`, `search`)
A complete source-only snapshot supports lexical/evidence operations and explicitly reports unavailable graph capabilities. Graph readiness requires matching ledger, identity, evidence, embedding/index watermarks for its declared profile; partial extraction never appears complete. Excluding failed records requires an explicit revised manifest.

### A04 — Atomic publication and resume (S1/S5; job operations)
Crash between indexing and publication: previous snapshot stays queryable; the new one remains unpublished. Retry resumes committed work idempotently; only validated publication changes readiness. Concurrent queries retain their pinned snapshot throughout the request.
Exercise cancel-before-activation and cancel-after-activation: the former cannot publish; the latter reports `already_published` and leaves history intact.

### A05 — Exact grounded evidence (S2/S3; `get_evidence`)
Every F1/F2 assertion opens its exact normalized substring and original-source locator under the pinned source/processing versions. Endpoints, direction, qualifiers, negation, modality, and dates match supplied evidence; invalid or unsupported fields fail validation instead of becoming facts.

### A06 — Absence is not a negative (S2/S4; `search`)
No matching edge, empty extraction, disconnected graph, absent top-k item, and exhausted budget produce distinct coverage/unknown states. None becomes “no relationship exists.” F5's explicit denial retains a cited negated assertion; graph paths alone never become causal findings.

### A07 — Late arrivals and delayed interpretation (S3/S5; `search`, `compare`)
F1's February 4 publication received February 10 is absent at system cutoff February 5. Assertion visibility begins at atomic snapshot activation (`recorded_at`), never staging `prepared_at`; extraction delay delays visibility. Report late evidence/processing lag; do not backdate receipt or call February 10 the handover date.

### A08 — Plans do not confirm themselves (S3/S5; `search`)
F1 at event February 2/knowledge February 5 returns B only as planned, actual operator unconfirmed. Advancing the wall clock past February 1 cannot change modality. At knowledge February 11, corrected evidence supports A for February 2 and reported B from February 3.

### A09 — Precision, unknown bounds, and query mode (S2/S5; `search`)
Date-only/unknown bounds retain precision; unknown is not infinity. Check `[from,to)` boundaries and timezone conversion. Unknown required time returns unsupported/qualified uncertainty, never silent widening. Knowledge-change fixes event scope; world-state comparison fixes knowledge scope.

### A10 — Corrections preserve prior belief (S3/S5; `compare`, `get_evidence`)
F1 correction adds a linked interpretation and keeps the prior date/version accessible. Historical queries reproduce earlier supported interpretations; current queries show correction provenance. A parser/extractor change on identical source bytes is processing discovery, not a new world event.

### A11 — Withdrawal removes only affected support (S3/S5; `compare`)
Withdraw one F2 source: remove its support from the current policy view and invalidate dependent current caches; other independent support survives. Keep allowed historical evidence/statuses. Withdrawal alone proves neither opposite claim nor a transition; source withdrawal never masquerades as access erasure.

### A12 — Conflict and duplicated reports (S3/S4; extraction, `search`)
F1's B/C claims coexist as disputed at knowledge February 13. F2 copies share provenance lineage and do not count as independent corroboration. Conflicts require mutually exclusive meaning and compatible time/scope; recency or embedding similarity cannot automatically settle them.

### A13 — Versioned identity decisions (S3/S5; `annotate`, `apply_review`, `search`)
F3 homonyms remain unresolved/separate until evidence supports mapping. A reviewed merge, reversal, or split adds versioned decisions and reprojects affected assertions without rewriting source mentions. Earlier snapshots keep prior mappings; resulting changes are identity revisions, not source/world changes.

### A14 — Cutoff safety and replay honesty (S2/S5; `search`)
Plant F5 future-only text in sources, aliases, descriptions, summaries, index features, and caches: none influences eligible context/traversal in strict historical mode. Recheck before serialization. Missing historical artifacts return `replay_unavailable`; cutoff-safe reconstruction and simulated published-history replay are explicitly labeled.

### A15 — Temporal-filter recall reference (S2/S7; retrieval)
F5 exact filtered search returns the independently enumerated nearest eligible IDs, including ties under deterministic ordering. Compare ANN against that reference across narrow/broad filters; empty post-filter results cannot imply no evidence. Expose scan exhaustion and fallback use; perfect ANN recall is not presumed.

### A16 — Stable logical result pages (S2/S6; `search`, `expand`)
F6 pages share one snapshot, effective scope, and deterministic result/enumeration identity. Repeating a cursor reproduces its page; traversing all pages yields no missing/duplicate IDs within that declared result set despite concurrent ingestion. Paging a frozen ranked subset never claims exhaustive corpus coverage.

### A17 — Cursor scope cannot drift (S2/S5; all paged reads)
Changing corpus, snapshot, temporal/status policy, entity mapping, baseline pair, or retrieval configuration invalidates the applicable cursor. Tampered, unknown, or expired cursors return typed restart guidance; never fall through to the latest scope. Cross-scope IDs are revalidated server-side.

### A18 — Bounded graph work, not just display (S4; `search`, `expand`)
F5 hub queries enforce per-node, explicit visited-edge, hop, candidate, rerank, and evidence-token caps before additional work. Cycles deduplicate; hidden nodes do not evade accounting. Native database scan counts may be approximate/unknown; enforce statement deadlines and never treat result LIMIT as a scan bound. Return validated partial evidence if available, reached limits, omitted counts when known, and a valid continuation only when supported.

### A19 — Query cancellation and resource exhaustion (S4/S5; queries/jobs)
Exhaust each enforceable time/token/call/explicit-work cap independently; no new work dispatches afterward. Cancellation propagates to cancellable work; any unavoidable in-flight usage is recorded. A cancelled database statement may return no rows; only completed-stage evidence may appear as partial results. Cancelled writes cannot publish a mixed snapshot or silently auto-resume spending.

### A20 — Baseline reconciliation, not top-k subtraction (S5; `save_baseline`, `compare`)
F6's unchanged finding dropped from ranking remains supported; an added corroboration is new support; a correction gets paired old/new evidence. Enumerate scoped ledger changes plus revalidate saved findings against target evidence, including changes outside top-k. Unexamined findings remain unknown, never removed.

### A21 — Comparison completeness and continuation (S5; `compare`)
For knowledge change, pin both snapshots, stable `(commit_seq,event_id)` boundaries, baseline findings, and policy. Resume F6 with tiny page caps inside a finite total run allocation, without lost/duplicate events or findings; advance even across zero-relevance scanned batches. Exhausting the run allocation requires an explicitly allocated new run to continue. Repeated completed pages do not repeat model work. Declare complete only after scoped event enumeration and baseline reconciliation finish; otherwise return coverage limits. World-state coverage follows A26.

### A22 — Review concurrency and reversibility (S5/S6; `annotate`, `apply_review`)
Two effective corrections target the same prior projection/review-head version: accept one and reject the stale action with conflict details. Independent notes may append concurrently without changing that projection. Store actor, reason, cited evidence, and affected version; reversal appends another event. Analyst assessment never overwrites source wording or silently becomes independently verified truth.

### A23 — Analyst scope remains visible (S6; workspace)
Complete search → evidence → graph → baseline → update → comparison using F6. Every surface shows compatible snapshot/time scope, unresolved states, and truncation. Counts distinguish displayed/returned/eligible totals and unknown totals; graph layout/hiding changes no evidence state. Refresh requests an explicit new snapshot.

### A24 — Reproducible evidence exports (S6/S8; export)
Export F6 findings with snapshot/baseline IDs, effective query/scope, source/processing versions, exact citation spans/hashes, assertion/review status, time basis, model/config versions, coverage, and usage. Reopening preserves links to both comparison sides; partial exports stay labeled. Include permitted excerpts/attribution, not unsupported claims of full-corpus evidence.

### A25 — Supported answers and failure behavior (S4/S8; synthesis)
For all fixtures, each accepted factual finding cites eligible supporting spans and preserves negation/plans/disputes. Unanswerable questions abstain with coverage limits; model recollection and plausible prose are insufficient. Provider timeout/invalid output yields typed failure or evidence-only partial output, never fabricated citations.

### A26 — World-state change without new commits (S5; `compare`)
At fixed F1 knowledge February 11, compare event January 31/February 4: report the supported A→B transition on February 3 even with zero new commits between requests. Enumerate eligible validity/event boundaries and both state projections, not commit deltas alone; pin K/V0/V1 in coverage/cursors. At knowledge February 5, crossing February 1 yields a planned transition only.
Both projections use one compatible analysis snapshot; an older saved baseline contributes scope, not an older K. Label its originally saved belief separately from the retrospective earlier state.

### A27 — Context-sensitive extraction caching (S3/S5; extraction)
Give identical text “Last month, R signed the agreement” independently documented reference dates January 15 and February 15, 2025 (UTC). Expected event intervals are December 2024 and January 2025, with month precision. Resolved outputs must not collide: key on temporal/source context and interpretation profile as well as text/model/prompt/schema. Raw span reuse is allowed; resolved-date reuse across contexts is not.

### A28 — Saved investigations and baseline scopes (S5/S6; investigation and baseline operations)
Save/reopen F6's question, selected identity, hypothesis note, run, baseline, and view; preserve the original snapshot while showing newer availability. A new neighbor enters `entity_neighborhood` under its fixed rule; `saved_findings` changes only through tracked lineage/evidence matches. Hidden canvas elements affect neither scope. Changing seed/filter/radius creates a new baseline. Unsupported claims in notes cannot become cited findings on reopen/export.

### A29 — Source instructions cannot control execution (S1/S4/S6; parsing, synthesis, review)
Add source text and model output requesting relaxed time filters, tool execution, or automatic review approval. Treat them as content; validation retains scope/budgets, invokes no requested external action, and applies no review decision. Findings may quote eligible evidence, but the data never becomes executable instructions.

### A30 — Clarification and declared fallback (S2/S4; `search`)
F3's homonym and an outcome-sensitive ambiguous date produce candidate interpretations without globally merging identities or widening scope. Request graph retrieval from a lexical-only snapshot: reject unsupported capability unless the caller explicitly permits lexical fallback. Report the effective mode, missing capabilities, extraction coverage, and original constraints. Unknown-time material stays outside strict temporal support.

### A31 — Source-only activation and idle time (S1/S2/S5; snapshot and query operations)
A document received January 1 but first published in a source-only snapshot January 3 is unavailable to strict system-history lexical lookup and `get_evidence` at K=January 2; receipt alone is insufficient. Published-history reconstruction is separately tagged. Repeated receipt preserves original activation; a changed processing profile gets its own activation. Between completed pages, simulated analyst idle time leaves active execution allowance unchanged, while a separately expired cursor returns its typed error without refilling budget.

## Requirement traceability

Requirement IDs refer to the [build specification](../BUILD_SPEC.md). These are target acceptance checks; the implementation mapping above distinguishes tested subsets from complete acceptance.

| Requirement | Principal cases |
| --- | --- |
| R01 Adapter preflight | A02, A03, A30 |
| R02 Versioning and publication | A01, A02, A03, A04, A07, A31 |
| R03 Grounded extraction | A05, A10, A12, A13, A27 |
| R04 Bounded retrieval | A06, A15, A18, A19, A25 |
| R05 Temporal safety | A07, A08, A09, A14, A26, A27, A31 |
| R06 Baseline comparison | A10, A11, A20, A21, A26, A28 |
| R07 Investigation persistence | A23, A28 |
| R08 Inspectable evidence | A05, A06, A12, A24, A25, A30 |
| R09 Graph manipulation and review | A13, A22, A23, A28 |
| R10 Resource and failure behavior | A01, A04, A16, A17, A18, A19, A21, A29, A31 |
| R11 Evidence export | A24, A28 |
| R12 Evaluation | A15, A25 and real-data/performance gates below |

## Real-data and performance gates

Behavioral acceptance means all applicable deterministic cases pass with archived traces; it establishes software invariants, not useful discovery or statistical accuracy.
Before real-data evaluation, qualify one corpus/adapter, review temporal semantics and rights, independently label evidence, and lock held-out query groups. Follow the [evaluation plan](../research/data-and-evaluation.md).
Report extraction, resolution, time interpretation, eligible-evidence retrieval, answer support, change quality, and analyst usefulness separately; investigate observed violations rather than hiding them in averages.
Compare lexical, dense, hybrid, hybrid+edge text, and bounded graph expansion with the same evidence eligibility and answer budgets; isolate extraction benefit from topology benefit.
For temporal ANN, report eligible-set size/selectivity, exact-reference recall, fallback rate, latency, and truncation. Freeze a minimum recall target after pilot measurements and before held-out testing.
For scale, report actual active/history chunks, assertions, degree distribution, hardware, concurrency, p50/p95, failures, memory/storage, build/query/update cost, and update lag.
Proposed 10k/100k/1m chunk stages, concurrency sweeps, and interactive caps are experiments; no size, latency, quality, or cost has been achieved or user-approved.
Freeze useful-quality gains and maximum latency/cost/update-delay targets before test labels are opened. A documented negative graph result remains acceptable research; it does not pass an unmet product target.
Synthetic stress data can verify termination/resource behavior only. Natural-language diversity, temporal label accuracy, and analyst benefit require real evidence and disclosed sample sizes.
