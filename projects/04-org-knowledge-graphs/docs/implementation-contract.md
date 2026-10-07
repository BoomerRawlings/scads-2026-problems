# Implementation contract version 1

Implementation authorized. Shared interface for the initial local build; all module outputs are JSON-compatible dictionaries.

## Canonical input

`{schema_version: 1, corpus: {id, name, synthetic, description?}, entities: [], messages: [], assertions: [], evidence: [], labels: []}`.

Entity: `{id, name, type: person|unit|shared_mailbox, email?, aliases: [], role?, unit_id?}`.
Message: `{id, sender: entity_id, to: [entity_id], cc: [], timestamp: ISO-string|null, body: string, subject: string, source_ref: string}`.
Assertion: `{id, subject, relation, object, origin: source|model|analyst, valid_from: ISO-date|null, valid_to: ISO-date|null, reporting_type: primary|matrix, raw_score: number|null, candidate_probability: number|null, selected_probability: number|null, calibration_status: string, evidence_ids: [], review_status: unreviewed|accepted|rejected, reason?: string}`. Time intervals are half-open. Omitted valid_to is open-ended; both dates absent mean undated. Entity IDs are stable. `labels` are held separately and never passed to inference by default.
Evidence: `{id, kind: message_span|communication_aggregate|source_assertion|analyst_reference, source_ref, text?, available: true, message_ids?: [], details?: {}, start?: number, end?: number}`.

Non-reporting relations may set `reporting_type: null`. Primary-manager reviews currently exclude matrix links; those remain readable context. The inference service strips labels, existing assertions, and source evidence before passing entities/messages to the engine.

## Module interfaces

- `ingest.parse_bytes(data: bytes, filename: str, corpus_id: str = "imported") -> dict`: returns `{dataset: canonical, report: {read, accepted, duplicate, quarantined, unsupported, issues: []}}`. JSON canonical input; CSV messages/person roster; EML/mbox; separate `parse_path(path, corpus_id)` supports Maildir. No DB dependency.
- `intake.IntakeManager(store)`: prepares normalized records, exact coverage, and a bounded source graph in temporary memory before an explicit build. One worker and at most two retained jobs; 30-minute idle expiry. Inspection/profile/plan do not write imported records or inference jobs. A server restart discards uncommitted previews. The application may already have created the empty SQLite schema at startup.
- `inference.infer(dataset: dict, *, threshold: float = 0.55, margin: float = 0.08, as_of: str | None = None) -> dict`: returns `{assertions: [], evidence: [], groups: [], metrics: {entity_id: {breadth, sent, received, cross_unit}}, unresolved: {entity_id: reason}, model: {id, name, calibration_status, ...}}`. No labels as input; model scores explicitly uncalibrated. Source assertions remain the service's responsibility. Model assertions use stable semantic IDs and sparse candidate generation. Typed inferred groups never become formal unit memberships automatically.
- Parent owns SQLite persistence, projection, snapshots, review semantics, API, and CLI.

## HTTP API

All endpoints same-origin under `/api`, JSON unless download/upload. Errors: `{detail: string}` with appropriate 400/404/409/413/422. IDs are opaque strings. Graph reads accept a `snapshot` query; intake builds, analysis and review writes supply `base_revision`. Client refreshes workspace after a write. Local server default `127.0.0.1:8764`.

### Staged browser intake

- `POST /intake/synthetic`: optional JSON `{people: 10000}`; strict integer 72–100,000. Returns `202` with an intake job. Generation and profiling run in the background, without importing records.
- `POST /intake/import`: multipart `file`, maximum 100 MiB; supported file adapters above. Returns `202` with an intake job. Malformed, unsupported, and empty sources can become a failed job with parser context; no usable entities means build is unavailable.
- `GET /intake/{id}`: current job and confirmed stage results; `404` if expired or absent.
- `POST /intake/{id}/build`: JSON `{base_revision: integer, replace: false}`. Only reviewed preparation or a retryable failed build is accepted. Returns `202`; stale revisions, missing replacement acknowledgement, or package restore into a populated workspace return `409` before writes. A completed job is idempotent. Existing source-only records retry analysis without duplicate import; identical analyzed inputs reuse their current analysis and corrections.
- `DELETE /intake/{id}`: discard a pre-build preview. Running generation/parsing may finish its current computation, but cannot save cancelled records. Saving/building and completed jobs cannot be cancelled through this endpoint; it does not roll back imports.

Job shape: `{id, mode: synthetic|import, status: profiling|ready_for_review|building|ready|failed|cancelled, source, stages, profile?, plan?, workspace, result?, error?, retryable}`. `source` contains `{name, format, bytes, requested_people?}`; bytes are the uploaded file size, or the measured canonical UTF-8 size for synthetic data after profiling. Unknown size is `null`, never zero. `result` is the published workspace when ready.

Stages are ordered `inspect → profile → plan → database → infer → ready`. Each has `{id, label, status: queued|running|complete|skipped|error, detail, started_at?, finished_at?}`. The UI draws this workflow before submitting the source and animates confirmed state changes. Fast completed stages can be replayed for explanation; replay makes no generation/import/inference requests. Existing analysis and package analysis are marked reused/skipped rather than portrayed as new inference.

