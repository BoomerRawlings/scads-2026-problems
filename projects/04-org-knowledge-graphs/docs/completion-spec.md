# Project 4 capabilities and completion criteria

This specification closes gaps in the initial plan. It defines the proposed minimum complete solution and the evidence required to call it complete. **These capabilities are specified, not implemented.** Workflow finalization precedes implementation and the actual example, per user direction.

## Minimum complete solution

An analyst can import an existing organization's available records, inspect a reconstructed hierarchy with evidence and explicit unknowns, investigate teams and communication patterns, correct dated relationships, and export a reproducible result. The system supports both partial-label learning and a separately reported unlabeled transfer run.

| Capability | Required behavior | Completion evidence |
| --- | --- | --- |
| Organization intake | Identify organization, source roles, dates, formats, coverage, and available model capabilities | Every record accounted for; missing inputs produce explicit limitations |
| Identity reconciliation | Separate people, aliases, positions, units, shared accounts, and unresolved identities | Reversible merges/splits; affected assertions and decisions identified |
| Reporting inference | Rank direct-manager candidates; retain alternatives and unknowns | Candidate and final-edge evaluation on audited labels; evidence available |
| Team discovery | Import formal units; propose communication groups separately | Candidate groups cannot silently become formal units or memberships |
| Formal and informal comparison | Compare reporting context with named communication measures | Highly connected people do not acquire manager status from a network score |
| Analyst explorer | Search, navigate levels, inspect evidence, filter, compare, edit, undo | Same essential tasks available through keyboard/tree/table access |
| Durable corrections | Preserve scoped decisions across refreshes and competing proposals | Refresh, re-identification, stale edits, and undo verified |
| Report and export | Freeze graph, evidence references, uncertainty scope, omissions, and review history | Canonical export/reimport preserves meaning and provenance |

A usable graph without independent labels is a software result. It is not evidence of accurate or calibrated organization inference.

## Capability discovery and graceful limits

Before a run, show what the inputs support:

- **Roster/chart only:** attributed organizational view and corrections; communication analysis unavailable.
- **Headers only:** behavioral inference and reproducible aggregate evidence; text-based explanations unavailable.
- **Headers and bodies:** add evidence extraction where the chosen model permits it.
- **No compatible fitted model:** import, review, and descriptive communication analysis remain available; supervised inference is unavailable until a model can be supplied or trained.
- **No local labels/calibrator:** a compatible frozen scorer may still run. Missing calibration yields scores without probabilities; missing target labels yields target-unvalidated estimates with their original validation scope. These are separate capability states.
- **Undated relationships:** explicit undated exploration remains available; exclude them from the default dated primary chart.
- **Unlabeled transfer:** run the frozen compatible scorer and show source validation scope; target accuracy remains unknown.

Missing sender/time/body fields are capability flags, not automatic reasons to discard an entire corpus. Validate model input requirements before processing. Distinguish `no_match`, `incomplete_coverage`, `outside_scope`, `evidence_unavailable`, and `unsupported_operation` in query results. An empty result with incomplete coverage cannot establish absence.

## Team and influence workflows

**Formal teams:** import unit hierarchy and memberships as dated source assertions. Infer a membership only when evidence supports that specific person/unit relationship. Record whether the label/name came from a directory, communication text, or analyst judgment.

**Candidate groups:** run one reproducible community baseline over a specified communication window. Retain method, parameters, membership, source coverage, and stability under resampling. Name unsupported groups neutrally. A group is a communication pattern, potentially a project or cross-team working group; formal unit creation is a separate analyst action. Accepting selected members creates new dated membership assertions with evidence, not an automatic relabeling of the whole cluster. Overlapping formal memberships and unassigned people remain valid.

**Formal versus informal comparison:** show reporting position beside interaction breadth and cross-unit communication counts. Define breadth as distinct observed counterparties in the selected window; retain inclusion rules, denominators, treatment of broadcasts/shared accounts, and source coverage. Optional centrality measures are explicitly named. Rank comparisons use a stated population and interval. These are observable communication indicators, not proof of influence, job importance, or supervision.

