# Analyst workflows

Status: proposed defaults inferred from the discovery brief; design only. First scope: one analyst, one public corpus, manual updates. No runtime or dataset is supplied here.
The [contracts](contracts.md) govern identifiers and service behavior; the [temporal workflow](temporal-workflow.md) governs time. These workflows add product behavior without claiming tested usability.

## Investigation lifecycle

An investigation keeps a question, scope, evidence, hypotheses, and conclusions together across sessions. Proposed lifecycle: active → concluded → reopened; concluding records a decision and leaves the evidence history intact.

| Saved object | Minimum persistent content |
| --- | --- |
| Investigation | Stable ID/version, title, question, corpus, current selected snapshot/time scope, status, notes |
| Query run | Question, effective scope, selected entity IDs, request/result references, coverage, resource limits, citations |
| Hypothesis note | P0: analyst-authored statement with linked evidence and qualifications. P1: dedicated disposition, reasoning, and review-time fields. |
| Finding | Statement, originating run/snapshot, exact assertion/chunk citations, qualifications, analyst review disposition |
| View | Selected entities, filters, hidden items, pinned positions; separate from the evidence and baseline scope |
| Baseline reference | Immutable baseline ID, readable label, comparison scope, selected findings or seed entities |

P1 hypothesis dispositions: open, supported within scope, challenged, inconclusive. A reviewer supplies the reason and evidence; a model can suggest a disposition but cannot silently finalize it. P0 captures these qualifications in ordinary notes. Analyst notes/hypotheses never become source evidence, independent corroboration, or automatic training updates.
Reopening restores the saved snapshot and scope, shows whether newer snapshots exist, and lets the analyst explicitly move to one. Saved findings and baselines retain their original references.
Persistence uses `save_investigation`, `get_investigation`, and `list_investigations`; scope/capability checks use `get_corpus_status`. Manual reruns create new query runs without automatic mutation of saved conclusions.
Acceptance example: save “Orion may depend on one supplier,” close and reopen the investigation; its hypothesis, citations, hidden nodes, and original snapshot remain distinct and recoverable.

## Query, inspect, and explore

1. Choose a complete corpus snapshot; see document/history/time coverage before asking a temporal question.
2. Ask a question; display the interpreted scope and time meaning with results. Changes to these controls create a new run rather than modifying a saved answer.
3. Read cited findings and source passages first. A bounded graph shows entities and assertions contributing to the evidence; select a finding to highlight its support.
4. Select an entity or assertion to inspect its source mentions, relationship wording, direction, qualifiers, modality, dates, and review state. Evidence details stay accessible without a graph.
5. Expand a selected entity under the same snapshot/time filters; show added items and omitted counts where known. Keep the question and selected evidence visible.
6. Pin useful findings, add supporting/challenging evidence to a hypothesis, and record uncertainty. Saving a finding does not certify it as true.

Entity disambiguation is a local query choice: show candidates with distinct IDs, contextual passages, corpus labels, and applicable dates. Selecting a candidate scopes this investigation/run; it does not merge records globally.
When identity remains unresolved, allow source-mention search and inspection. Canonical merge/split belongs to a separate review action with evidence and a version check.
Acceptance example: “Orion” matches a vessel and a company; choosing the company excludes vessel-only expansion, while both identities remain unchanged in storage.

## Manipulate the graph without rewriting evidence

| Action | Effect |
| --- | --- |
| Drag, pin, hide, collapse, filter | Change the saved view only; do not withdraw assertions or narrow an existing baseline silently. |
| Expand or select a path | Retrieve bounded eligible evidence; a path is a connection, not proof of causality. |
| Attach a note or hypothesized relationship | Add an analyst hypothesis referencing entities/evidence; keep it visually and semantically separate from extracted assertions. |
| Dispute an assertion | Append a review event with reason/evidence; preserve the original assertion and source passage. |
| Correct identity or temporal interpretation | `annotate` records a proposal; `apply_review` applies a reversible decision against an exact version, through normal validation/publication. |
| Edit extracted wording | Create a linked interpretation revision; never overwrite the original wording or source. |

Pending corrections appear in a separate review overlay with `submitted_at`; they do not alter saved snapshot evidence. Effective query-facing decisions receive `recorded_at` only at publication. Historical queries exclude later review events. Query behavior changes only in a newly published snapshot; the analyst chooses when to switch. A stale target rejects the action with current-version context and preserves the draft reason.
Acceptance example: hiding a disputed edge removes it from the canvas, but it remains in evidence, the dispute record, and previously saved baseline comparisons.

## Two baseline scopes; separate time modes

Saving a baseline freezes snapshot, query, effective filters, temporal mode, model/index/resolution configuration, evidence references, and coverage. `baseline_kind` controls scope independently of `comparison_mode`:

| Scope | Tracks | Does not imply |
| --- | --- | --- |
| Saved findings (`saved_findings`) | Selected conclusions plus their supporting assertion/source revision lineages; new support, challenges, corrections, and withdrawals | Discovery of every new relationship outside those findings |
| Selected-entity neighborhood (`entity_neighborhood`) | Fixed seed identities and eligible relationships within a saved radius/filter policy; proposed default one hop, configurable within caps | Whole-corpus discovery or completeness when enumeration is truncated |

