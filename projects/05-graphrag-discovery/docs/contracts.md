# Dataset and service contracts

These target contracts let a corpus plug into the workflow without changing graph or query logic. Versioned JSON schemas and a strict plain-text reference adapter now implement a subset; [implementation status](implementation-status.md) documents supported operations and narrower limits. Scope and priorities are in the [build specification](../BUILD_SPEC.md); numeric architecture targets remain proposed profiles, not service guarantees.

## Corpus adapter

An adapter exposes `describe()`, `read_snapshot()`, and optionally `read_changes(cursor)`. It emits UTF-8 JSONL document-version records in bounded batches, plus a manifest. Cursor persistence follows successful ingestion; replaying a batch is idempotent.

| Field | Meaning |
| --- | --- |
| `schema_version`, `corpus_id` | Contract version and stable namespace |
| `event_id` | Stable source lifecycle-event ID, separate from the document/version IDs |
| `document_id`, `version_id` | Stable document identity and immutable source version |
| `source_sha256`, `processing_version` | Original source-byte hash and parser/normalization profile version |
| `operation` | `upsert` or `withdraw`; withdrawal never implies the document's claims were false |
| `text`, `content_sha256` | Normalized text and hash; text required for upsert, omitted for withdrawal |
| `source_uri`, `source_version_ref` | Verifiable source/version locator; local adapters may use logical paths |
| `source_available_at` | Nullable publisher/source availability timestamp with evidence and precision |
| `ingested_at` | Trusted ingestion-service timestamp; adapter-supplied values do not overwrite it |
| `supersedes_version_id` | Optional explicit revision relationship; never infer from arrival order alone |
| `language`, `metadata` | Language and namespaced optional fields; unknown remains explicit |
| `rights_ref`, `access_scope` | Manifest rights reference and retrieval scope; a public-only pilot uses one fixed scope |
| `provenance_map` | Mapping from normalized character offsets to original source locations |

The manifest declares source type, rights/attribution, languages, ordering, update/withdrawal support, timestamp semantics, history completeness, and whether replay is observed or simulated. Static corpora remain usable for retrieval; missing history disables unsupported change claims.

`upsert` requires text, hashes, processing profile, and immutable source/version identity. `withdraw` requires its own event ID, the exact target source version, reason, and available source-event timestamp; it does not require text/hashes. One withdrawal never implicitly removes every revision or corroborating source. Out-of-order events are retained as pending references until their targets resolve. Never advance the successful source cursor past an unaccounted record: durable quarantine is accounted for, silent loss is not.

`validate_corpus` performs bounded preflight before model calls: schema, supported languages/formats, provenance mapping, version links, timestamp coverage, duplicates, and declared capabilities. Return sampled-versus-complete counts and blocking errors. Unknown capabilities remain unknown. Adapter support for updates does not imply complete historical coverage.

**Illustrative record, not an acquired dataset:**

```json
{
  "schema_version": "1",
  "corpus_id": "fixture",
  "event_id": "notice-17-v2-import",
  "document_id": "notice-17",
  "version_id": "v2",
  "source_sha256": "<computed from original source bytes>",
  "processing_version": "plain-text-v1",
  "operation": "upsert",
  "text": "Orion changed suppliers on March 1.",
  "content_sha256": "<computed during normalization>",
  "source_uri": "fixture://notice-17",
  "source_version_ref": "v2",
  "source_available_at": "2026-03-03T10:00:00Z",
  "supersedes_version_id": "v1",
  "language": "en",
  "rights_ref": "fixture-authored",
  "access_scope": "public"
}
```

March 1 comes from the passage and requires year/context interpretation; March 3 is availability. Neither becomes the trusted local ingestion time. Date precision, timezone, and ambiguity belong in temporal metadata. Adapters emit document facts, not model-derived entity identities.

