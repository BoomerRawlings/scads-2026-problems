# Authored pump fixture

Fictional text and authored assertions; no acquired corpus, AI extraction, or real-world validation.
The fixture tests history, publication, evidence, and comparison behavior. It cannot measure retrieval/extraction accuracy or scale.

`manifest.json` gives five ordered batches with source JSONL and assertion JSON-array paths relative to this directory.
Each upsert's original bytes are its exact UTF-8 `text`, without an added newline; raw and normalized hashes therefore match.
Assertion `start`/`end` are Unicode-code-point offsets into that text; assertion text is the exact half-open substring.
`plain-text-v1` is lossless normalization. Fixture source locators are logical `fixture://` references, not public URLs.

| Batch | Source availability | Trusted receipt / publication | Authored interpretation |
| --- | --- | --- | --- |
| `01-initial` | January 5, 2025, 09:00Z | January 5, 10:00 / 10:05Z | A operates Pump P from January 1; no stated end. |
| `02-planned` | January 20, 09:00Z | January 20, 10:00 / 10:05Z | Planned A end and B start February 1. |
| `03-corrected` | February 4, 09:00Z | February 10, 10:00 / 10:05Z | Reported A end/B start February 3; explicitly supersedes the plan. |
| `04-conflicting` | February 12, 09:00Z | February 12, 10:00 / 10:05Z | Independent report names C from February 3; retain B and C. |
| `05-withdrawn` | February 15, 09:00Z | February 15, 10:00 / 10:05Z | Withdraw C's source only; B support survives. |

All clocks are controlled test values. `prepared_at` is 10:01Z, before activation; staged assertions are not yet queryable knowledge.
The corrected report is available February 4, after the February 3 event; it arrives late on February 10.
Source availability, receipt, preparation, publication, and claimed validity remain separate.

`relation_group=pump-p-operator` plus `qualifiers.exclusive=true` states a fixture premise: one actual operator at a time.
This permits a deterministic B/C dispute check; a matching group or similar text alone would not establish contradiction.
Every asserted endpoint label and interval is explicit in the cited sentence. Open ends mean no stated end, not guaranteed persistence.
Passing the planned date does not confirm B's operation; later correction is required to label it reported.
`supersedes` links interpretations; source revision links preserve the underlying document history independently.

`gold.json` is manually specified expected behavior, not computed from engine outputs.
It enumerates expected evidence IDs, modality, dispute status, boundary behavior, and fixed-knowledge world comparisons.
These expectations establish consistency with the authored claims; they are not an independent account of an actual pump.
Additional ingestion/error fixtures are small variations constructed in the tests; they do not expand this corpus's realism.
