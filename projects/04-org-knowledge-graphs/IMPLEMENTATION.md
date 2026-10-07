# Project 4 · Organization Atlas

A local workbench for reconstructing and reviewing organizational relationships from communications and source directories.

**Status: working first development slice.** Choose a source → measure coverage → preview its graph → build → inspect evidence → correct/undo → export/restore. An animated workflow explains each preparation and analysis stage before opening the explorer. The bundled Meridian Research organization is entirely fictional. Real-data accuracy, calibrated manager probabilities, and unlabeled transfer remain unvalidated. See the [acceptance matrix](docs/acceptance.md) for implemented behavior and remaining gates.

## Run locally

Requirements: Python 3.12+ (excluding 3.14.1), Node.js 20.19+ or 22.12+, and npm. From this project directory in PowerShell:

```powershell
./scripts/setup.ps1
./scripts/start.ps1
```

The setup script installs pinned Python and Node dependencies and builds the interface. Open [Organization Atlas](http://127.0.0.1:8764), then choose **Import a dataset** or **View synthetic dataset**. The synthetic option defaults to 10,000 fictional people; its size is adjustable. If records already exist, **Open saved workspace** opens their explorer directly. With the virtual environment activated, the server command is `python -m orggraph serve --port 8764`.

On macOS/Linux: create `.venv` with `python3 -m venv .venv`, install `requirements-lock.txt` and then `pip install --no-deps -e .` using `.venv/bin/python -m pip`, run `npm --prefix frontend ci` and `npm --prefix frontend run build`, then `.venv/bin/python -m orggraph serve`. The pinned runtime was exercised on Windows; clean-device portability remains to verify.

The server binds to `127.0.0.1`; data persists in `runs/workspace.sqlite3`. Frontend assets are served by the same process. This is a single local analyst workspace; authentication, multiuser permissions, and row-level access controls are not implemented. No model API key, paid inference service, or real corpus is required for the demo.

## Explore the first slice

1. **Choose and inspect a source.** Upload supported records or select a fictional organization size. The six-stage diagram appears before submission, then advances automatically through source inspection, coverage, graph preview, saving, analysis and exploration. Nodes highlight and source connections appear as the explanation unfolds. Inspection measures source bytes, accepted people/entities, messages, assertions, evidence, field coverage and parser quality. The UI starts at 10,000 people; the CLI's fast default remains 72 people, five units, two shared mailboxes, and 404 messages.
2. **Review the plan, then build.** Inspect the measured summary and bounded source graph before dataset records enter SQLite. Green buttons identify the next action: **Continue — build organization chart**, or **Continue with saved chart** for matching analyzed data. The walkthrough stops at this explicit review checkpoint. Pause/resume, 2× speed, skip and replay affect the explanation only; processing has a separate live status. Reduced motion shows results without animation. Switching the active corpus requires explicit replacement; earlier snapshots and reviews remain stored. Package restore requires an empty workspace and preserves its analysis/history. Communication, membership, reporting assertions and isolated evaluation labels remain distinct.
3. **Investigate.** Mouse wheel defaults to **Zoom**; pinch and +/− also navigate departments → reporting branches → people → connections. Continued zoom reveals up to **30 → 80 → 200 people** in the reporting neighborhood while existing positions stay fixed. At that limit, zoom over another person to follow their branch. Click a group to enter; double-click a person for connections. Zooming out or **Up one level** restores the parent view's location and expanded connections. Switch **Chart grouping** to explore inferred communication communities separately. Search by name, email or role to focus any person directly.
4. **Review.** Accept, reject, replace, or undo a manager relationship with a reason. Replacements can have half-open validity intervals. Stale writes are rejected; corrections survive inference refreshes.
5. **Compare and export.** Inspect semantic differences between snapshots. Download a canonical JSON package, lossy CSV primary chart, or Markdown analyst report. Canonical packages restore into an empty workspace with snapshot and review history.

Hover people, groups or reporting lines for position, membership and relationship details, including provenance, review status and explicit uncertainty. Raw model scores are not probabilities. Keyboard focus provides the same information; Escape dismisses the tooltip. Click a reporting line's **i** marker to inspect evidence. Optional **Scroll → Move through chart** provides continuous pan with automatic loading; Ctrl + scroll or pinch still zooms, and Shift + scroll moves sideways.

Preparation leaves the existing corpus unchanged. Refreshing the same browser tab resumes its retained intake using opaque request/job identifiers in session storage; source records and file contents are never stored there. Lost responses are recovered by request key, and interrupted progress reads retry automatically. Previews remain temporary: up to two jobs are retained, one worker runs at a time, and inactive jobs expire after 30 minutes. Server restart discards them; the UI then offers fresh inspection or the saved workspace. Cancelling preparation discards the preview; cancelling is unavailable once saving starts. If analysis fails after records were saved, the source remains available for retry.

Counts describe normalized imported identities, not verified individuals; names may be derived from email addresses. Missing fields and unresolved relationships remain visible. Group member names come from the displayed snapshot, including people outside the current directory page. The baseline uses attributable direct-report wording and communication evidence; coordination or approval language alone does not establish a manager.

Blank time scope means **undated exploration of available evidence**, not a current organizational chart. A dated view excludes undated reporting assertions. A statement date is an observed evidence date, not independent proof of employment dates.

## 10,000-person synthetic corpus

The expanded Meridian corpus contains **10,000 people, 45 formal units, two shared mailboxes and 76,680 messages**. Person counts include two external collaborators; total entities are 10,047. Original people and records retain their IDs. Added staff form an eight-way hierarchy under the existing division directors, with peer traffic, cross-department handoffs, a nonmanager coordinator, shared-mailbox requests and deliberately weak/conflicting/quoted evidence.

Generate a portable input without changing the workspace:

```powershell
.\.venv\Scripts\python.exe -m orggraph demo --people 10000 --output runs/synthetic-10000/corpus.json --generate-only
```

Generate, import and infer into a new workspace:

```powershell
.\.venv\Scripts\python.exe -m orggraph --db runs/meridian-10000.sqlite3 demo --people 10000
./scripts/start.ps1 -Database runs/meridian-10000.sqlite3
```

To switch a populated workspace, use `demo --people 10000 --replace`; earlier snapshots remain in the database, while the active history selector shows the new corpus. Export the earlier corpus first if its portable history is needed. Repeating the same size is idempotent. The browser defaults to 10,000 people; the CLI and legacy `/api/demo` default to the fast 72-person fixture. Counts from 72 to 100,000 are accepted, but the communication-bearing corpus has only been run end to end at 10,000 so far.

There are 9,993 authored fixture manager labels in the separate `labels` collection and only 41 source reporting anchors. Labels are removed before inference. Because language templates and labels share an authored organization, this data tests workflow/scale; it cannot establish real-data accuracy or calibration. [Build measurements](docs/synthetic-10000-results.json) record the actual 10,000-person run.

## Inputs and command line

| Input | Current behavior |
| --- | --- |
| Canonical JSON | Typed entities, messages, assertions, evidence, optional isolated labels; exported package history supported |
| Message CSV/TSV | Standard aliases for sender/from, to/recipients, timestamp/date, body/text, subject, message ID |
| Roster CSV/TSV | IDs, names, emails, aliases, units, roles, manager references, optional validity dates; hierarchy remains attributed source assertions |
| EML, mbox/mbx | Participants, normalized timestamps, body, message IDs, reply references, source locations; attachments are not treated as the sender's authored body |
| Maildir | CLI/path adapter; reads `cur/` and `new/` without modifying the archive |

The browser upload limit is 100 MiB. The CLI has no explicit upload cap, but parsing and inference still use memory; it is not a streaming ingestion engine. PST/OST, enterprise connectors, and general document extraction are not implemented. Missing senders quarantine individual messages; missing body/time fields produce explicit quality limits. Display names never merge identities automatically.

Try the supplied [communications CSV](fixtures/sample-communications.csv) or [roster CSV](fixtures/sample-roster.csv). The communications sample intentionally includes one duplicate, one missing sender, and one missing date. Use separate databases to try independent corpora:

```powershell
.\.venv\Scripts\python.exe -m orggraph --db runs/example.sqlite3 import fixtures/sample-communications.csv
.\.venv\Scripts\python.exe -m orggraph --db runs/example.sqlite3 infer
.\.venv\Scripts\python.exe -m orggraph --db runs/example.sqlite3 status
.\.venv\Scripts\python.exe -m orggraph --db runs/example.sqlite3 export exports/organization.json
.\.venv\Scripts\python.exe -m orggraph --db runs/restored.sqlite3 import exports/organization.json
```

`import PATH` also accepts a Maildir directory. `infer --as-of YYYY-MM-DD` selects a dated view. `export PATH --format csv|report` creates the alternate exports. `--db` precedes the subcommand. Importing a different corpus into a populated workspace requires explicit `--replace`; package restoration always requires an empty workspace. Repeated identical imports and demo loads are idempotent.

## Implementation choices

- **Python/FastAPI + SQLite:** durable imports, jobs, immutable snapshots, indexed paging, and append-only review events.
- **Staged intake:** temporary parsing, exact coverage measurements, and a bounded source graph precede explicit record saving. An automatic explanatory walkthrough follows confirmed stages, with separate processing status and green continuation controls. Opaque recovery handles survive tab refresh; retained request keys prevent duplicate preparation after lost responses. Duplicate inputs reuse saved analysis, and package restoration preserves analyst history.
- **Conservative baseline:** sparse communication candidates, explicit self-report language, separate authority relations, abstention, and deterministic communication communities. Labels and source/analyst hierarchy assertions are excluded from inference inputs.
- **React/TypeScript + semantic SVG zoom:** aggregate departments/communication groups → reporting branches → positions → individual connections. A frame-driven camera, retained scenes and cached scope loading keep movement continuous. Connection neighborhoods expand from 30 to 80 to 200 people without shifting existing positions. Directory metadata streams into a rolling window of 240 cards; at most 200 nearby cards render. Return navigation and responsive resizing preserve the neighborhood; reduced-motion preferences are respected. Reporting branches are navigation groups derived from selected links, not formal team assertions. Sigma/Graphology is not implemented or benchmarked.
- **Explicit uncertainty:** raw ranking scores are not probabilities. Offline calibration utilities require supplied labeled splits and matching applicability scope; they are not automatically applied to the browser's baseline.

Identity merge/split, membership adjudication, arbitrary import column mapping, incremental multi-source reconciliation, dense graph rendering, and real-data research evaluation remain follow-up work. Intake profiling and source previews are implemented; they do not provide automatic identity reconciliation or a streaming parser. These limits are tracked in [acceptance](docs/acceptance.md).

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
.\.venv\Scripts\python.exe scripts/benchmark.py
```

Tests cover read-only intake preparation, coverage accounting, revision-checked builds/retries, package history validation, parser accounting, evidence spans, typed inference, scoped calibration utilities, durable corrections, atomic publication, API behavior, package replay, and bounded layout. The [benchmark report](docs/benchmark-results.json) records hardware, methods, results, and limits; its storage measurements exclude HTTP/browser rendering. Synthetic tests establish software behavior only.

Latest test totals, browser checks, and screenshots are recorded in [verification results](docs/verification.md). Semantic traversal reaches every one of the 10,000 people through both chart groupings. Existing browser evidence covers default wheel zoom, expansion through 29 → 79 → 199 connections, stable positions, expanded-view restoration, person/group/line tooltips, continuous pan, responsive reflow, and evidence inspection.

## Specifications and research

| Document | Purpose |
| --- | --- |
| [Implementation contract / canonical schema](docs/implementation-contract.md) | Current module, entity, assertion, evidence, and HTTP interfaces |
| [Acceptance status](docs/acceptance.md) | C01–C17 evidence, partial completion, remaining gates |
| [Completion specification](docs/completion-spec.md) | Target capabilities and full software/research definition of done |
| [Workflows](docs/workflows.md) | Original agreed workflow design |
| [Architecture](docs/architecture.md) | Research-stage architecture and longer-term contracts |
| [Build plan](docs/build-plan.md) | Remaining corpus, modeling, scaling, and analyst-study work |
| [Inference research](research/inference.md) | Methods and reproduction candidates |
| [Data and evaluation](research/data-and-evaluation.md) | Dataset qualification and evaluation design |
| [Exploration research](research/exploration.md) | Renderer choices and scale-measurement protocol |

The earlier planning documents describe the full target, including unimplemented capabilities. This README and the acceptance matrix describe the current build. Full research completion still requires independent real direct-report labels, a predeclared evaluation, calibrated output within a verified scope, and a separate transfer corpus.