Offsets use Unicode code points in the exact normalized string, half-open `[start,end)`. Citations pin source version and processing version. Changed parsing/normalization creates a new `processing_version` and regenerated offsets, while preserving the original source revision and raw hash. Normalized content is immutable under `(corpus_id, document_id, version_id, processing_version)`. Reject conflicting raw bytes under one source revision or conflicting normalized hashes under one full processing key; quarantine instead of overwriting.

The initial adapter accepts fixed public access scope. Source withdrawal changes current evidence status while preserving history. Access revocation or mandatory erasure is a separate later capability with its own retrieval/cache/history policy; `withdraw` does not implement it. Reject unsupported access scopes explicitly.

## Extraction and embedding adapters

`extract(chunks, schema_version, prompt_version)` returns source-grounded mention spans and assertion candidates with subject/object mentions, relationship text, qualifiers, direction, negation/modality, source spans, and temporal evidence. Invalid output is retried within a cap or quarantined. An empty assertion list is valid.

Extraction cache keys include all semantically used inputs: source/processing identity, content/context hashes, reference date/timezone, language, schema, prompt, model configuration, and any supplied identity-map version. Identical text with different relative-date context must not reuse a resolved date. Keep assertion occurrence, interpretation version, and projected edge identity separate; reprocessing creates lineage, not an invented world event.

`embed(texts, model_version)` returns vectors with declared dimension, distance metric, and text hashes. Never mix incompatible vector spaces. Changing a model creates a separate index generation; rollback remains possible. Keep batch sizes, usage, latency, failures, and provider configuration observable. No provider or API credentials are required to finalize this design.

Staged extraction records `prepared_at`; query-facing assertions receive `recorded_at` and `commit_seq` only at atomic snapshot activation. Durable document `ingested_at` remains separate. Neither a prepared claim nor a staged review decision is historical system knowledge. Temporal fields include `valid_from`, `valid_to`, and explicit `temporal_status`/precision. Distinguish unknown bounds from genuinely open intervals. The [temporal workflow](temporal-workflow.md) governs version projection and conflict handling.

## Snapshot capabilities and coverage

Each immutable manifest declares its source/processing membership, publication time/sequence, policy/model versions, and enabled capabilities: `lexical`, `dense`, `assertions`, `expansion`, `source_compare`, `knowledge_compare`, `world_compare`. Capabilities are prerequisites; particular records may still lack sufficient time evidence for a query.

Each source/processing version records first activation as `visible_from` and `visible_seq`, separate from receipt. Strict system-knowledge reads require receipt and this activation at/before K, even for lexical results or `get_evidence` with no assertions. A new normalization profile has its own activation; do not replace historical processing versions silently. Source availability remains the distinct clock for explicitly tagged published-history reconstruction.

Track extraction outcomes per input unit: `pending`, `succeeded_with_assertions`, `succeeded_empty`, `abstained`, `quarantined`. Report counts and denominators, including rejected/excluded documents. `succeeded_empty` is a completed extraction result, not proof of no real-world relationships. An abstention is unassessed evidence, not successful extraction coverage.

A source-only snapshot can publish after its declared lexical/dense indexes complete. A graph-capable snapshot requires completed required stages for its included inputs. Pending or quarantined work cannot silently become a graph with zero edges. Either keep the previous snapshot, publish source-only capabilities, or create an explicitly scoped manifest with exclusions. Queries using partial graph coverage require `coverage_policy=allow_declared_gaps` and preserve gap counts; `require_complete_processing` rejects gaps. Successful processing is not a guarantee of extraction accuracy or exhaustive claims.

Activation atomically exposes ledger decisions, membership, capability watermarks, and index generation. Cancel/publication races are serialized: if cancel wins, no activation; if activation wins, return `already_published` and do not undo the snapshot. Rollback changes the active pointer to a retained complete generation without altering historical publication records.

## Core service operations

