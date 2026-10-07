# GraphRAG implementation roadmap

Implementation has started: a runnable SQLite evidence/temporal reference slice spans portions of Stages 0–6. No stage is declared complete solely from that slice. See [implementation status](docs/implementation-status.md) for tests, restrictions, and next gates.

Build a replayable evidence workflow first, then plug in a qualified corpus and measure where graph retrieval helps. Work packages below are dependencies, not calendar estimates; corpus, hardware, and model budgets remain undecided.

The [build specification](BUILD_SPEC.md) defines 12 requirements and release scope; [acceptance](docs/acceptance.md) defines cases A01–A31 and their requirement mapping. This roadmap includes the inferred product and operational behavior needed to make the original design implementable.

## Ordered work packages

| Stage | Deliverables | Acceptance gate |
| --- | --- | --- |
| 0 Contract and fixtures | Versioned operation/record schemas; capability, coverage, budget, finding/citation, review, and export contracts; authored fixtures F1–F6 with deterministic model stubs | Expected IDs/spans/time states independently specified; fixture and real-model runs cannot be confused |
| 1 Ingestion and history | Adapter preflight, lifecycle IDs, original/processing versions, chunks, single worker/checkpoints, staged ledger, atomic capability snapshots | Same-key payload conflict, out-of-order events, cancellation races, and source-only readiness pass A01–A04/A07; partial jobs cannot silently publish graph capability |
| 2 Retrieval baseline | Lexical/exact dense retrieval, typed plans/scope, structured evidence, persisted runs, logical result paging, model-free lookup | Grounding, empty states, cutoff filters, cursor stability, and explicit fallback pass A05/A06/A14–A17/A30 before graph extraction |
| 3 Graph extraction | Replaceable model adapters, occurrences/interpretations/projected edges, unresolved identities, context-aware cache, extraction outcome coverage | Fixture truth and actual model quality evaluated separately; malformed/unsupported assertions abstain or quarantine; A05/A08–A13/A27 |
| 4 Bounded GraphRAG | Fusion, bounded expansion, selection explanations, reranking, supported synthesis, cumulative run budgets/cancellation | Graph-on/off uses identical inputs/model/budgets; explicit visits and calls bounded; database deadlines honest; A18/A19/A25/A29 |
| 5 Baselines and updates | Saved-findings/neighborhood scopes, mode-specific comparison, lineage matching, paired evidence, bounded resume, invalidation, run/baseline persistence | Knowledge changes versus fixed-K world transitions correct; baseline reconciliation complete within declared scope; A10/A11/A20/A21/A26/A28 |
| 6 Analyst workspace | Persisted investigation/notes/view, scope controls, evidence/graph/timeline, proposed versus applied review, local evidence export | Full analyst journey restores original snapshots; graph views do not rewrite facts; reversals, exports, and reopen pass A13/A22–A24/A28 |
| 7 Scale evaluation | Filtered ANN, cost telemetry, update workloads, concurrent queries, backend alternatives only as needed | Publish quality/latency/memory/update-cost curves and failure regimes; every scale result states actual corpus and hardware |
| 8 Demonstration | Reproducible run, error analysis, dataset manifest, documented limitations, export for website | Findings independently traceable; success or negative result supported by measurements; PDF/site packaging afterward |

Stages 0-2 can start with authored fixtures. A real corpus can then be connected through the adapter; reserve a held-out evaluation split before tuning extraction or retrieval. Stage 3 and UI wireframes can proceed in parallel after contracts stabilize. Final UI integration depends on the evidence and temporal APIs.

## Vertical delivery checks

1. **Evidence slice:** ingest fixture versions → publish source-only snapshot → lexical query → exact passage → persisted run. No model key required; prove failure/coverage handling first.
2. **Temporal slice:** inject gold extraction/embedding outputs → publish graph snapshots → save both baseline kinds → ingest update → compare → reconstruct prior knowledge. Exercise all three comparison modes before optimizing retrieval.
3. **Analyst slice:** query → disambiguate → inspect → save investigation → manipulate view → compare → apply review → export/reopen. Hypotheses remain ordinary notes for P0.
4. **Evaluation slice:** replace stubs with actual models; plug in a qualified corpus; freeze held-out questions and targets; run baseline/graph/update experiments and explain error/cost regimes.

