# Extraction development diagnostics

Authentic scan inputs; selected agent-inspected references. **Not human gold or held-out accuracy.**

Processed 5 admitted manuals, 616 pages. Successful pages: 610. Automatic candidates: 21 layout / 7 line baseline.

| Method | Selected reference field matches | Denominator |
| --- | ---: | ---: |
| Layout | 13 | 17 |
| Line baseline | 4 | 17 |

Denominator: all 17 admitted development leads. Match requires document, source page, exact model, attribute, canonical unit, value/range and rating qualifier. Conditions and component meaning need review; a field match is not automatically a correct full assertion. Unmatched candidates are unlabelled, so precision is unknown. Selected leads cannot measure exhaustive recall. All source families were inspected during development; no generalization claim.

Page success counts describe extraction execution. A separate36dpi decode audit, when present, identifies recovered image-stream errors and downgrades affected pages to unknown; it does not certify OCR text or visual completeness.

| Manual | Pages OK / total | Candidates | Status |
| --- | ---: | ---: | --- |
| tm9-617-m18-1944 | 157 / 158 | 7 | partial |
| tm9-618-m7-1943 | 177 / 178 | 4 | partial |
| tm9-1752-homelite-1942 | 49 / 51 | 5 | partial |
| tm9-834-workshop-1944 | 110 / 110 | 5 | complete |
| tm9-867-hand-tools-1945 | 117 / 119 | 0 | partial |

## Fresh local OCR on actual scan pages

The original PDF pages were rasterized in memory; no synthetic degradation or replacement source. Python network connection functions were blocked. This verifies that local assets ran without Python network calls, not an OS firewall boundary. The same document/model-category metadata is used for saved-page and fresh-OCR extraction; cached OCR output is reused when its source/page/engine identity matches.

| Manual/page | Status | Candidates | Selected field matches |
| --- | --- | ---: | ---: |
| tm9-617-m18-1944 / 12 | ok | 5 | 2 / 3 |
| tm9-1752-homelite-1942 / 3 | ok | 5 | 4 / 4 |
| tm9-834-workshop-1944 / 93 | ok | 1 | 0 / 3 |

## Preserved whole-output development audits

These audits inspect every emitted candidate in a specific frozen M18 record, using original source pixels. They remain agent development audits; the rubric was applied after inspecting candidates.
- `data/corpus/m18-candidate-audit-v1.json`: {'emitted': 17, 'numeric_transcriptions_supported': 17, 'supported': 5, 'needs_scope': 9, 'wrong_entity': 3, 'redundant_supported_observations': 2, 'distinct_supported_claims': 3}; pinned record `95004745f4b71004d335738bb9c842d74f42800561bd373d864a26338f3bd77d`. 5/17 is agent-audited full-scope precision for this development version only.17/17 numeric transcription is not factual extraction precision. Three wrong-entity claims are definite; nine further claims require missing configuration/condition repair. No human gold or held-out/generalized accuracy claim.
- `data/corpus/m18-candidate-audit-v2.json`: {'emitted': 7, 'supported': 7, 'needs_scope': 0, 'wrong_entity': 0}; pinned record `827a83cd2a5c3d8850eba13f407331343ce1ef9f4fc6ccc3f63f23513718d67e`. 7/7 is source-inspected agent development precision for emitted claims on this repaired manual only, not human gold or generalization. Ten former observations are no longer emitted; no recall estimate. Original 5/17 result remains preserved.

## Remaining extraction roadblocks

- Sparse OCR, damaged glyphs and split model identifiers can change applicability; unresolved identity must abstain.
- Prose specifications with implicit subjects and component-to-assembly relationships require stronger contextual parsing and reviewed labels.
- Electrical/mechanical roles, discrete ratings, governed/rated/no-load conditions, unit assumptions and revision scope need source review.
- Field/lead matches omit full condition correctness. Build exhaustive human annotations before reporting precision/recall or declaring A3/A10 complete.
- Broad authentic low-quality, multi-model, multilingual and unseen-layout coverage remains unproven.

- Rendering has a24M-pixel cap and failed pages have a3-attempt automatic resume budget. No hard per-page timeout or isolated process/memory sandbox exists; a hung native/OCR call needs operator interruption.

Reproduce from frozen workspace: `.venv/Scripts/python.exe scripts/evaluate_extraction.py --skip-ingest`. A fresh rebuild requires ingestion, followed by explicit source-bound Homelite page 3 OCR (`python -m vopt reocr --workspace runs/real-workspace --doc-id tm9-1752-homelite-1942 --pages 3`), then category evidence and decoder audit before freezing reviews (`.venv/Scripts/python.exe scripts/evaluate_extraction.py --skip-ingest --reextract --audit-decoders --category-evidence data/corpus/model-category-evidence.json`). Detailed hashes, page failures, engine counts and per-lead results: `reports/extraction-development.json`.
