# Publication verification

Verified October 7, 2026, against this curated source snapshot. These checks establish software behavior for the tested fixtures, not research completion, real-world accuracy or production capacity.

| Project | Checks executed | Result |
| --- | --- | --- |
| Sensemaking | `python -m unittest discover -s tests -p test_core.py -q` | 13 passed |
| Sensemaking | `python scripts/build_showcase.py` | 288 files, 13 recorded cases built |
| NYC 311 analytics | `python -m unittest discover -s tests -p test_service.py -q` | 20 passed |
| Semantic discovery | `python -m pytest -q tests/test_search.py tests/test_lifecycle.py tests/test_schema_interchange.py tests/test_guidance.py` | 87 passed |
| Semantic discovery | `node --test tests/test_ui.cjs tests/test_guide.cjs` | 23 passed |
| Semantic discovery | Validate/import authored catalog; query `output power >= 25 kW` | One expected fictional generator match |
| Organization Atlas | `python -m pytest -q tests/test_inference.py tests/test_store.py tests/test_temporal_review.py` | 66 passed |
| Temporal GraphRAG | `python -m unittest discover -s tests -q` | 138 passed |
| Temporal GraphRAG | `node --test tests/frontend.test.cjs` | 30 passed |

Commands run from the relevant project directory with Python 3.12.13; frontend checks used Node 24.18.0. Required test dependencies were installed in isolated environments. The semantic-discovery Node check used `VOPT_PYTHON` to select the available interpreter. Model inference, scale benchmarks, corpus downloads and external services were not required by these checks.

An initial concurrent GraphRAG run produced one timeout-versus-transport error classification failure. Its 14 local-model tests passed in isolation; the subsequent complete 138-test run passed. This is recorded as timing sensitivity under concurrent host load, not omitted from the verification history.

## Publication-specific additions

- Current navigation READMEs; original technical overviews retained as `IMPLEMENTATION.md`.
- A fictional three-document VOPT catalog and deterministic generator, enabling a clean source checkout to exercise discovery without research manuals or private workspaces.
- GraphRAG's frontend preview test helper explicitly enters Explore, matching the application's guide-first startup. Application code is unchanged.
- Four documentation-only research proposals for Projects 6-9, with Not started status, methods, evaluation designs and roadmaps.

## Frozen implementation versions

| Project | Source identity |
| --- | --- |
| Sensemaking | Unversioned source snapshot; exact file hashes in source manifest |
| NYC 311 analytics | 0.6.0 |
| Semantic discovery | 0.1.0 |
| Organization Atlas | 0.1.0 |
| Temporal GraphRAG | 0.3.2 |

Temporal GraphRAG's original technical README was recovered from its preserved 0.3.2 source distribution after concurrent development advanced the live README to 0.4.0. The retained `IMPLEMENTATION.md` is the original 9,065-byte 0.3.2 README, SHA-256 `db4f4ba56d3f9f6f6641f05a672588ec98a57671b79294624a62406e2746dcd3`. The tested publication implementation remains the captured 0.3.2 source snapshot.

The source manifest records portable project-relative paths and SHA-256 hashes. Runtime directories, model weights, external corpus PDFs, generated workload dumps, process logs and device-specific state are excluded. The release retains selected authored fixtures and public-source provenance records required to inspect the research.
