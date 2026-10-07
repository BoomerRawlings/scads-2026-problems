# GraphRAG build specification

Build a reusable discovery service and a small analyst workspace: connect a corpus, investigate relationships, save a baseline, ingest updates, and explain what changed with inspectable evidence. The graph must improve discovery or reveal measurable limits of the approach.

**Status:** target design specification; the first local reference engine and authored temporal demo are implemented. See [implementation status](docs/implementation-status.md) for working scope and remaining gates. No real corpus has been acquired. Requirements marked **brief** come from Project 5. Other requirements are inferred implementation defaults, not additional user-confirmed constraints. Contracts define field semantics, this document defines scope, and the roadmap defines delivery order.

## Intent and implied behavior

| Stated need | Implied behavior | Boundary |
| --- | --- | --- |
| Discovery and sensemaking | Help form questions, connect evidence, and preserve an investigation across sessions | Fluent answers and attractive graphs alone do not demonstrate discovery |
| Flexible relationships | Store individual free-text assertions with stable endpoints and qualifiers | A flexible ontology still requires identity, provenance, and time structure |
| Query-time edge selection | Explain which evidence selected an edge; bound retrieval and expansion work | An embedding match is neither a verified fact nor a causal link |
| Temporal updates and baselines | Preserve source history, distinguish clocks, pair earlier/later support | New reporting, new interpretation, and real-world change are different |
| Graph manipulation | Separate navigation, hypothesis notes, and evidence-affecting review | Hiding an edge never retracts a source assertion |
| Medium to large scale | Measure quality, cost, update delay, and resource limits together | Proposed chunk counts do not establish achieved scale |

## First evaluated prototype

Default deployment: one analyst, one local service, public data, one corpus per query. User selected local models with no paid API dependency. Python/SQLite, a bounded browser workspace, and llama.cpp now implement this direction; PostgreSQL/pgvector remains a proposed scale backend. Model adapters remain replaceable within the local execution policy.

The first useful vertical slice must work through the same APIs intended for a later corpus: a small authored corpus, explicit gold assertions, two snapshots, a saved investigation, a comparison, and a cited evidence export. A deterministic extraction stub validates plumbing; a model-backed run is separately required to evaluate extraction. Neither demonstrates real-data scale.

| ID | Priority and origin | Required behavior | Build stage |
| --- | --- | --- | --- |
| R01 | P0 inferred | Adapter preflight declares supported text, history, dates, language, and update semantics; reject unsupported modes before expensive work | 0–1 |
| R02 | P0 inferred | Immutable source/processing identity, idempotent batches, atomically published snapshots, explicit processing coverage | 1 |
| R03 | P0 brief | Extract source-grounded entity mentions and text relationships; retain unresolved identities, qualifiers, modality, and evidence | 3 |
| R04 | P0 brief | Query-select relevant assertions; combine passage retrieval and bounded graph expansion with visible selection reasons | 2–4 |
| R05 | P0 brief | Filter knowledge/event time consistently through evidence, identities, summaries, and graph paths | 1–5 |
| R06 | P0 brief | Compare saved baselines using paired evidence and distinct source, knowledge, and world-state changes | 5 |
| R07 | P0 inferred | Save question, scope, anchors, selected findings, notes, and view; reopen without silently switching snapshots | 5–6 |
| R08 | P0 inferred | Open exact evidence from any result; show support, conflict, uncertainty, and bounded-search limitations | 2–6 |
| R09 | P0 brief | Navigate and manipulate the displayed graph; review changes append versioned decisions | 6 |
| R10 | P0 inferred | Enforce request/job budgets, expose progress/failures, cancel safely, and resume bounded work | 1–7 |
| R11 | P0 inferred | Export a local evidence bundle with citations, configuration, coverage, and verification manifest | 6–8 |
| R12 | P0 brief | Evaluate against non-graph retrieval; report quality/cost/update tradeoffs and useful negative results | 2–8 |

P0 means required for the first evaluated prototype, not required in the first code commit. Keep the P0 interface small; saved notes satisfy hypothesis capture initially.

**P1 after evidence of need:** dedicated hypothesis status tracking, named search collections, bounded connection/path queries, clustering and global-theme exploration, richer review queues, multilingual extraction, and optimized filtered ANN. Ordinary manual reruns remain P0. ANN moves earlier only if necessary to reach the declared measurement scale.

**Deferred:** scheduled alerts, multi-user permissions, private-data revocation/erasure, cross-corpus identity federation, distributed ingestion, autonomous graph edits, model training from feedback, and unrestricted agent exploration. These need separate requirements; no services or automation are authorized by this specification.

## Query behavior

