# NYC 311 conversational analytics

Part of [SCADS 2026: independent problem-set implementations](../../README.md). Published October 2026.

[Product page and demo](https://boomerrawlings.com/work/scads-2026/02-311-analytics/) · [Research PDF](https://boomerrawlings.com/documents/scads-2026/02-311-analytics.pdf) · [All projects](https://boomerrawlings.com/work/scads-2026/)

## Problem

Turn analytical questions into inspectable filters, geographic queries, grouped statistics, comparisons and recoverable CSV exports.

## Solution

An agent supplies a typed request to one analytical service through JSON CLI or seven MCP tools. The service owns dataset definitions, calculations, provenance and export recovery. Fixture and Elasticsearch adapters share the contract.

Current **v0.7** branch evidence reconciles **2,133,268 real requests** across capture, normalization, frozen Elasticsearch and an independent SQLite reference. Repeated real runs passed analytical-query and CSV-membership checks; comparisons describe the reconciled observed snapshot, not complete citywide reporting. Live Kibana Maps now verify242 points,196 neighborhood groups and a selected three-neighborhood view against filters, five metrics, CSVs and official polygons. The40-question ×3 agent study is executing; model quality and overall acceptance remain unqualified. [Current evidence](docs/acceptance.md) includes retained failures and measurement limits. The public demo and PDF linked above remain the earlier published edition.

## Run locally

Python 3.11+. The included 32-record synthetic fixture runs without Elasticsearch, Docker or a model server. [Runtime guide](docs/runtime.md) covers optional Elasticsearch/Kibana and agent integration.

For a deep Windows checkout, enable Git long-path support for this repository with `git config --local core.longpaths true`; archived evidence filenames include full SHA256 values. For a new checkout, use `git -c core.longpaths=true clone <repository-url>`.

Run from this project directory. Activate `.venv` with `.venv/Scripts/Activate.ps1` on Windows or `source .venv/bin/activate` on macOS/Linux.

```sh
python -m venv .venv
# Activate the environment, then:
python -m pip install -e ".[mcp,geo]"
python -m analytics311 doctor
python -m analytics311 run examples/brooklyn-noise.json
```

[Detailed implementation record](IMPLEMENTATION.md) preserves the technical source overview used by the research paper.

## Inspect the implementation

`analytics311/` contains the service, query compiler, storage adapters and export jobs; `config/` defines catalog and index metadata; `fixtures/` and `examples/` supply reproducible requests; `tests/` verifies behavior.

[Analytical contract](docs/tool-contract.md) · [Recovery design](docs/reliability.md) · [Worked answer](examples/agent-demo/answer.md) · [Verification evidence](docs/acceptance.md)

## Verify

```sh
python -m unittest discover -s tests -v
```

These checks test software behavior and authored examples. Detailed evaluation documents identify the datasets, review provenance and scope of each reported measurement.

## Authorship

Built independently by Boomer Rawlings after the original submission and grading dates, as individual portfolio work rather than a group submission. Inspired by the SCADS 2026 Problem Book; independent of SCADS.
