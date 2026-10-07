# Semantic discovery for technical manuals

Part of [SCADS 2026: independent problem-set implementations](../../README.md). Published October 2026.

[Product page and demo](https://boomerrawlings.com/work/scads-2026/03-semantic-discovery/) · [Research PDF](https://boomerrawlings.com/documents/scads-2026/03-semantic-discovery.pdf) · [All projects](https://boomerrawlings.com/work/scads-2026/)

## Problem

Find technical documents from equipment and specification needs while controlling which reviewed metadata reaches discovery.

## Solution

VOPT extracts source-linked candidates, records review decisions and exports validated metadata snapshots. A separate discovery installation supports equipment filters, interpreted Boolean/numeric queries, match evidence and request-list export without access to original manuals.

## Run locally

Python 3.11+ with SQLite FTS5. The authored catalog demonstrates source-free discovery. Extraction is optional: install `.[extraction,test]` and follow the [operating guide](RUNBOOK.md) for local OCR, review and release.

Run from this project directory. Activate `.venv` with `.venv/Scripts/Activate.ps1` on Windows or `source .venv/bin/activate` on macOS/Linux.

```sh
python -m venv .venv
# Activate the environment, then:
python -m pip install -e ".[test]"
python -m vopt doctor
python -m vopt import examples/catalog-synthetic.json --catalog runs/demo.sqlite3
python -m vopt serve --catalog runs/demo.sqlite3 --port 8763
```

[Detailed implementation record](IMPLEMENTATION.md) preserves the technical source overview used by the research paper.

## Inspect the implementation

`vopt/` contains ingestion, review, release and search; `vopt/web/` implements the guided browser; `schemas/` specifies catalog interchange; `tests/` uses authored fixtures. Corpus metadata identifies source URLs and hashes; scanned manuals and OCR weights are acquired separately.

[Operating guide](RUNBOOK.md) · [Implementation contracts](docs/implementation-contract.md) · [Extraction evidence](reports/extraction-development.md) · [Retrieval evidence](reports/retrieval-development.md) · [Corpus provenance](data/corpus-manifest.jsonl)

## Verify

```sh
python -m pytest -q
node --test tests/test_ui.cjs tests/test_guide.cjs
```

These checks test software behavior and authored examples. Detailed evaluation documents identify the datasets, review provenance and scope of each reported measurement.

## Authorship

Built independently by Boomer Rawlings after the original submission and grading dates, as individual portfolio work rather than a group submission. Inspired by the SCADS 2026 Problem Book; independent of SCADS.
