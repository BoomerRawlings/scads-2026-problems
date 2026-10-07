# VOPT evaluation protocol

Status: development protocol; final corpus/labels/configuration are not frozen. All currently inspected manuals and authored queries are development material. Passing engineering fixtures does not pass A1–A12.

## Development evidence

- Regression tests: explicit semantic, lifecycle, isolation, interface and OCR behaviors. These estimate implementation correctness on authored cases, not field accuracy.
- Source leads: selected, agent-inspected real-page claims. Report lead recovery with its exact denominator and scope matching criteria. Leads do not exhaust false positives or missed claims.
- Extraction comparison: identical page records through simple line rules and layout rules; additional actual OCR samples distinguish embedded-text extraction from image recognition. Report page outcome/engine counts.
- Retrieval comparison: identical released/reference records and authored queries through BM25 and ontology TF-IDF. Separate source-reference and actual reviewed-catalog runs. Do not fill missing extracted facts from references and call it automatic performance.
- Scaling: synthetic document/assertion counts, import/query timing, memory and environment. No realistic throughput extrapolation from a single shared host.

## Final test prerequisites

1. Declare supported equipment categories, languages, attributes and scan/layout conditions. Include critical combinations, not merely broad counts.
2. Acquire new rights-qualified families. Keep original editions, derivative scans and related models together. No final document or final query may have been used to debug the implementation.
3. Label all target assertions in sampled regions and document relevance for independently authored queries. Use independent human review and adjudication; preserve provenance and timing.
4. Freeze corpus hashes, split registry, ontology/schema/parser versions, model assets, normalization tolerances and expected query statuses before running.
5. Set final numeric targets with denominators and confidence bounds. Suggested starting gates below require confirmation against the declared scope before freeze; they are not achieved results.

## Proposed quantitative gates

| Measure | Proposed gate | Required reporting |
| --- | --- | --- |
| Full-assertion precision | ≥95% observed; lower 95% interval ≥90% | Every claimed critical slice, false associations and denominator |
| Full-assertion recall | ≥80% | Include missed/failed pages; abstentions count as unrecovered |
| Discovery recall at 10 | ≥90% for answerable supported queries | Source-reference and automatic/reviewed metadata separately |
| Hard-constraint violations | Zero in the final challenge suite | Same model/variant, units, ranges/tolerances, qualifiers and conditions |
| Status correctness | ≥95% | Confusion matrix for match/no-match/unknown/conflict/clarify/unsupported |
| Boundary/lifecycle failures | Zero tested violations | Forbidden fields, source sentinels, atomicity, withdrawal, downgrade and stale approval |
| Offline qualification | Entire frozen workflow succeeds on target with OS networking unavailable | Installation, all assets, OCR, review, export/import, search and recovery |
| Effort | Measured, no predetermined savings claim | Active review/manual-cataloging time plus machine time |

Size each critical slice to support its statistical claim. A handful of source leads cannot meet these gates; increasing totals without independent families does not solve dependence. A slice with insufficient evidence remains unqualified.

## Failure and rerun rules

Preserve the first final result, including failures. Fixes turn those cases into regression data; generalization needs fresh untouched evidence. Do not tune thresholds after seeing final results or exclude failed pages from recall. Report severe errors even when aggregate thresholds pass. Report operator, platform and license/source limitations with the affected claim.

The final PDF chapter follows the verified results and traces each A1–A12 claim to evidence. Development reports may support an honest implementation case study before broad generalization is established, but must preserve those limits.
