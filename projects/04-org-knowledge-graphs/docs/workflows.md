# Project 4 workflows

**Current scope: finalize workflows before implementation or an actual example.** No dataset has been selected. The proposed workflow accepts an existing organization and its available evidence; it does not depend on Enron-specific names, folders, or label formats.

“Entity” is interpreted here as an organization, optionally entered through a person, unit, or domain within that organization. A name/domain alone identifies a research scope; it cannot supply an internal reporting chart. Supplied records and authorized sources determine what can be reconstructed.

The [completion specification](completion-spec.md) supplies capability limits, acceptance scenarios, and the distinction between workflow readiness, software completion, and research completion.

## Input modes

| Available input | Supported workflow | Valid output |
| --- | --- | --- |
| Communications plus partial direct-report labels | Train, calibrate, evaluate, infer remaining relationships | Evidence-linked estimates with measured scope |
| Communications without hierarchy labels | Apply frozen model; inspect evidence and uncertainty | Target-unvalidated hypotheses and coverage diagnostics |
| Roster or existing chart without communications | Import, reconcile identities, navigate, correct | Attributed source assertions; no claim of communication-based inference |
| Communications plus roster/chart used as context | Assisted reconstruction | Explicitly separate from communication-only benchmarking |
| Only an organization name/domain | Define entity and source inventory | Intake record and missing-evidence report |

Every input source receives a declared role: **model evidence**, **training labels**, **validation/calibration**, **test labels**, or **analyst reference**. A file cannot quietly serve both prediction evidence and independent evaluation truth.

## Intake and source mapping

The analyst identifies organization scope, relevant dates, known domains/aliases, excluded entities, available formats, and intended use. The system inventories counts and coverage before inference. Record source ownership/terms, processing location, allowed model access, and allowed exports with the corpus manifest.

| Adapter | First implementation scope | Normalized output and caveat |
| --- | --- | --- |
| `.eml`, Maildir, mbox | Initial email adapters | Message IDs, participants, times, thread references, body versions, source locators |
| CSV or JSON communications | Explicit column/field mapping | Same schema; declare absent body, recipients, or threading fields |
| CSV or JSON people/units/chart | Initial reference adapter | Stable IDs, aliases, role/unit membership, typed reporting assertions, validity intervals |
| PST/OST or proprietary export | Later conversion adapter if the selected corpus requires it | Preserve conversion provenance and reconcile source/output counts; do not assume standard-library support |
| Native enterprise API or chat export | Later source-specific adapter | Preserve channel/thread semantics; do not force chat turns into email features |
| Document or web directory | Optional later reference source | Attributed person/role/relationship assertions; publication date is not automatically validity date |

Python's standard library supports several mailbox formats, including mbox and Maildir; `email.parser` handles message parsing. Neither capability performs identity resolution, thread reconstruction, or organizational inference. [Mailbox](https://docs.python.org/3/library/mailbox.html), [email parser](https://docs.python.org/3/library/email.parser.html). RFC 5322 defines relevant message and reply-reference fields; retain originals when normalization fails. [Internet Message Format](https://datatracker.ietf.org/doc/html/rfc5322).

Each adapter emits a common import report: read, accepted, duplicate, quarantined, and unsupported counts; missing-field rates; time coverage; stable source references; and parser version. Account for every input record. Malformed records go to quarantine with reasons, not silent deletion. Re-running the same source/version is idempotent. Never modify the supplied archive.

Before importing, preview mappings, required-field failures, supported analysis modes, and estimated workload. Headers-only data enables behavioral analysis; missing text disables text features. No fitted model disables supervised inference while preserving import/review. Persist progress and checkpoints; failure or cancellation leaves the previous completed snapshot active.

## Identity and evidence preparation

1. Normalize address syntax and timestamps while retaining originals and timezone uncertainty.
2. Propose alias clusters from stable IDs, explicit directories, and corroborating evidence. A shared display name or shared mailbox is insufficient for an automatic person merge.
3. Separate people, shared mailboxes, automated senders, distribution lists, organizational units, and unresolved identities. Domain membership alone does not establish employment.
4. Reconcile message copies; preserve all source locations. Separate newly authored material from quoted/forwarded material while retaining mappings to original text.
5. Reconstruct threads with explicit reply references when available; mark heuristic links. Retain incomplete-conversation status.
6. Produce an auditable identity/coverage report and a review queue. Ambiguous identities can remain unresolved; record how exclusions affect model coverage.

**Exit artifact:** canonical entities and messages, reversible mappings, source hashes, evidence offsets, quality flags, and the set of records eligible for each model.

## Hierarchy inference

Choose a time window and available-evidence profile: headers only; headers plus text; or assisted with existing organizational context. Generate sparse manager candidates, compute interpretable features, and score candidates using a selected versioned model. Store retrieved alternatives and reasons for abstention.

Classify the relation being supported: direct report, indirect authority, team membership, communication, or insufficient evidence. An instruction to complete a task can indicate temporary coordination; the system must not automatically turn it into a manager edge.

Apply the declared structural projection. Retain unresolved and outside-corpus managers. Attach applicable calibration metadata and evidence to every proposed assertion. Generate a snapshot with a consistent model, time, and review revision.

**Exit artifact:** a versioned hypothesis graph, alternatives, unresolved cases, diagnostics, and inference cost. A visually complete chart is not an acceptance criterion.

## Teams and communication comparison

