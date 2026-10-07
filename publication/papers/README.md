# Research papers

Nine research papers by Boomer Rawlings: five implementation working papers (10 pages each, **In progress**) and four research proposals (8 pages each, **Not started**). Recorded results, primary literature and proposed evaluation/roadmaps remain explicitly separate. Projects 6–9 are projected solutions; implementation has not begun and no empirical results are claimed.

- `papers.py`: editable evidence-based core manuscripts.
- `research_extensions.py`: formal definitions, algorithms, related work, proposed evaluation and roadmap.
- `proposed_papers.py` and `build_proposals.py`: four projected solutions and their PDF builder.
- `build_papers.py`: ReportLab builder; run with Python containing `reportlab` and `pypdf`.
- `pdf/`: final PDFs, stable filenames matching project folders.
- `evidence-manifest.json`: PDF and cited local-source hashes, verified primary URLs.
- `proposal-manifest.json`: proposal PDF hashes and primary references.

Run from any directory:

```sh
python publication/papers/build_papers.py
python publication/papers/build_proposals.py
```

During publication, bind hashes to the tested curated checkout, preserving concurrent project work:

```sh
python publication/papers/build_papers.py --source-root tmp/github-release
```

The builder uses Georgia/Arial when available on Windows, with Times/Helvetica fallbacks. Cited current technical READMEs are published as `IMPLEMENTATION.md`; their evidence hashes refer to the original local README bytes. Historical frozen snapshot READMEs keep their original paths.

No new model inference, backend scale benchmark or OCR experiment was performed for publication. All new evaluation designs and roadmaps are labeled prospective. Evidence sources were read and primary literature URLs checked for the October 7, 2026 edition.