| Operation | Inputs | Output |
| --- | --- | --- |
| `validate_corpus`, `get_corpus_status` | Manifest/sample or corpus ID | Capability/coverage report, active snapshots, stage lag, blocking errors |
| `ingest` | Manifest, document batch, idempotency key | Accepted/rejected counts, cursor, job ID |
| `publish_snapshot` | Completed extraction/index jobs | Immutable snapshot manifest or validation failure |
| `search` | Query, scope, temporal mode, budgets | Ranked assertions/chunks, citations, bounded graph, coverage |
| `expand` | Entity/assertion IDs, same scope, cursor, limits | Eligible adjacent assertions and pagination/truncation state |
| `get_evidence` | Assertion ID or chunk/document-version/span target, snapshot, caller scope | Exact source and processing version/spans; derivation when present |
| `save_baseline` | Query-run ID, baseline kind, selected findings or entity seeds/traversal rule | Baseline ID and frozen scope/configuration |
| `compare` | Baseline ID, target snapshot, mode, budgets, optional cursor | Change candidates, paired evidence, category, uncertainties, coverage/cursor |
| `annotate` | Target ID/version, action, reason, evidence | New review event; conflict on stale version |
| `get_job`, `retry_job`, `cancel_job` | Job ID; retry/cancel additionally check current attempt/version | Stage, progress, failures, committed checkpoints, terminal state |
| `get_snapshot`, `list_snapshots`, `get_run`, `get_baseline`, `list_baselines` | Scoped object ID or paginated corpus listing | Saved manifest/run/baseline with capabilities and availability |
| `save_investigation`, `get_investigation`, `list_investigations` | Versioned question, anchors, notes, run/baseline IDs, view state | Reopenable local investigation; conflict on stale write |
| `apply_review` | Proposal/action, target version, reason, evidence | Staged identity/dispute decision; new snapshot on activation |
| `export_evidence` | Investigation/run/baseline ID, inclusion profile, destination | Local bundle manifest, hashes, included/omitted dependencies |

The CLI implements these core operations first; MCP/HTTP reuse them. No multi-user service or automatic publication is implied. `annotate` records notes/disputes/proposals. `apply_review` applies an explicit merge, split, assertion assessment, interpretation correction, or reversal; ordinary comments never change canonical identity. Reviewed acceptance remains an analyst assessment, not proof of truth. Effective decisions check the expected projection/review-head version; ordinary independent notes may append concurrently.

`scope` includes `corpus_id`, `snapshot_id`, `knowledge_cutoff`, optional `valid_time`, and access scope. Knowledge cutoffs cannot exceed the selected snapshot watermark. A published-history replay uses explicitly simulated visibility and never labels it actual historical system knowledge.

Historical knowledge queries reconstruct eligible ledger state. Literal retrieval replay additionally requires the matching saved index/statistics/configuration; return `replay_unavailable` if absent. A newer index filtered to an old cutoff must be labeled reconstruction and use cutoff-safe candidate generation. Exact answer replay returns the saved answer; rerunning a model may vary even with the same version.

For `knowledge_change` and `source_change`, `compare` enumerates published ledger candidates in stable `(commit_seq,event_id)` order and reconciles baseline members, including support withdrawal and unchanged findings. For `world_state_change`, hold knowledge fixed and enumerate eligible interval/event boundaries plus state projections at both valid times; no newly committed event is required. Planned evidence retains its modality. Source-only snapshots support source comparisons, not world-state assertions.

`baseline_kind=saved_findings` follows selected source/assertion lineages and explicit supporting/challenging links; disconnected new evidence can be missed and coverage states that limit. `entity_neighborhood` freezes seed IDs, hop cap, direction, and status/time policy; compute the eligible neighborhood under that rule at each boundary, including new neighbors. Identity revision is classified separately. Traversal caps can make either side incomplete; do not infer disappearance from a truncated side.