Neighborhood comparison evaluates the saved policy at both boundaries and includes newly eligible neighbors, rather than freezing the old canvas. Scan the union of relevant baseline/target neighborhoods and their ledger events; retain removed/superseded relationships for explanation. Identity revisions remain separately labeled.
Hiding a node does not exclude it from this scope. Changing seeds, radius, or filters creates a new baseline; it cannot silently redefine the old comparison. Saved-findings baselines can use chunk citations before extraction; entity-neighborhood scope requires graph capability.
Acceptance example: baseline selects Orion at one hop; a later source adds a new supplier. Neighborhood mode includes that candidate; saved-findings mode changes only if the new evidence bears on a tracked conclusion.

`knowledge_change` holds the event window fixed across two knowledge boundaries; `world_state_change` holds one knowledge boundary fixed across two event times; `source_change` compares source revisions/withdrawals. Make this distinction readable beside the comparison.
World-state comparison evaluates eligible validity intervals at the two event-time boundaries under the same knowledge cutoff; commit deltas alone cannot reveal a transition already known at the baseline.
Both state projections use one compatible analysis snapshot. The baseline contributes scope; its original saved findings remain visible separately from the retrospective earlier state evaluated with later knowledge.
Source availability, first ingestion, and claimed event dates remain separate. Show “date unknown” or “planned” rather than implying an actual transition. A scheduled date passing does not confirm an event.

## Change review and paired evidence

Each change card states the affected finding/entities, category, claim/event date when supported, first-learned date, scope, coverage, and review disposition. Pair the earlier and later interpretations with exact source versions/passages; either side may explicitly lack evidence.
Categories follow the temporal contract: newly observed event, new support, late evidence, correction, retraction, unresolved conflict, identity revision, processing discovery, and coverage change. Multiple categories may apply.
Keep unchanged support accessible beside changes. “No longer retrieved,” “left this neighborhood,” “source withdrawn,” and “relationship ended” are different outcomes; only the last requires evidence of an actual end.
Ranked change candidates remain candidates until reviewed. Proposed review dispositions: unreviewed, relevant, dismissed with reason, unresolved. Dismissal hides a card from the default review queue, preserves it in history, and cannot suppress later supporting/challenging evidence automatically.
Acceptance example: February evidence corrects a January event date. The card pairs both passages, labels late evidence/correction, and does not present February receipt as the event date.
Acceptance example: a competing source disputes the corrected account. Both claims remain visible; accepting one as the analyst's working interpretation does not remove the other source.

## Review and exports

Conclude an investigation with selected findings, qualified hypothesis notes, unresolved questions, and coverage limitations. Structured hypothesis dispositions are P1. Require no artificial “all resolved” condition; an inconclusive outcome is valid.
`export_evidence` produces a local bundle: a readable Markdown report and a JSON evidence manifest. Include investigation/baseline IDs, snapshots and temporal meanings, selected findings, paired citations, review reasons, unknowns, partial-result flags, and provenance/configuration references. Sharing/publication is deferred.
Export source excerpts with exact version/location references; keep full-corpus distribution outside the default export. Preserve source attribution/rights requirements. Graph selection/layout may accompany the manifest but cannot replace citations.
A reopened export resolves its saved evidence versions; regeneration against newer evidence is a new report. Missing historical artifacts are labeled unavailable, never silently substituted.
Acceptance example: export a partial comparison with an unresolved conflict; both qualifications and both source references appear in the report and manifest. PDF/site packaging remains a later milestone.

## Honest states and recovery

| State | Required analyst-facing behavior |
| --- | --- |
| No corpus / graph unavailable | Explain required input or pending extraction; source search remains available where indexed. Never display invented findings. |
| No eligible results | Say no supported result was found within the shown scope; offer explicit query/scope changes without widening automatically. |
| Ambiguous identity / time | Show alternatives or unknown-time evidence separately; keep strict temporal results strict. |
| Partial search/comparison | Show the reached limit, examined coverage where known, and resumable cursor when supported; do not say “all changes.” |
| Update running / failed | Keep the selected complete snapshot queryable; show pending progress/failure and explicit retry or cancellation. |
| Stale derived artifact | Rebuild or omit it; explain reduced capability. A saved historical snapshot is historical, not dirty merely because newer data exists. |
| Conflicting evidence | Present competing attributed statements and temporal overlap; avoid a falsely settled answer or confidence percentage. |
| Missing historical evidence | Flag the affected citation/report; do not replace it with current text or count the finding as verified. |

Inspecting evidence does not spend a run's active execution-time allowance while the analyst is idle. Show cursor expiry separately; continuing an exhausted allocation requires a new explicitly budgeted run.

## First useful demonstration

Use future authored fixtures only: a company with two similar names, an existing supplier, a planned supplier change, a late correction, and an independent conflicting report. The fixtures demonstrate behavior, not discovery accuracy on real data.

1. Open a corpus snapshot, create an investigation, disambiguate the company, query its dependencies, and inspect an exact cited passage.
2. Save a hypothesis and one reviewed finding; manipulate the graph view; create both baseline scopes with clearly different coverage.
3. Ingest the fixture updates through the normal job/snapshot path; confirm the original view stays pinned while processing.
4. Select the new snapshot; compare both baselines; inspect old/new evidence, late-arrival/correction labels, a new neighbor, and the unresolved conflict.
5. Review a candidate, record an inconclusive hypothesis where warranted, export the report/manifest, and reopen the original baseline without altered evidence.
Pass when every result has inspectable evidence, every scope/time distinction survives save/reopen/export, graph edits cannot change source facts, and partial/conflict states remain visible. Canonical acceptance gates remain in the roadmap and build specification.
