# Reproduction and data notes

This source snapshot preserves the implementations, dependency metadata, authored fixtures, tests, selected evaluation artifacts and technical documents. Project READMEs are the current publication entry points. Historical research notes retain the evidence context in which measurements were collected.

## Reproduce

Use each project's README from that project directory. The five implemented projects have authored examples. Projects 6-9 are documentation-only research proposals with no runtime or demo. The browser demonstrations on the portfolio explain the implementation; the repository contains the local software. Setup may download declared dependencies. Once prepared, local fixture runs need no paid model provider.

Model inference is an optional separate step in sensemaking and GraphRAG. Local model URLs, identities and setup are documented in those projects; weights and runtime binaries are not included.

## Data provenance

- Sensemaking includes a fictional organization and its authored media. Captured ROR/Wikidata research-organization metadata retains source URLs, revision/capture information and hash manifests. It represents registry assertions at capture time. Historical model runs and reviews retain separate outcomes.
- NYC 311 includes a 32-record fictional fixture and typed example requests. Public 311 captures and generated scale datasets are not distributed here; capture and workload-generation code provide the reproduction route.
- VOPT includes a fictional released catalog plus research manifests with manual source URLs, hashes, attribution and admission decisions. Scanned manuals, rendered pages, OCR/model binaries and private extraction workspaces are not distributed. Use `scripts/acquire_corpus.py` and the documented acquisition/review workflow when reproducing corpus development work. The retained manifest also documents candidate records; acquisition does not itself grant release rights.
- Organization Atlas uses fictional organizations and synthetic communications; person/email examples are authored test data.
- GraphRAG includes an authored five-batch pump-maintenance fixture with explicit simulated dates.

## Interpretation

Test counts establish behavior of the tested source snapshot. Fixture results and development-corpus measurements are scoped to those inputs; they are not population accuracy, human validation, or production-capacity estimates. Original technical evidence is retained so readers can assess those distinctions.

This repository contains no local virtual environments, model weights, captured process logs, databases, device-specific Codex state, generated workload dumps or deployment credentials. Publication READMEs and this note are editorial additions. Original technical READMEs are retained byte-for-byte as IMPLEMENTATION.md. The publication adds a clearly fictional VOPT catalog and its generator, and updates the GraphRAG frontend test helper to enter Explore after the application now starts on its guide. These changes affect the example and test setup; retained implementation source and historical evidence otherwise preserve their original bytes.

## Proposal manuscripts

Projects 6-9 retain the full projected solution in PROPOSAL.md and its dependency-ordered plan in ROADMAP.md. They report no empirical results. The PDFs and editable publication sources are distributed alongside the portfolio.