**Evaluation:** assess imported membership fidelity separately from inferred membership. Compare candidate communities with verified team labels only where coverage and membership semantics match; report cross-team groups and unknowns. Evaluate whether analysts correctly distinguish a communication hub from a manager. Team discovery must not inflate direct-manager accuracy.

## Evidence and explanation behavior

Use a shared evidence envelope with four kinds: `message_span`, `communication_aggregate`, `source_assertion`, and `analyst_reference`. Every item records its source/version, applicable time, identity mapping, and derivation. Text evidence adds offsets and speaker context; aggregate evidence adds the reproducible query/feature definition and covered source references.

The relationship panel answers: **what is proposed, why, what conflicts, what alternative remains, and what is missing?** Show raw signals and their role in scoring separately from evidence that directly states a reporting relationship. A model contribution or high centrality is not causal proof. Repeated quotations from one thread are not presented as independent corroboration.

Use explicit unresolved reasons, including insufficient input, unresolved identity, empty candidate set, weak evidence, close alternatives, conflicting evidence, unknown dates, and model/calibration unavailable. “Manager outside corpus” requires supporting evidence; it cannot be inferred merely from unsuccessful search. Suggest a concrete review action, such as resolving an alias or checking a dated roster.

## Analyst polish and query behavior

Keep one selected entity synchronized across sidebar, graph, and evidence panel. Preserve it through expansion and snapshot changes where identity correspondence is established. Show reporting type, time scope, review status, and confidence applicability using labels as well as color.

Essential queries: manager/direct reports; ancestors; units and memberships; unresolved relationships; supporting/contradicting evidence; alternate managers; formal-versus-communication comparison; semantic differences between snapshots. Each returns the snapshot, time, relation scope, returned/eligible counts, omissions, and an indication of completeness. A bounded ancestry query that stops early is marked truncated, not displayed as a complete chain.

Provide loading, empty, partial, failed, stale, and unavailable-evidence states. Preserve the last successful view on a recoverable failure. Use forms for edits, visible save/conflict feedback, keyboard navigation, persistent focus, and an undo action. Retain rejected assertions in history while excluding them from the accepted working projection.

The review queue offers conflicts, identity issues, unresolved managers, and proposed relationships as explicit categories. Within a category, prioritize visible impact and uncertainty only where meaningful; explain the ordering and allow FIFO. Store queue selection reasons. Keep the independent evaluation sample outside this queue's sampling policy.

## Runs and snapshots

Use local durable job records, not an additional distributed orchestration system. A job records input manifest, configuration, model versions, checkpoints, progress, record counts, and errors. States: queued → running → validating → complete; failed or cancelled runs retain a resumable checkpoint when safe.

Publish a snapshot atomically only after input/output counts reconcile and required invariants pass. An interruption leaves the previous complete snapshot active. Retry with the same input/configuration must not duplicate entities, assertions, or reviews. Changed inputs create a new run. Partial output may be inspected as a labeled diagnostic; it cannot masquerade as the completed snapshot.

Source quarantine can be allowed by a declared policy, with exclusions recorded in the published coverage report. Required-stage failures prevent publication. Cancelling an inference run preserves imports and the last completed graph. Resume uses recorded completed outputs; stochastic model reruns are recorded as new attempts rather than claimed bit-for-bit reproductions.

Snapshot comparisons use semantic relationships and verified identity mappings, not changing assertion IDs. Classify changes as relationship added/removed, manager changed, validity changed, score changed, review changed, or evidence availability changed. Attribute the system cause to new input, model/policy revision, analyst decision, or temporal projection. A system change is not automatically an organizational reorganization.

## Export and report package

The canonical package contains a manifest, entities/aliases, typed assertions, evidence references/derivations, scoped review events, snapshot bindings, and coverage/omission records. Include the dependency closure of exported history: referenced original/superseded assertions, identity revisions, and model/calibrator/policy descriptors with hashes. Preserve null probabilities, unresolved managers, and uncertain dates. An import into an empty compatible workspace must preserve stable identities and semantic content; this is a later acceptance test, not an instruction to ingest data now. Replaying stored decisions does not require retraining; rerunning inference may require separately supplied model artifacts and permitted source data.

