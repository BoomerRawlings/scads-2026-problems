# Project 2 NYC 311 conversational analytics

Runnable Python analytical service with JSON CLI and seven MCP tools. Supports filtered records, geographic queries, grouped statistics, period comparisons, background CSV exports, and Elasticsearch/Kibana adapters. Any compatible tool-using agent can provide the conversation; the service needs no model provider or model API key.

Version **0.6.0** adds normalization byte/disk guards, rejects known oversized exports before launching workers, and retrieves only requested CSV source fields. These changes come from a [scale thought experiment](docs/forecast-v0.6.md); no scale simulation or live engine run was performed for this build. Earlier 0.5 export diagnostics, checkpoint leases and recovery tooling remain. [Reliability and recovery](docs/reliability.md) · [Distribution](docs/distribution.md) · [Capacity](docs/capacity.md) · [Capture](docs/capture.md) · [Live parity](docs/live-parity.md).

**Upgrade:** existing schema-v2 ingestion checkpoints remain compatible with their original input bytes. Schema-v1 requires a new versioned index and checkpoint; do not edit version numbers. New normalization uses portable LF bytes and may produce a different Windows file hash. Saved analyses include the engine version and must be rerun after upgrading before exporting or mapping.

Build one analytical tool service; let an existing agent handle conversation and tool selection. The service owns dataset definitions, query execution, calculations, and reproducible outputs. Agents connect through MCP or a JSON CLI; add HTTP only when a client needs it.

Priority: reusable backend, then demonstration, with rigorous evaluation throughout. Self-host Elasticsearch/Kibana; build the application layer in-house. Resource profiles range from local fixtures to full demonstrations and larger self-hosted clusters. One billion records is a design target; initial acceptance requires measured operation on at least two million real unique records. Fully local model execution follows the initial solve.

- [Build plan](docs/build-plan.md): architecture, milestones, acceptance criteria.
- [Run locally](docs/runtime.md): installation, agent connection, data ingestion, and map setup.
- [Live execution kit](docs/live-runbook.md): capable-host workflow for actual Elastic/Kibana and multi-million-record validation; these gates remain unpassed here.
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

**Current boundary:** local execution and protocol tests run here; live Elasticsearch/Kibana map parity, two-million-record real-data acceptance, and large-cluster capacity remain unverified. The implementation includes those adapters and a deployment path; small local measurements do not establish their capacity.