`profile` contains exact accepted-record counts (`entities`, `people`, `units`, `shared_mailboxes`, `messages`, `assertions`, `evidence`, `labels`, `data_points`, `communication_links`, `communication_events`), field coverage `{id,label,present,missing,total}`, source assertion counts by relation, parser totals and up to 20 issue summaries, time coverage, canonical bytes, and interpretation notes. `data_points` sums entities/messages/assertions/evidence; evaluation labels are separate and excluded from inference and previews. Communication links count distinct directed sender–recipient pairs; events count unique nonself recipients per message across To/CC. Neither implies reporting authority. Field coverage describes normalized data; inferred names do not establish verified identity.

`plan` contains at most 24 sample nodes and 40 edges with closed endpoints, full entity/source-assertion counts, and a sampling note. Edges preserve relation and `origin`; supplied model assertions remain proposals. This is a bounded source preview, not a predicted organization chart. `workspace` contains `{base_revision, occupied, same_dataset, requires_replacement, can_reuse, package_requires_empty}`. Package histories are structurally validated during preparation, restored only into an empty workspace, and never automatically reinferred. A build failure after record import retains sources and refreshes the revision for an explicit retry.

### Workspace and graph endpoints

- `GET /workspace`: `{corpus, active_snapshot, revision, counts: {entities, people, assertions, selected, unresolved, reviewed, groups}, model, capabilities, snapshots: [{id, created_at, reason, as_of, revision}], jobs: [], coverage}`.
- `POST /demo`: legacy direct endpoint, optional JSON `{people: 72..100000, replace: false, base_revision?: integer}`; no body uses 72. Seeds deterministic fictional people/communications, then infers. Switching a populated corpus requires explicit `replace: true` and its current `base_revision`; earlier snapshots remain stored. Same size idempotent; a source-only snapshot retries a previously failed initial inference. Returns workspace. The new browser entry uses staged intake instead.
- `POST /import`: legacy direct multipart `file`; optional `replace` false (nonempty workspace conflicts unless true), returns `{report, workspace}`. Reimport same input idempotent. This endpoint predates revision-checked intake; the new browser uses the staged endpoints instead.
- `POST /infer`: `{base_revision, threshold?, margin?, as_of?: date|null}`, returns `{workspace, job}`.
- `GET /entities?q=&type=&status=&offset=0&limit=50&snapshot=`: `{items: [{...entity, manager_id, manager_name, status, children_count, metrics}], total, offset, limit, snapshot}`. status `all|unresolved|reviewed|inferred|source`. Search by name/email/role; bounded max 200.
- `GET /entities/{id}?snapshot=`: `{entity, manager: assertion|null, alternatives: [assertion], evidence: [evidence], ancestors: [entity], children: [entity], history: [review], metrics, unresolved_reason, snapshot, revision}`. Assertions include `object_name`, `subject_name`, `selected` and evidence records where practical.
- `GET /graph?focus=&limit=80&snapshot=`: `{nodes: [{id,name,type,role,unit_id,status,depth,manager_id}], edges: [{id,source: manager_id,target: employee_id,origin,review_status,raw_score,calibration_status}], total_nodes, returned_nodes, omitted_nodes, snapshot}`. Hard node budget 200; only valid selected primary relationships in context. Client lays out bounded nodes.
- `GET /chart?lens=formal|inferred&scope=&person=&offset=&limit=&snapshot=`: `{snapshot,total_people,breadcrumbs,nodes,edges,total,offset,limit,scope,lens,description}`. Root returns top-level units or communication groups plus unassigned people; scope IDs are opaque navigation tokens. Nested units roll up unique members; large scopes collapse selected reporting subtrees into presentation branches. Person lookup resolves a containing page and breadcrumbs. Nodes include `kind`, `person_count`, `unresolved_count`, `expandable` and individual position/status/entity ID. Edges retain selected assertion IDs, origin and evidence references. Pages contain at most 200 cards; full stored memberships are used, not the truncated `/groups` response. Snapshot-keyed metadata cache retains at most two indexes.
- `GET /children?parent=&offset=0&limit=50&snapshot=`: same entity page shape. No parent returns primary roots plus unresolved (with distinct status).
- `GET /groups?snapshot=`: `{items: [{id,name,kind: formal|inferred,members: [entity_id],...}], snapshot}`.
- `POST /reviews`: `{base_revision, subject, action: accept|reject|replace|undo, assertion_id?, object?, valid_from?, valid_to?, reason, event_id?, idempotency_key?}` -> `{workspace, event}`. Replace makes human assertion with null model probabilities. Reject blocks semantic relation across refresh. Undo targets event_id.
- `GET /compare?before=&after=`: `{before, after, changes: [{subject,subject_name,kind,before,after}], total}`; semantic relationships not assertion ID comparisons.
- `GET /export?format=json|csv|report&snapshot=`: download canonical JSON package, lossy CSV chart, or Markdown analyst report.
- `GET /health`: `{status:"ok",version}`.

The frontend must render unknowns and errors explicitly, show synthetic and uncalibrated badges, and never format raw scores as confidence percentages. Same dataset serves graph/list/details; no mocked UI data. No external API or paid model requirement.