| Intent | Required result | Honest limitation |
| --- | --- | --- |
| Find an entity or relationship | Ranked passages/assertions, disambiguation choices, selection reason | Same-name entities remain separate until resolved |
| Explore a neighborhood | Eligible edges, endpoints, supporting spans, expansion path | Visible subset; omitted/unknown counts distinguished |
| Review historical knowledge | Eligible source/interpretation versions at pinned cutoff | Reconstruction and exact saved replay labeled separately |
| Compare with baseline | Paired evidence, change category, review status, coverage | Ranked candidates are not an exhaustive change inventory |
| Test a proposed explanation | Supporting and conflicting passages, qualified inference | Missing support does not prove the explanation false |

Default to the latest complete compatible snapshot at request start; resolve “latest” once. Persist its ID with the result. Reopening an investigation uses its saved snapshot. “Check latest” is an explicit new run and does not overwrite the baseline.

An ambiguous entity or time expression returns a proposed interpretation and alternatives when choosing differently would change the answer. An omitted event-time constraint does not invent one. Unknown-time material may appear in a separately labeled group only under an explicit policy; it cannot support a strict historical conclusion.

## Baseline and change requirements

Baseline scope and comparison mode are independent. `saved_findings` rechecks selected assertion/source lineages, including evidence supporting or challenging them. `entity_neighborhood` fixes seed identities and a declared traversal rule, enabling discovery of new neighbors within that rule. Visual filters and pinned nodes do not redefine either scope.

Knowledge comparison examines newly published source/assertion/review events between snapshots. World-state comparison uses one compatible analysis snapshot at fixed K and evaluates supported states/events at V0/V1; the baseline contributes scope. It can find a transition already known before either time. Keep the original saved belief distinct from retrospective V0 evaluation. Planned transitions remain planned until occurrence evidence supports them.

Match records first by immutable lineage, then by reviewed identity/equivalence mappings. Treat a semantically similar assertion as an uncertain match until checked against endpoints, scope, time, and modality. A changed model, alias merge, paraphrase, or chunk boundary cannot alone establish real-world change.

Each change exposes old/new support, reason for categorization, effective/learned dates, matching basis, and uncertainty. Source document edits, corrected interpretations, new independent support, and duplicated reporting receive different labels. Keep contested claims available for inspection.

## Observable states

Readiness and evidence coverage are separate. A published lexical snapshot can be valid while graph extraction is unavailable. Completed extraction with zero assertions, extraction abstention, and extraction failure are separate outcomes.

| State | Interface behavior |
| --- | --- |
| No corpus or incompatible adapter | Show input requirements and missing capabilities |
| Processing or partially indexed | Show the last usable snapshot and explicit lag; never mix generations |
| Ready with exclusions | Show manifest exclusions and coverage; never imply full supplied-corpus coverage |
| Empty eligible result | Report no supported evidence found in the declared search scope |
| Ambiguous or conflicting | Preserve alternatives; allow source inspection and review |
| Budget exhausted or cancelled | Show validated completed work if available, truncation, and resume/retry information |
| Dependency unavailable | Return a typed failure or caller-authorized reduced mode; no silent modality change |
| Export cannot reproduce a dependency | Identify the missing artifact; never label the bundle fully reproducible |

## Resource and operational defaults

Reuse existing candidate/hop/context limits in the [architecture](docs/architecture.md). A server-owned budget profile additionally caps request deadline, total model calls/tokens, provider retries, job batch size, and concurrent jobs. Values requiring hardware/model information remain deployment configuration; refuse an unbounded profile.

Budgets are cumulative across expansions, comparison pages, retries, and model subcalls in one logical run. A resume spends the remaining budget; a larger budget requires an explicit new run/profile. Native database scan work may be measured rather than hard-countable; enforce deadlines and report unavailable scan counters as unknown.

Per-request wall deadlines, cumulative active execution time, and run/cursor expiry are separate. Analyst idle time does not consume active execution allowance. Expiry never refills budgets or erases saved baseline evidence.

Cancel stops new dispatch and publication, but does not promise that already-running provider work is unbilled. A failed database statement may yield no rows; never manufacture partial results. Include cancellation, retry, failed-call, indexing, and update costs in measurements.

Source content and model output are data. They cannot alter the query scope, invoke tools, rewrite instructions, or publish annotations. Annotation proposals and applied decisions have distinct effects and history. No source text is executed during parsing or retrieval.

## Completion evidence

The [acceptance specification](docs/acceptance.md) supplies deterministic fixture cases; the [evaluation plan](research/data-and-evaluation.md) supplies real-data measurements. The [analyst workflows](docs/analyst-workflows.md) define the user journey and visible states.

Delivery requires: fixture replay and evidence checks; one end-to-end analyst journey; real-data quality/cost comparisons at a declared measured scale; explicit failure analysis; and a reproducible local export. Freeze real-data thresholds before opening held-out labels. No corpus, provider, hardware, calendar estimate, or numerical quality/latency guarantee is assumed here.