Import formal units/memberships as attributed assertions. Generate candidate communication groups through a separately versioned process. Keep them labeled as inferred groups; cross-team collaboration does not automatically establish a department. Analysts can accept selected dated memberships with evidence, retaining the original candidate group.

Compare reporting position with interaction breadth and cross-unit communication counts for the same stated interval and population. Display source coverage and calculation rules. A communication hub remains a communication hub; its score does not create a reporting relationship. Where suitable labels exist, evaluate team membership separately from direct-manager recovery.

**Exit artifact:** distinguishable formal/inferred groups and a reproducible comparison of reporting structure with observed communication indicators.

## Exploration and bounded querying

The analyst searches a person/unit or enters through the organization overview. Show ancestors, a bounded child list, local context, and an evidence panel. Expanding or zooming changes level of detail and requests only the needed portion of the graph.

Initial queries are structured and inspectable: find person; show direct reports; show ancestry; list unresolved managers; filter by time, relation, score applicability, or review status; compare two snapshots. These cover the required query workflow without an unrestricted language agent. A later natural-language interface may translate into the same bounded query schema, with ambiguous names or relations resolved before execution.

Every view identifies active time, snapshot, relationship layer, and hidden/collapsed counts. Keyboard/tree/table workflows must provide equivalent access to evidence and editing. A restricted source yields an unavailable-evidence state, never an invented explanation.

Distinguish no match from incomplete coverage and unsupported analysis. Evidence panels support text spans, aggregate derivations, source assertions, and analyst references. Preserve the last successful view during loading/failure; show alternatives, conflict, and unresolved reasons without relying on color alone.

**Exit artifact:** a shareable view specification or permitted export containing snapshot, focus, filters, and provenance, not just a screenshot.

## Review and correction

The analyst opens supporting and contradicting evidence, checks competing managers, and accepts, rejects, edits, or leaves the relationship unresolved. An edit records the reason, relevant interval, evidence, and actor reference.

Validate identity, stale revisions, self-reporting, cycles, and the declared primary-reporting rules. Show conflicts and affected relationships before an identity merge or structural change. An accepted event updates the working projection; preserve original model assertions and enable undo through a compensating event. Concurrent conflicting edits require reconciliation.

**Exit artifact:** an append-only correction history and a new snapshot. Acceptance of an unchanged hypothesis preserves its model estimate. Changing its manager, identity, relation, or interval creates a human assertion with null model probability; retain the original prediction separately. Decisions bind to the semantic relationship and time scope so model refresh cannot bypass a rejection using a new assertion ID. Rejection alone leaves the manager unresolved; alternatives remain proposals.

## Evaluation and feedback

Freeze train/development/calibration/test membership before feature fitting. Benchmark candidate retrieval, manager ranking, structured selection, calibration, and abstention independently and end to end. Match dates and relation definitions. Use audited scopes to distinguish false predictions from unobserved truth.

Keep an independent audit sample separate from uncertainty-driven review cases. Export adjudicated corrections for later training; record selection policy and exclude test cases. A retrained model becomes a new version with a comparison report; it does not overwrite analyst corrections.

For transfer, freeze the source model first. Run on the target without labels and label confidence as unvalidated there. If target labels later become available, evaluate frozen zero-shot results before using a separate subset for adaptation. Report adapted results separately.

**Exit artifact:** reproducible evaluation manifest, performance/coverage/cost report, limitations, and optional training export. No target labels means no measured target accuracy.

## Refresh and export

Incremental imports identify new/changed source versions, rerun affected identities/features, and invalidate impacted cached views. Compare model revisions and effective dates; preserve analyst decisions and surface newly conflicting evidence. Source removals must propagate to dependent evidence availability and exports under the applicable retention policy.

Pin import, identity, inference, calibration, review, and projection revisions in every snapshot. Paging and search expansion use that same snapshot. Undated assertions are visibly possible history, excluded from the default dated primary chart and hard temporal constraints until their validity is established.

Export typed entities/assertions, uncertainty scope, review states, effective dates, source references, and snapshot metadata. Allow a primary reporting chart as one export profile and the fuller knowledge graph as another. Do not export unavailable evidence bodies or disguise missing relationships as confirmed roots.

Compare snapshots by semantic relationship and verified identity correspondence. Separate actual relationship differences from changed scores, source availability, model/policy updates, or review decisions; none alone proves a reorganization. Canonical export/reimport must preserve graph meaning. Chart-only exports declare omitted alternatives and fields. Include an analyst report with findings, unknowns, coverage, and traceable evidence.

## Workflow finalization checklist

Before implementation, settle these design choices; dataset-specific values can remain explicit configuration slots:

- Initial adapters: email files plus CSV/JSON roster/chart; source API integrations deferred.
- Relation vocabulary and direction; treatment of positions, primary/matrix reporting, missing managers, and time.
- Evidence permissions and source roles; clear separation of prediction inputs and evaluation labels.
- Shared assertion, confidence, review-event, and snapshot contracts.
- Analyst journeys: search, navigate, inspect, compare teams/communication, correct, undo, inspect semantic changes, and export.
- Run lifecycle: capability preview, progress, quarantine, cancellation, retry, and atomic snapshot publication.
- Evaluation regimes and release gates; quantitative targets fixed after the eventual corpus pilot, before final testing.

Once these workflows are agreed, select a corpus and implement a narrow vertical slice. Build the actual example only after that slice satisfies the declared checks.
