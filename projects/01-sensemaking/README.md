# Organizational sensemaking

Part of [SCADS 2026: independent problem-set implementations](../../README.md). Published October 2026.

[Product page and demo](https://boomerrawlings.com/work/scads-2026/01-sensemaking/) · [Research PDF](https://boomerrawlings.com/documents/scads-2026/01-sensemaking.pdf) · [All projects](https://boomerrawlings.com/work/scads-2026/)

## Problem

Follow connected evidence across records, documents, images and sampled video frames, then produce a cited analysis.

## Solution

The solution separates entity resolution, typed relationship traversal, source retrieval and media inspection into six MCP tools. A local tool-using model selects evidence; saved reports retain citations, conflicts and provenance.

## Run locally

Python 3.11+. Core retrieval uses the standard library; media inspection also uses ffmpeg/ffprobe. The saved-case explorer needs no model. See [local inference setup](docs/local-runtime.md) for the optional llama.cpp path.

Run from this project directory. Activate `.venv` with `.venv/Scripts/Activate.ps1` on Windows or `source .venv/bin/activate` on macOS/Linux.

```sh
python -m venv .venv
# Activate the environment, then:
python -m pip install -r requirements.txt
python sensemaking.py entities
python sensemaking.py investigate riverwatch --max-hops 2
python sensemaking.py evaluate
python scripts/build_showcase.py
python -m http.server 18573 --bind 127.0.0.1 --directory showcase/dist
```

[Detailed implementation record](IMPLEMENTATION.md) preserves the technical source overview used by the research paper.

## Inspect the implementation

`sensemaking.py` handles evidence retrieval; `mcp_server.py` exposes tools; `local_agent.py` runs local investigations; `showcase/` explores recorded cases. `tests/` contains behavioral regression checks.

[Tool contracts](docs/integration.md) · [Local inference evidence](docs/local-validation.md) · [Fixture description](data/README.md) · [Recorded case review](examples/local-riverwatch-guidance-accepted/REVIEW.md)

## Verify

```sh
python -m unittest discover -s tests -v
```

These checks test software behavior and authored examples. Detailed evaluation documents identify the datasets, review provenance and scope of each reported measurement.

## Authorship

Built independently by Boomer Rawlings after the original submission and grading dates, as individual portfolio work rather than a group submission. Inspired by the SCADS 2026 Problem Book; independent of SCADS.
