# Implementation status

Version 0.3.2 is an installable local Python/SQLite application with CLI, browser workspace, optional llama.cpp extraction/embeddings, exact vector/hybrid retrieval, and temporal baseline comparisons. User selected local inference without paid APIs. The full target remains in [BUILD_SPEC](../BUILD_SPEC.md); this page distinguishes working software from unfinished research/product requirements.

The 0.3.2 workspace adds live typing previews: finite relationship reveals, matching-node highlights, and dotted source-support links. A separate ephemeral endpoint shares search eligibility rules and uses fixed keyword/prefix limits: 12 findings, 500 scored candidates, one graph hop, 14,400 evidence characters, and a 750 ms projection deadline. No models, saved runs or cursors are created. Browser requests debounce for 300 ms; stale responses cannot replace newer scope or committed results. Pause/Escape/clear restores selections and evidence. Reduced-motion preferences disable animation. These cues illustrate retrieved support, not model reasoning or extraction progress.

## Run and inspect

Run from the project directory with Python 3.12+; the verified environment uses Python 3.14 through `uv`. Runtime and unit tests use the Python standard library. The authored demo needs no model service; real extraction/embeddings require a separately configured local llama.cpp server.

```powershell
uv run --no-project python -m unittest discover -s tests -v
uv run --no-project python -m graphrag_discovery --db runs/demo.sqlite3 demo --output runs/demo
uv run --no-project python -m graphrag_discovery --db runs/demo.sqlite3 serve --port 8765
uv run --no-project python -m graphrag_discovery --help
```

Use new database/output paths for each demo. It refuses to overwrite existing output. Wheel and sdist include fixtures/schemas/static assets. A fresh offline wheel installation outside the checkout passed on Windows; [installation instructions](installation.md) include build and smoke scripts. Windows/macOS/Linux CI is configured, but no macOS/Linux run is claimed. A Python wheel is not a standalone native installer or a bundled model runtime.

The authored demo creates `report.md`, structured `report.json`, a database, and four evidence bundles. It uses simulated time and no network calls. Ordinary ingestion uses service time; real model calls stay on explicitly configured loopback endpoints. The browser serves locally at port 8765 by default.

## Working behavior

| Component | Implemented scope |
| --- | --- |
| Input | Strict UTF-8 JSONL, closed JSON schemas and runtime cross-field validation, lossless English/public plain text, exact UTF-8 hashes, Unicode code-point offsets |
| History | Immutable source versions; explicit revisions/withdrawals; idempotent jobs; staged authored assertions; serialized atomic publication; source-only readiness; cancellation before activation |
| Evidence | Fixed 1,200-character chunks; original version/span/hash; historical access to superseded and withdrawn support; publication cutoffs checked before retrieval |
| Retrieval | Document-local lexical scoring; exact cosine on eligible evidence; reciprocal-rank fusion; assertion-text/vector seeds plus bounded graph expansion; immutable index/profile fingerprints |
| Local inference | llama.cpp adapter; exact quote/endpoint validation; conservative unknown time and mention identities; record/context/config cache; explicit staging before publication; real extraction and embeddings smoke-tested |
| Time | Separate source availability, receipt, and publication; half-open assertion validity; known/open/unknown bounds; reported/planned/negated modality; cutoff-specific extraction coverage |
| Baselines | Immutable saved findings or fixed entity seeds/radius; saved query/snapshot/time scope; comparisons revalidate scoped evidence independently of result ranking |
| Comparison | Source revisions, explicit corrections, new support, late evidence, withdrawal, and fixture conflicts; fixed-knowledge world-state projections with paired evidence |
| Persistence | Frozen search runs and expiring scope-bound pages; optimistic-versioned investigations, notes/view state, baseline links |
| Export | Local evidence bundles with immutable source-span verification and file hashes; both comparison sides and original saved findings; truncation and coverage preserved |
| Workspace | Responsive GraphRAG interface; snapshot history; readable provenance/time; SVG graph with seed selection and zoom; baseline comparison; draft protection; restored saved runs; staged imports; ZIP downloads; serialized actions and stale-response guards; loopback Host/Origin/CSRF protection and typed request validation |
| Distribution | Wheel/sdist, bundled resources, offline installed smoke, additive SQLite schema migration, integrity check and consistent backup |