Each slice uses the same contracts as later stages. Stubbed temporal/UI checks may run before the full extraction milestone; they cannot satisfy real-model acceptance. CLI operations are the first clients, not a second implementation of business logic.

## Planned module boundaries

```text
adapters/        corpus normalization and update cursors
core/            validated records, identifiers, temporal projections
storage/         migrations, snapshots, files, indexes
pipeline/        chunking, extraction, resolution, embeddings, jobs
retrieval/       lexical, dense, expansion, reranking, evidence packing
discovery/       baselines, comparison, citations, analyst annotations
interfaces/      CLI first; MCP and HTTP wrappers when needed
evaluation/      gold records, workloads, metrics, replay checks
web/             analyst interface after service contracts stabilize
```

These are planned responsibilities, not existing implementation. Keep one package until actual deployment boundaries require separation.

Persist investigations/runs/reviews in the existing database and export through the discovery layer; no separate workflow engine is needed. Use dependency membership and snapshot generations for invalidation, not a full file/vector clone at every update.

## Experiment gates

**Correctness first:** exact source/version citations, strict cutoff eligibility, deterministic history projection, and explicit unknowns. Exercise model failures and partial updates as well as the happy path. Query-model memory is never a substitute for corpus evidence.

**Operationally complete:** bounded corpus preflight, idempotency conflicts, restart/cancel/publication races, source-only historical visibility, coverage-aware fallback, stable pages, cumulative budgets excluding analyst idle time, source-data instruction isolation, and reproducibility-level reporting. All 31 applicable deterministic acceptance cases require traces; documentation checks alone do not pass them.

**Quality second:** compare lexical, dense, hybrid, hybrid plus edge retrieval, and hybrid plus edge retrieval/expansion. Use the same eligible source versions, synthesis model, token ceiling, and evaluation questions. Compare observed quality/cost frontiers as well as equal budget settings. Community-summary and deferred-extraction methods are optional follow-up comparators.

**Scale third:** proposed checkpoints of 10,000, 100,000, and 1,000,000 chunks, with actual assertion/vector counts reported. Set pilot-derived latency, update, quality, and cost targets before held-out evaluation. No universal promise attaches to the word “large.”

The [evaluation plan](research/data-and-evaluation.md) defines labeling, leakage checks, workloads, and reporting. Synthetic fixtures prove behavior; duplicated or generated bulk data can stress capacity but cannot establish useful discovery on diverse human text.

## Decisions when a dataset is selected

1. Confirm use cases, document/version semantics, source rights, languages, and time-field meaning.
2. Implement one adapter and report missing history/timestamps before ingesting the full corpus.
3. Freeze representative query families and hold out entities/documents/time ranges appropriately.
4. Choose extraction, embedding, and synthesis models from a small measured pilot; record their full cost.
5. Set a hardware/resource budget, deployment target, and acceptance thresholds from pilot evidence.

Model execution policy is now user-selected: local models without paid APIs. Qualify model weights, supported languages/formats, and retained historical artifacts before real ingestion. Public single-analyst scope is the inferred first release; expanding to private/multi-user data requires separate access and retention contracts.

Dataset selection does not require rewriting the core schema. Corpus-specific metadata stays namespaced; domain-specific normalization belongs in the adapter or optional extraction profile.

## Risks and fallback outcomes

| Risk | Measurement or fallback |
| --- | --- |
| Graph extraction costs more than its retrieval benefit | Keep hybrid baseline; report break-even workload and query categories |
| Entity merges create false paths | Preserve unresolved mentions; compare reviewed versus automatic resolution |
| Timestamps cannot establish real-world change | Offer newly available/learned evidence and explicitly limit world-state claims |
| Tight time filters reduce ANN recall | Exact filtered reference, adaptive scan budget, partitioning/backend comparison |
| Updates invalidate too much derived state | Measure affected fraction and backlog; rebuild selected artifacts or omit summaries |
| Global queries exceed bounded budgets | Separate asynchronous/global experiment with explicit scope and cost; retain interactive local workflow |
| Labels are weak or biased | Human evidence review, disagreement accounting, and separate synthetic/real results |

A measured finding that GraphRAG adds little value at the available scale still satisfies the research objective if the benchmark explains why and supports a simpler design.
