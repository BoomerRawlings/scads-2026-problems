# Project 4 staged build and research plan

**Planning only.** User has no datasets yet; implementation and an actual example follow workflow finalization. Estimates below describe a later prototype, not scheduled commitments or production readiness.

The [completion specification](completion-spec.md) is the acceptance checklist. All seventeen scenarios are currently unrun. Documentation completion alone does not complete the software or research objectives.

## Decisions to carry into implementation

1. Make direct-report reconstruction the primary task; measure authority, teams, and influence separately.
2. Support organization-specific inputs through adapters and a shared assertion contract.
3. Establish interpretable baselines before adding language models or GNNs.
4. Make unknown managers, evidence, calibration scope, and analyst corrections first-class outputs.
5. Scale by indexed retrieval and bounded views; benchmark total and visible graph sizes separately.
6. Keep initial execution local and reproducible. A graph database, streaming platform, autonomous agent framework, and live enterprise connectors are optional later choices.

## Milestones and exit gates

| Stage | Deliverable | Exit gate | Dependency |
| --- | --- | --- | --- |
| 0 Workflow agreement | Input profiles, relation semantics, review journeys, contracts | Ambiguous/absent data and conflict paths specified | Current research |
| 1 Corpus and parser pilot | Registry, adapters, capability preview, identity audit, resumable jobs, split plan | Obtain usable sources/labels; account for every input; verify failure/retry; audit label meaning and dates | 0; actual source access |
| 2 Inference baseline | Sparse candidates, tabular scorer, abstention, typed evidence, formal/candidate groups, communication indicators | Direct-report evaluation plus separately reported group/comparison outcomes | 1 |
| 3 Explorer vertical slice | Search, virtualized hierarchy, bounded graph, evidence, comparisons, corrections, undo | Read/infer/review/export round trip; scoped decisions preserved; semantic snapshot comparison | Contract from 0; fixtures after workflow agreement |
| 4 Research comparisons | Text/LLM features, selected paper reproduction, optional GNN, calibration | Added complexity improves held-out utility at stated coverage/cost or is rejected | 2; sufficient labels |
| 5 Scale and transfer | Large synthetic topology suite; frozen model on second corpus | Honest performance and transfer report; no target calibration claim without labels | 3–4; second corpus |
| 6 Actual example and case study | Permitted reproducible demonstration, analyst report, evaluation package | Core acceptance scenarios pass; canonical export reimports; evidence/limitations/data rights verified | Prior gates |

Stages 2 and 3 can run in parallel after the contract is fixed. Stage 4 should compare models against the same frozen snapshots. Restricted-data access can delay stages independently of engineering effort.

Rough prototype allowance after workflow agreement: **8–12 person-weeks**, excluding uncertain data access and substantial new annotation. Two builders could divide inference/evaluation and interface/storage, with independent annotation review. This is a scope estimate; re-estimate after the parser/label pilot. Omit the GNN and elaborate document/API adapters if they threaten the complete baseline workflow.

## Experiment matrix

| Experiment | Controlled comparison | Decision evidence |
| --- | --- | --- |
| Candidate policy | Direct contacts; contacts plus bounded neighbors; added unit/evidence candidates | Recall@K for identifiable in-corpus managers, retrieval misses, separately audited outside-corpus/unresolved decisions, cost and activity bias |
| Interpretable baselines | Contact frequency/centrality; logistic regression; tabular trees | Direct-edge precision/recall, manager rank, coverage; same candidates/splits |
| Language contribution | Headers/graph; conventional text cues; evidence-bound LLM features; fused model | Gain at fixed review budget and coverage, evidence validity, cost |
| Known hierarchy completion | Reproduced relational baseline with declared observed training edges | Separate from communication-only and unseen-organization inference |
| GNN contribution | Same features and training budget with/without message passing | Inductive benefit, variance, inference/training cost, leakage audit |
| Structural projection | Independent parent choices; greedy forest; optimal branching prototype | Cycle rate, direct-edge accuracy, abstention, runtime, calibration change |
| Calibration | Raw scores; simple held-out scaling; selected-edge calibration | Brier/log loss, reliability plots, risk–coverage with uncertainty |
| Transfer | Frozen source model; later separately labeled/adapted model | First unlabeled diagnostics, then independent target outcomes if available |
| Analyst utility | Basic tree/table; bounded context plus evidence/uncertainty | Task accuracy/time, correction effort, unjustified confidence |
| Teams and communication comparison | Formal unit data versus candidate communities; reporting context versus observed communication indicators | Membership validity where labeled; analysts distinguish hubs, working groups, and formal managers/units |

Use the [inference review](../research/inference.md) to choose a reproduction with accessible artifacts. Reproducing one direct-report method carefully is more useful than implementing every paper superficially. Partial public code is an access/reconstruction risk, not a guaranteed runnable baseline.