`graphrag` uses lexical assertion seeds, or hybrid seeds when an explicit vector artifact is supplied. Assertions distinguish `authored-fixture` from `local-model-v1`. Exact quote/label checks establish mechanical grounding, not semantic correctness; generated answers are still absent. Strict local extraction leaves dates unknown unless explicit timezone-aware ISO bounds occur in the quote. Review/identity resolution is still required for richer reasoning.

The [live local verification](local-model-validation.md) records two extracted assertions, preserved reported/planned modality, three 2,048-component vectors, hybrid/graph queries, and canonical-verified exports. An initial embedding HTTP 501 is retained before the successful embedding-server configuration. The decoder weights used for that small smoke are not an optimized embedding model or proof of retrieval quality.

The fictional [pump fixture](../fixtures/pump/README.md) has five batches: initial operator, proposed handover, late correction, conflicting report, withdrawal. Its independently authored [gold file](../fixtures/pump/gold.json) defines eight historical states and two world comparisons. At earlier knowledge time B remains planned; later evidence supports A before February 3 and reported B afterward. B/C coexist while conflicting evidence remains active; withdrawing C changes support without proving a new physical transition.

## Reference limits

- The browser snapshot strip shows up to eight recent published snapshots plus an older selected snapshot; the selector retains access to all. It is not a world-event timeline. Graph zoom uses the bounded returned subset, without full-corpus layout or free-form editing. Unsaved notes are protected by discard/unload prompts, not durable autosave. Browser actions serialize to avoid stale overlapping results; the browser timeout does not cancel an already executing server mutation.

- SQLite was selected without PostgreSQL or Docker. Additive schema upgrades preserve the original tables; backups and integrity checks are implemented. PostgreSQL/pgvector and a general storage-port interface remain planned.
- Per import: at most 1,000 records and 16 MiB serialized source data; at most 5,000 authored assertions. Projections reject more than 20,000 published source events or assertions. These are guardrails, not benchmarked capacity promises. Pending/history storage requires separate operational limits before deployment.
- Scan, candidate, edge, degree, hop, and evidence-character caps bound supported phases. SQLite progress/lock deadlines and Python projection checkpoints enforce query time cooperatively. Local HTTP has a total socket deadline; model loops stop new dispatch after call/time limits. Peak memory, all Python/native work, explicit user query cancellation, and cumulative continuation allowances remain incompletely bounded. Interrupted projections return a typed error rather than a false complete result.
- Exact vectors are capped at 20,000 items, 4,096 dimensions, and four million scalar cells. Imports bind every retained chunk/assertion to its exact text hash. Eligible evidence is filtered before scoring; a missing eligible vector raises an explicit error. A modern index over retained text is labeled cutoff-safe reconstruction, not historical ANN replay. Client profiles contain declared model identity; endpoint aliases cannot attest to loaded weights or server pooling/context.
- Search paging slices an already frozen subset. It neither continues corpus search nor replenishes an execution budget. Comparison has no continuation cursor or ledger-event enumeration; it reports endpoint states within declared candidate scope. Intermediate changes can disappear from a net comparison, so the demo separately compares the conflict and withdrawal snapshots.
- Saved-findings candidates include tracked document lineages, explicit assertion supersession, and exact endpoint/group matches. Neighborhood comparison uses fixed seeds/hops. Neither offers semantic completeness. Source-only comparison of a graph-neighborhood baseline is rejected explicitly.
- Conflict detection is restricted to explicitly exclusive authored relation groups with overlapping known validity intervals. No general contradiction model, source-independence estimator, entity resolution, or probabilistic confidence is implemented. Group labels are authored matching assumptions.
- Unknown validity bounds are excluded from strict event-time support. Historical graph queries against a later graph snapshot can return no claims while reporting pending historical extraction; zero evidence is never a claim that no relationship exists.
- Exports preserve inspectable saved evidence; they do not bundle the full corpus, external model/index artifacts, or prove source truth. Source instructions remain inert text. All input must be public, and this local CLI is not a multi-user access-control boundary.

