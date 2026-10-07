# Publication verification: projects 1-5

Edition: October 7, 2026. Five research working papers, 10 pages each; 14,278 extracted words total.

- All 50 pages rendered with Poppler and visually inspected in full-document contact sheets. Revised method, metric, reproducibility and bibliography pages were rendered and inspected again after review corrections.
- Final layout: navy text, blue headings/citations, gold rules, cream paper; serif body and readable sans-serif tables. No clipped text, overlapping content, unsupported-glyph boxes or broken table rows observed. Headers, footers and page numbering consistent.
- Automated checks: 50 pages, correct page counts/footers, no out-of-bounds words or replacement glyphs, linked references, PDF hashes and every cited local-source hash pass. Detailed receipt: `verification.json`.
- Manuscript mathematical symbols use portable ASCII. Font character coverage checked for ASCII and the zero-width reference wrapping glyph.
- Independent technical critique checked formulas, measured tables, citation metadata and reproduction boundaries. Corrected the implemented edge-list traversal cost; the organizational baseline's zero-record branch and top-eight candidate rule; macro retrieval metric labels; and the distinction between exact vector query cost and embedding/index construction.
- Source evidence bound to the tested curated repository snapshot, not concurrently changing working projects. GraphRAG paper describes version 0.3.2. `IMPLEMENTATION.md` is the preserved technical overview in the published projects; current editorial READMEs are separate.
- Retained historical measurements are clearly differentiated from proposed evaluations and roadmaps. VOPT's exact historical extraction replay explicitly requires its separately retained frozen workspace/research bundle.

Recheck against the same curated source:

```sh
python publication/papers/verify_papers.py --source-root tmp/github-release
```

These publication checks inspect artifacts and claim/source consistency. They do not rerun the underlying research experiments or turn development results into independent accuracy validation.
