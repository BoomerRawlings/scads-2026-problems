# Project 5 GraphRAG Discovery at Scale

**Version 0.3.2.** Local GraphRAG discovery with source provenance, temporal filters, baseline comparisons, and saved investigations. Python/SQLite core, CLI/browser interface, local llama.cpp extraction/embeddings, and exact dense/hybrid retrieval. Installable wheel and source package; Windows installation verified.

User-selected execution policy: **local models; no paid API dependency**. [Live local verification](docs/local-model-validation.md) exercised real extraction and embeddings; the separate five-batch authored fixture checks temporal behavior. Entity resolution, reversible applied reviews, resumable change enumeration, real-data evaluation, and platform certification remain incomplete. This is not the finished research project; see [implementation status](docs/implementation-status.md).

## Run locally

From this project directory, with Python available through `uv`:

```powershell
uv run --no-project python -m graphrag_discovery --db runs/demo.sqlite3 demo --output runs/demo
uv run --no-project python -m graphrag_discovery --db runs/demo.sqlite3 serve --port 8765
uv run --no-project python -m unittest discover -s tests -v
```

Open `http://127.0.0.1:8765` after starting `serve`; stop it with Ctrl+C. The workspace supports search, exact evidence, selectable graph nodes and zoom, three comparison modes, protected notes, staged JSONL imports, and ZIP export. The snapshot strip navigates published knowledge snapshots, not world events. Advanced time/model controls expand on demand; Ctrl/Cmd+K focuses search. Changing corpus or snapshot clears the previous results. Opening an investigation restores its saved evidence run; source facts and analyst notes remain separate. It binds only to loopback. Tests run in a separate terminal or after stopping the server.

Frontend interaction regressions run with `node --test tests/frontend.test.cjs` (Node 20+; development only). No Node runtime, remote fonts, CDN, or paid API is needed to use the installed workspace.

Typing previews matching evidence after a 300 ms pause. Relationships draw in, matching entities highlight, and dotted links connect relationships to their source revisions. Select a node, edge, source, or finding to trace its passage. Preview uses bounded keyword retrieval, including a partial final word; it respects the pinned snapshot and time filters. It makes no model calls or saved runs. Search uses the selected retrieval method and retains results. Escape, clearing the question, or toggling Live preview restores the preceding analysis. Reduced-motion preferences disable animation.

The service uses Python's standard library. The authored demo needs no model server or credentials. Place global `--db` before the command. Use fresh paths for each demo; existing data is never reset. [Installation instructions](docs/installation.md) cover wheel/sdist builds and offline wheel installation without `uv`.

The demo writes `runs/demo/report.md`, `report.json`, and baseline/latest/world-change/withdrawal evidence bundles with file hashes. Its clock is explicitly simulated and its assertions manually authored; passing checks establishes fixture behavior, not extraction accuracy or discovery performance.

Commands include `ingest`, `extract`, `assertions`, `publish`, `index-vectors`, `search`, `evidence`, `baseline`, `compare`, `investigation`, `export`, `serve`, `doctor`, and `backup`. See `--help` for flags. Ordinary ingestion uses service time; it has no historical-clock override. [Local model setup](docs/local-models.md) documents llama.cpp endpoints and model provenance; downloads and the model server are separate from the dependency-free application wheel.

## Target analyst workflow

1. **Connect a corpus:** adapt documents and revisions to a common input contract; preview coverage and missing timestamps.
2. **Establish a baseline:** save an investigation and freeze a snapshot, query/time scope, and either selected findings or an entity-neighborhood rule.
3. **Discover:** ask a question; inspect cited findings, a bounded graph, and unresolved identities or conflicts.
4. **Inspect evidence:** open an edge to see its exact source version, passage, extraction status, and time basis.
5. **Add updates:** ingest new versions, corrections, and withdrawals without destroying history.
6. **Compare:** separate newly learned information, asserted real-world changes, corrections, and unresolved contradictions.
7. **Review and export:** record reversible assessments/corrections; retain originals; save a local evidence bundle with paired citations and coverage.

Example question: “Since my last review, what changed in the dependencies around this organization, and what evidence supports each change?” A changed search ranking alone does not establish a changed relationship.

## Target design

The system uses a small structural schema with text-bearing relationship assertions and optional embeddings, selects eligible evidence before scoring, and supports graph-on/off retrieval comparisons. SQLite currently stores versioned sources and immutable exact-vector artifacts. PostgreSQL/pgvector, ANN, and measured scale remain future work.

| Area | Choice | Reason |
| --- | --- | --- |
| Ingestion | Versioned JSONL contract plus corpus adapters | Dataset can be plugged in later |
| Storage | PostgreSQL with pgvector; original files outside the database | One transactional source of truth for claims, versions, graph adjacency, and vectors |
| Extraction | Replaceable model adapter; source-grounded assertions | Avoid provider dependency and invented relationships |
| Retrieval | Lexical + dense candidates; bounded edge expansion | Establish a useful baseline before expensive graph reasoning |
| Time | Separate event time, source availability, and system knowledge | Distinguish new evidence from actual change |
| Interface | Evidence list, graph neighborhood, timeline, baseline comparison | Support discovery without rendering the entire graph |
| Integration | Python core and JSON CLI first; MCP/HTTP adapters later | Reuse the same service from an agent or website |

This table describes the target architecture; the current implementation uses SQLite, exact cosine plus reciprocal-rank fusion, a local model adapter, and a native browser workspace. Backend alternatives and the distinction from Microsoft's community-summary GraphRAG appear in the research notes. No production performance result is implied.

## Build documents

- [Implementation status](docs/implementation-status.md): current capabilities, checks, limitations, and remaining work.
- [Installation](docs/installation.md): portable distributions, local install verification, and platform support boundaries.
- [Local models](docs/local-models.md) and [live verification](docs/local-model-validation.md): configuration, actual inference evidence, retained failures.
- [Canonical build specification](BUILD_SPEC.md): explicit versus inferred requirements, P0/P1 scope, observable behavior, and completion evidence.
- [Implementation roadmap](ROADMAP.md): ordered work packages, dependencies, acceptance gates.
- [Analyst workflows](docs/analyst-workflows.md): investigations, graph manipulation, two baseline scopes, review, and export.
- [Acceptance specification](docs/acceptance.md): 31 behavioral cases mapped to 12 requirements; see implementation status for covered cases and remaining real-data gates.
- [Architecture](docs/architecture.md): storage, extraction, query execution, scaling, interface.
- [Input and tool contracts](docs/contracts.md): dataset adapter, model boundary, service operations.
- [Temporal workflow](docs/temporal-workflow.md): history, baseline comparisons, corrections, leakage prevention.
- [Methods research](research/methods.md): existing approaches and what to reuse.
- [Data and evaluation](research/data-and-evaluation.md): corpus requirements, experiments, cost accounting.

## Success criteria

Either demonstrate better supported discovery than the strongest non-graph baseline within a measured resource budget, or explain the limiting factors with reproducible experiments. Report failures and useful query categories separately; a compelling graph display is not evidence of retrieval quality.

The temporal fixture, browser workflow, and local-model integration now run. Production model selection, a real corpus, hardware budget, and quality/latency targets remain open. Controlled retrieval comparisons, analyst evaluation, and measured scale remain necessary for final success. PDFs and website publication follow an evaluated demonstration.

Current scope is one analyst, public data, a local CLI/browser service, local inference, and manual updates. Saved hypotheses are notes; monitoring, multi-user permissions, private-data revocation, distributed processing, and richer hypothesis tooling are deferred. Inferred defaults remain distinguishable from the brief's requirements.