Comparison pages pin their mode-specific snapshot(s), baseline, entity-map/matching policy, mode, filters, deterministic ordering, and logical run budget. Knowledge/source mode pins baseline and target snapshots/cutoffs. World-state mode requires `analysis_snapshot_id`, fixed `knowledge_cutoff=K`, `valid_from_time=V0`, and `valid_to_time=V1`; the analysis snapshot must support K and both state projections. The baseline contributes saved scope/seeds/lineages, not a competing old knowledge boundary. Show its original saved findings separately from the retrospectively evaluated V0 state.

Enumerate candidates before semantic ranking; ranking applies only to the examined set until enumeration completes. Claim completeness only after exhausting the declared candidate scope and reconciling baseline members; this does not establish world truth or complete extraction.

All cursors are opaque service-owned references to snapshot/scope/order/checkpoint, not client-editable offsets. Changed scope yields `cursor_scope_mismatch`; an unavailable saved generation yields `cursor_unavailable`. Ranked search pages reference the saved ordered result list; they do not rerun ANN independently. Comparison/expansion resume stable enumeration without duplicates and report remaining scope as unknown when uncounted.

A page cap divides an already allocated logical-run budget; it does not refill that budget. Repeating a completed page returns its saved result without rerunning models. If the run allocation is exhausted, a new explicitly allocated run may continue from the saved semantic checkpoint; link both runs and retain cumulative usage rather than labeling the second allocation free continuation.

Jobs use `queued`, `running`, `succeeded`, `failed`, or `cancelled`. Retries resume idempotent stages from committed checkpoints, bounded by remaining attempts/time/token allowance. Use one worker initially. Same idempotency key and payload hash returns the existing outcome; changed payload gives `idempotency_conflict`. Restart inspects checkpoints and activation state before retrying. Provider retries can incur additional billing; exactly-once local publication does not imply exactly-once external execution.

Comparison modes: **knowledge change** fixes the event-time scope and compares what is supported at two knowledge boundaries; **world-state change** fixes the knowledge boundary and compares two event times. Return both only as separately labeled results. Revisions/withdrawals remain a third, source-level change category.

Every read returns `request_id`, schema/index/model versions, effective scope, citations, unknowns, warnings, and usage. Usage includes stage times, candidate/expanded counts, model calls/tokens, cache hits, and `truncated`. Retrieval scores are separate from factual confidence. Validate all IDs and limits server-side; an agent cannot relax access/time restrictions.

## Query and result records

Store a query run with `run_id`, original question, validated plan, effective snapshot/cutoffs, ordered evidence IDs, budget profile/consumption, component versions, answer, and status. Baselines accept only server-validated findings/anchors from the selected run. Notes are separate from source-backed findings.

| Record | Required fields and semantics |
| --- | --- |
| Query plan | Retrieval mode `lexical/dense/hybrid/graphrag`; intent; entity seeds; knowledge clock; optional valid point/window; status/coverage policy; declared fallback; budget profile |
| Finding | ID, statement, `source_report/inference`, support/contradiction references, temporal qualification, unresolved questions, review status; unsupported hypotheses remain separate notes |
| Evidence reference | Corpus/document/source/processing version IDs, chunk/offsets, text hash, assertion interpretation if used, evidence role |
| Graph element | Stable projected ID, endpoint mention/identity versions, assertion references, direction, planned/disputed/review status |
| Selection reason | Retrieval channel, rank, optional expansion predecessor/path, active filters; relevance score distinct from factual confidence |
| Change | Baseline/target IDs, category, prior/current support, valid/learned time, matching basis, uncertainty, coverage |
| Usage | Cumulative calls/tokens/retries, elapsed stage time, visited/returned counts, known scan counters, remaining budget, stop reason |

Support/contradiction links express evaluated relationships to a finding. Validating a citation verifies identity/hash/offset/eligibility, not semantic entailment; acceptance uses gold cases and independent human review for real data. Hypotheses without support remain notes and cannot become factual findings through export.