An evidence body is optional and governed by its source terms. Export/reimport can preserve a reference without recreating inaccessible content; mark that reference unavailable. Record semantic losses and excluded evidence categories without exposing restricted content. Source withdrawal or changed access can make replay incomplete; the manifest must say so.

A chart/table export is a declared **lossy projection**: state omitted alternatives, relation types, uncertainty fields, and review history. It cannot silently become evaluation truth. An analyst report includes scope/time, data coverage, documented and inferred findings, disagreements, unknowns, corrections, and linked evidence. Each finding remains traceable to assertion and snapshot IDs. Report prose cannot make stronger claims than the underlying graph.

## Acceptance scenarios

These scenarios become executable and analyst checks after implementation begins. All currently **unrun**.

| ID | Scenario | Pass condition |
| --- | --- | --- |
| C01 | Repeat import; malformed message present | No duplicate canonical records; accepted/duplicate/quarantined/unsupported totals reconcile |
| C02 | Headers-only evidence | Prediction cites aggregate derivation; no fabricated text span |
| C03 | Shared name and shared mailbox | Distinct people remain separable; ambiguity visible; merge reversible |
| C04 | Strong authority cue but no direct-report evidence | Relative authority stays separate; direct manager may remain unresolved |
| C05 | Sparse employee or absent manager | Person stays searchable; unresolved/outside-corpus distinction justified |
| C06 | Cross-team communication group | Candidate community creates no formal unit automatically; selected memberships reviewable |
| C07 | Highly connected nonmanager | Communication comparison surfaces the person without changing reporting status |
| C08 | Competing parents or dated reorganization | Time-specific primary projection valid; alternate/unknown-date assertions retained |
| C09 | Analyst changes manager and refreshes model | New human assertion has null model probability; scoped decision survives new assertion IDs |
| C10 | Stale edit or identity split affects prior decision | Explicit conflict/reconciliation; no silent retargeting or loss |
| C11 | Model run interrupted and retried | Last complete snapshot remains active; retry does not duplicate output |
| C12 | Snapshot differs only in scores or IDs | Comparison reports score/system change, not an organizational reorganization |
| C13 | Search and paging at 100,000 logical nodes | Snapshot-consistent results, bounded payload/scene, no duplicate/skipped siblings; latency measured |
| C14 | Keyboard/table user reviews uncertain edge | Search, evidence, correction, and undo work without graph-only interaction |
| C15 | Canonical versus chart-only export | Prediction→correction→undo/refresh history and its dependencies survive reimport; chart losses and unavailable evidence declared |
| C16 | Target has no labels | No target-accuracy or target-calibration claim; validation scope visible |
| C17 | Source is removed after a prediction | Affected evidence availability and exports updated; prior unsupported explanation not shown as current |

## Definition of done

**Workflow ready:** capabilities, input profiles, source roles, relationship/time semantics, recovery, and the above scenarios specified without contradicting one another. The design can be finalized without selecting a real organization.

**Software complete:** required capabilities work through one integrated import→infer→review→export flow; C01–C17 pass where applicable with stated reasons for any nonapplicable checks; 10,000/100,000-node tests and accessibility checks recorded. Performance targets remain those in the [build plan](build-plan.md), measured on declared hardware. No core requirement can be marked nonapplicable solely because it is inconvenient.

**Research complete for the full solution:** at least one communication-based inference baseline evaluated on independent real direct-report labels; source-scope calibrated direct-edge output satisfies predeclared calibration/error/coverage criteria on held-out data, with counts and uncertainty; a separate unlabeled transfer corpus processed with explicit limits; advanced-model comparisons reported if attempted. Set criteria after the pilot and before final testing, as specified in the build plan. Failed criteria remain an honest partial or negative research result, not a fulfilled calibrated-inference requirement. Required label/data access remains an empirical dependency, not something synthetic tests can replace.

**Reportable solution:** software and research evidence, limitations, and a permitted actual example delivered together. A novel method is optional; trustworthy results are required. Million-node browsing, model-driven natural-language queries, live connectors, additional GNN/LLM variants, and collaborative hosting are later extensions unless evidence makes them necessary.
