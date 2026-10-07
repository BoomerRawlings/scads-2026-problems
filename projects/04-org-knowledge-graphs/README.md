# Organization Atlas

Part of [SCADS 2026: independent problem-set implementations](../../README.md). Published October 2026.

[Product page and demo](https://boomerrawlings.com/work/scads-2026/04-org-knowledge-graphs/) · [Research PDF](https://boomerrawlings.com/documents/scads-2026/04-org-knowledge-graphs.pdf) · [All projects](https://boomerrawlings.com/work/scads-2026/)

## Problem

Inspect organizational evidence, build an explorable relationship graph, review links and compare snapshots.

## Solution

A staged intake profiles source coverage before saving records. Conservative inference keeps observed communications, roster assertions and analyst review distinct. A bounded SVG interface moves from departments to reporting branches, people and their evidence.

## Run locally

Python 3.12+ (except 3.14.1), Node 20.19+ or 22.12+. The fictional organization runs locally. Windows users can use `scripts/setup.ps1` and `scripts/start.ps1`.

Run from this project directory. Activate `.venv` with `.venv/Scripts/Activate.ps1` on Windows or `source .venv/bin/activate` on macOS/Linux.

```sh
python -m venv .venv
# Activate the environment, then:
python -m pip install -e ".[test]"
npm --prefix frontend ci
npm --prefix frontend run build
python -m orggraph --db runs/demo.sqlite3 demo
python -m orggraph --db runs/demo.sqlite3 serve --port 8764
```

[Detailed implementation record](IMPLEMENTATION.md) preserves the technical source overview used by the research paper.

## Inspect the implementation

`orggraph/` contains parsers, intake, inference, durable reviews and API routes; `frontend/` contains the React/TypeScript explorer; `fixtures/` contains synthetic CSV samples; `tests/` covers inference and state transitions.

[Architecture](docs/architecture.md) · [Analyst workflows](docs/workflows.md) · [Input contracts](docs/implementation-contract.md) · [Verification evidence](docs/verification.md)

## Verify

```sh
python -m pytest -q
npm --prefix frontend test
```

These checks test software behavior and authored examples. Detailed evaluation documents identify the datasets, review provenance and scope of each reported measurement.

## Authorship

Built independently by Boomer Rawlings after the original submission and grading dates, as individual portfolio work rather than a group submission. Inspired by the SCADS 2026 Problem Book; independent of SCADS.
