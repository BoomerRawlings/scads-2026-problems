# Temporal GraphRAG discovery

Part of [SCADS 2026: independent problem-set implementations](../../README.md). Published October 2026.

[Product page and demo](https://boomerrawlings.com/work/scads-2026/05-graphrag-discovery/) · [Research PDF](https://boomerrawlings.com/documents/scads-2026/05-graphrag-discovery.pdf) · [All projects](https://boomerrawlings.com/work/scads-2026/)

## Problem

Explore source-backed relationships and distinguish newly learned evidence, changed assertions, corrections and withdrawals.

## Solution

Versioned records and source-grounded assertions form immutable knowledge snapshots. Retrieval combines lexical or local dense search with bounded graph expansion; saved investigations and baseline comparison preserve exact evidence and time scope.

## Run locally

Python 3.12+. The authored five-batch demo uses only the standard library and requires no model, network or credentials. [Local model setup](docs/local-models.md) enables optional extraction and embeddings.

Run from this project directory. Activate `.venv` with `.venv/Scripts/Activate.ps1` on Windows or `source .venv/bin/activate` on macOS/Linux.

```sh
python -m venv .venv
# Activate the environment, then:
python -m pip install -e .
python -m graphrag_discovery --db runs/demo.sqlite3 demo --output runs/demo
python -m graphrag_discovery --db runs/demo.sqlite3 serve --port 8765
```

[Detailed implementation record](IMPLEMENTATION.md) preserves the technical source overview used by the research paper.

## Inspect the implementation

`graphrag_discovery/` contains versioned storage, extraction adapters, retrieval and browser service; `static/` contains the interface; `fixtures/pump/` contains authored temporal data; `schemas/` and `tests/` document the contracts.

[Input contracts](docs/contracts.md) · [Architecture](docs/architecture.md) · [Temporal workflow](docs/temporal-workflow.md) · [Local inference evidence](docs/local-model-validation.md) · [Installation](docs/installation.md)

## Verify

```sh
python -m unittest discover -s tests -v
node --test tests/frontend.test.cjs
```

These checks test software behavior and authored examples. Detailed evaluation documents identify the datasets, review provenance and scope of each reported measurement.

## Authorship

Built independently by Boomer Rawlings after the original submission and grading dates, as individual portfolio work rather than a group submission. Inspired by the SCADS 2026 Problem Book; independent of SCADS.