Essential ablations: identities masked/unmasked; signatures/titles included/excluded; text/metadata/graph alone; quoted text removed/retained; known hierarchy available/unavailable; sparse versus dense users; decoder on/off. Predeclare each comparison's generalization claim. Keep real and synthetic results in separate tables.

Keep metric denominators explicit: candidate recall among identifiable in-corpus managers; end-to-end recovery including candidate misses; and open-world decision quality among audited outside-corpus/unresolved cases. A generic unknown option never counts as retrieval of the true manager.

## Acceptance and measurement

**Non-negotiable behavior:** no self-report/cycles in the declared primary projection; unresolved people retained; every proposed edge has a source/model trail; confidence applicability visible; corrections survive model refresh; imports and exports reconcile; snapshots reproduce from stored outputs; no withheld labels in inference features; candidate communities never silently become formal teams; interrupted jobs cannot publish incomplete charts.

**Statistical acceptance:** choose the acceptable error/coverage tradeoff with the eventual analyst after the label pilot, before final testing. Require confidence intervals and a sufficient number of evaluated cases in any claimed confidence band. Do not invent an “accurate enough” percentage before understanding labels and task costs. Report abstentions and missing candidate managers in denominators.

**Scale acceptance:** test 10,000 and 100,000 logical nodes; 1 million is a stretch goal. Keep visible budgets fixed initially at 500 nodes/1,000 edges. Proposed laptop targets: p95 local interaction ≤100 ms, paged expansion ≤500 ms, first useful view ≤2 s, p95 pan/zoom frame time ≤33 ms. Declare hardware, viewport, data density, cold/warm state, and network conditions. These targets are unmeasured; see [benchmark protocol](../research/exploration.md).

**Analyst study:** begin with a small formative pilot, for example 5–8 representative reviewers, to find workflow failures; this cannot establish broad population effects. Tasks: identify a manager; explain uncertainty; find an unassigned employee; correct a dated edge; identify conflict; export a traceable view. Counterbalance interfaces/task variants and record errors as well as time. Size a later comparative study using pilot variance.

**Resource budget:** record messages parsed, eligible people, candidate pairs, feature storage, model calls/tokens, runtime, annotation minutes, and review minutes. Run a bounded text-model pilot before extrapolating to all candidate pairs. Cache results by evidence/model/prompt hashes. Choose model access and hosting only after corpus restrictions and measured need are known.

**Completion order:** workflow ready → software complete → research complete → reportable solution, as defined in the completion specification. No real labels means the inference research gate remains unmet; no target corpus means the transfer gate remains unmet. Optional advanced models and the million-node stretch target do not block a complete baseline solution.

## Plausible research contributions

The strongest candidate is **direct-report inference with evidence, selective prediction, and analyst correction evaluated together across organizations**. Specific hypotheses:

- Language-derived authority evidence improves direct-manager ranking beyond communication structure at a fixed annotation and compute budget.
- Calibrating the displayed, structurally selected edges improves reliability at useful coverage relative to calibrating raw candidate scores alone.
- Explicit unknowns, alternative parents, and evidence improve analyst decisions without making large-hierarchy navigation impractical.

These are testable hypotheses, not established novelty. LLM power inference, graph hierarchy reconstruction, semantic zoom, and uncertainty visualization all have prior work. A negative finding remains useful if the experiment cleanly identifies when a simpler method performs as well.

## Main risks and responses

| Risk | Response |
| --- | --- |
| No usable direct-report labels | Verify archive access first; annotate an auditable subset or limit claims to authority evidence. Do not relabel department/power data as manager truth. |
| Historical labels do not match messages | Restrict to defensible intervals or report temporal scope as unknown; no temporal-performance claim. |
| Famous-corpus memorization or identity leakage | Mask identities, hold out entities/groups, isolate gold documents, compare explicit-title ablations. |
| Missing mailboxes and managers | Open-world candidate/unknown handling; report coverage separately from error. |
| Partial labels mistaken for nonedges | Audit closed local scopes or treat labels as positive/unlabeled; justify sampling assumptions. |
| Source confidence fails on transfer | Mark target confidence unvalidated; retain abstention; obtain independent target audit before accuracy claims. |
| Viewer works only on favorable trees | Test wide/deep/forest/matrix/conflict topologies and dense optional overlays. |
| Analyst feedback contaminates evaluation | Separate review training exports from frozen independently sampled tests. |

## Future handoff package

After implementation: corpus manifest and access instructions; adapter/schema versions; reproducible pipeline entry point; frozen split/evaluation manifests; model and calibration records; bounded-view benchmark results; analyst task protocol; correction/export round trip; and a permitted example. Keep licensed/private source content outside the public repository.