## Acceptance coverage

The [31 acceptance scenarios](acceptance.md) describe the complete target system. A passing unit suite does **not** mean all 31 are complete. Current tests exercise these portions:

| Scenarios | Tested portion | Remaining acceptance |
| --- | --- | --- |
| A01–A05 | Idempotency, version order, hash/span validation, readiness, atomic activation, exact lookup, local extraction cache/retry, atomic vector artifacts | General durable worker resume, richer parsers, broad crash injection |
| A06–A12 | Evidence-only empty results; late receipt/interpretation; plans; strict intervals; correction; withdrawal; authored B/C conflict | Full precision handling, source-dependence/copy fixture, real extraction and uncertainty quality |
| A13 | None | Versioned entity decisions and reversible projection |
| A14–A17 | Cutoff safety, exact dense ranking and future-vector exclusion, fixed pages, profile/scope/expiry rejection | ANN measurements, summaries/alias leakage, historical model/index replay |
| A18–A19 | Zero scan/edge/text caps, partial flags, job cancellation, SQLite deadline handling, local model call caps and total HTTP deadlines | Complete work accounting, asynchronous query cancellation, resource stress |
| A20–A21 | Reconciliation independent of top-k; paired correction/retraction | Ledger enumeration, resumable comparison, cumulative budgets |
| A22–A24 | Investigation optimistic concurrency; CLI/HTTP/browser journey; graph selection; ZIP hashes/spans | Applied review, full temporal timeline, full target export profiles |
| A25–A27 | Evidence-only answers; fixed-K transitions; real local extraction cache; malformed/timeout response tests; live model smoke | Grounded synthesis, quality evaluation, general event-boundary enumeration |
| A28–A31 | Saved scopes/notes; unsupported modes; no execution of text; source activation and stable pages | Interactive disambiguation/review, model prompt-injection evaluation, active-time cumulative budgets |

Executable cases are in `tests/`, including vector, pipeline, local-model, HTTP, packaging, and dependency-free Node frontend suites. v0.3.0 passed 127 Python tests and 18 frontend checks covering request locks, stale responses, draft retention, restored scope/selection, and import context. Browser verification used the Codex in-app browser: search → exact source → baseline → withdrawal comparison → draft protection → save/reopen with restored evidence. Desktop 1440×1000 and mobile 390×844 layouts were inspected; no horizontal overflow or browser console warnings/errors were recorded. Final artifact checks are recorded in [project state](../.codex/STATE.md). These checks do not constitute a full accessibility or multi-browser certification.

Version 0.3.2 passes 138 Python and 30 frontend checks, including non-persistence, prefix/time scope, bounded preview work, stale-response rejection, IME/debounce, exact committed-view restoration, and no-model typing. Desktop and 390×844 mobile checks exercised preview tracing, source revision links, Search, seed selection and Escape restoration; no horizontal overflow or console warnings/errors. Motion is finite and reduced-motion CSS disables it. These remain fixture/interface checks, not discovery-quality or scale results.

## Next implementation gates

1. Complete operational work accounting and resumable ledger comparison before increasing corpus size.
2. Add reversible evidence/identity review, richer temporal handling, and the timeline interface.
3. Measure lexical/dense/hybrid/graph variants under equivalent scopes and budgets; choose appropriate local embedding/extraction models.
4. Verify macOS/Linux clean installs and model execution, then native distribution/upgrade flows if required; no cross-platform certification is implied by a pure-Python wheel.
5. Qualify a dataset, reserve held-out labels, and evaluate real extraction/discovery quality, update cost, and actual scale. A measured negative result remains valid research.
