# Project 2 NYC 311 conversational analytics

Runnable Python analytical service with JSON CLI and seven MCP tools. Supports filtered records, geographic queries, grouped statistics, period comparisons, background CSV exports, and Elasticsearch/Kibana adapters. Any compatible tool-using agent can provide the conversation; the service needs no model provider or model API key.

Version **0.7.0** acquired **2,133,268 real unique NYC 311 requests** from April through October 2025. Repeated real runs reconcile captured, normalized, ingested, frozen Elasticsearch and independent SQLite counts; five analytical families and exact CSV membership checks passed. Live Kibana verification now matches242 rendered points,196 neighborhood trend groups and a selected three-neighborhood view to filters, metrics, CSV membership and the original official polygons. The frozen40-question x3 local-agent study is executing; model quality remains unqualified. Official NTA boundaries qualify comparisons within the reconciled observed snapshot, without claiming complete citywide reporting or transaction isolation. [Verification status](docs/acceptance.md) records measurements, failures and remaining gates. The earlier [0.6 scale thought experiment](docs/forecast-v0.6.md) remains historical. [Reliability and recovery](docs/reliability.md) · [Distribution](docs/distribution.md) · [Capacity](docs/capacity.md) · [Capture](docs/capture.md) · [Live parity](docs/live-parity.md).

**Upgrade:** existing schema-v2 ingestion checkpoints remain compatible with their original input bytes. Schema-v1 requires a new versioned index and checkpoint; do not edit version numbers. New normalization uses portable LF bytes and may produce a different Windows file hash. Saved analyses include the engine version and must be rerun after upgrading before exporting or mapping.

Build one analytical tool service; let an existing agent handle conversation and tool selection. The service owns dataset definitions, query execution, calculations, and reproducible outputs. Agents connect through MCP or a JSON CLI; add HTTP only when a client needs it.

Priority: reusable backend, then demonstration, with rigorous evaluation throughout. Self-host Elasticsearch/Kibana; build the application layer in-house. Resource profiles range from local fixtures to larger self-hosted clusters. The real-corpus and self-hosted CPU-model studies run on a capable Linux CI host; the small fixture and verified offline Windows packages support constrained local use. One billion records remains a design target. Fully offline deployment requires separately staged data, server images, browser runtime and model assets.

- [Build plan](docs/build-plan.md): architecture, milestones, acceptance criteria.
- [Run locally](docs/runtime.md): installation, agent connection, data ingestion, and map setup.
- [Live execution kit](docs/live-runbook.md): capable-host setup; [real-corpus runner](docs/real-acceptance-runner.md) and [agent evaluation](docs/agent-evaluation.md) describe the current measured workflows and remaining gates.
- [Verification status](docs/acceptance.md): measured checks and remaining release gates.
- [Tool contract](docs/tool-contract.md): implemented agent interface and worked request.
- [Portable verification](docs/continuous-integration.md): configured multi-platform builds and opt-in real engine tests; execution status stated separately.
- [Existing implementations](docs/prior-art.md): what to reuse, imitate, and avoid.
- [NYC data research](docs/data-research.md): sources, schema, ingestion, analytical caveats.
- [Elastic research](docs/elastic-research.md): queries, exports, Maps, integration constraints.

## Quick start

From this project directory, using Python 3.11 or newer:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[mcp,geo]"
.venv/Scripts/python.exe -m analytics311 doctor
.venv/Scripts/python.exe -m analytics311 run examples/brooklyn-noise.json
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Linux/macOS: use `.venv/bin/python`. The bundled 32-record fixture works without Elasticsearch, Docker, a GPU, or network access after installation. Its findings are synthetic. Five example requests cover records, closure statistics, proximity, weekly buckets, and neighborhood comparisons.

For a conversational session, attach `.venv/Scripts/python.exe -m analytics311 mcp` to an existing MCP-capable agent (Linux/macOS: `.venv/bin/python`), or let an agent call the JSON CLI. Start with `describe_dataset`; it returns the catalog, coverage, limits, request rules, and valid example specifications.

**Current boundary:** the real-corpus count target, analytical-query parity, exact CSV membership and bounded performance/recovery checks have actual evidence. Rendered Maps verification and the 40-question ×3 agent study are underway; neither has passed acceptance. The latest model development question failed quality. Sampled finite workloads do not establish sustained performance, large-cluster capacity or overall conversational acceptance. See the [current evidence ledger](docs/acceptance.md).