Resolve `snapshot_id=latest` exactly once at run start. Unknown entity/time interpretations return `needs_clarification` with alternatives when outcome-sensitive. No automatic relaxation of temporal, evidence-status, or coverage constraints. A caller-authorized lexical fallback must label the effective mode and missing capability.

## Budget and export semantics

A logical run carries cumulative limits across expansions, comparison pages, retries, and model subcalls. The service controls deadline, concurrency, returned candidates, explicit graph visits/hops, and model-call/token ceilings; reserve requested token allowances before dispatch. Native scan counts can be unknown or approximate; a SQL result limit alone is not a scan-work cap. Enforce statement/request deadlines. Failed or cancelled statements may return no partial rows; retain only completed, validated stage results.

Time limits have distinct meanings: `max_request_wall_ms` bounds each request including service/provider waiting; `max_run_active_ms` accumulates server execution/wait time while requests are active, excluding analyst idle time. Initially allow only one active continuation per run to avoid double spending. `resume_expires_at` governs checkpoint/cursor retention separately; expiration returns a typed error and never replenishes budgets. Saved investigations/baselines persist independently of an expired executable run.

Default evidence export: `manifest.json`, structured findings/changes, source references and required permitted excerpts, query/configuration metadata, usage/coverage, and a human-readable report. Add raw originals only through an explicit inclusion profile consistent with corpus rights. Hash each included file; list external or unavailable dependencies. Local export does not send, share, or publish anything.

Retain saved answers/manifests and pin dependencies used by baselines. Retaining every historical ANN index is optional; report `replay_unavailable` when the exact index/model artifact was not retained, while allowing correctly labeled reconstruction from retained source/interpretation versions. Export reproducibility levels: inspectable citations, replayable evidence selection, or exact saved-answer replay; declare which applies.

## Failure behavior

- Missing required time evidence: return `unsupported_temporal_query` or explicitly include unknown-time evidence; never silently widen the interval.
- Insufficient evidence: return an empty result or abstention with coverage limits.
- Resource cap: return partial results with the reason, or a bounded-job reference if explicitly supported.
- Unpublished/dirty snapshot: reject or use a caller-selected complete snapshot; never silently mix generations.
- Source/model failure: retain the job checkpoint and expose retryable versus terminal errors.
- Stale analyst action: reject the conflicting version; preserve all earlier events.
- Scope/cursor mismatch, unsupported capability, idempotency conflict, or insufficient replay artifacts: return a typed error and the effective known state; never silently restart under different semantics.

Conformance fixtures must cover repeated batches, revisions arriving out of order, unknown dates, source withdrawal, unsupported languages, invalid spans, identity collisions, contradictory assertions, and partial extraction failures.

## Implemented typing preview

`POST /api/preview` accepts `corpus_id`, `query` (2–256 characters, at most 16 terms), and optional `snapshot_id`, `knowledge_cutoff`, `valid_time`, `mode` (`lexical` or `graphrag`). It uses the same loopback/CSRF checks as search. The last unfinished term prefix-matches; trailing whitespace completes the term. Graph mode may add real assertion edges through one expansion hop. Source-only mode rejects event-time filtering.

Returns `operation: preview`, `query`, eligible `items`, pinned `scope`, `usage`, `coverage`, `budget`, `truncated`, and `stop_reasons`. No run ID, pagination cursor, model call, or database write is produced. Fixed limits: 12 findings/edges, 500 scored items, 8 adjacent edges per node, 14,400 evidence characters, and a 750 ms projection deadline. Projection work also consumes the deadline; 500 is not a bound on all history rows examined. Exhausted projection returns `query_budget_exhausted`; candidate/result caps are reported as partial coverage. Caller-supplied budgets, vectors, and model modes are rejected.

The browser debounces 300 ms, invalidates superseded responses, and preserves committed run/selection/evidence state. Dense/hybrid selections receive an explicitly labeled keyword preview; their configured local model runs only on Search. Animation illustrates returned relationships and citations, not new extraction or a model's internal reasoning.
