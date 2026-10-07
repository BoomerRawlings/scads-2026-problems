# Retrieval development evaluation

Agent-authored queries and partial agent/source-inspected references. No human accuracy, untouched generalization, or labor-savings claim.

Both rankers execute the same hard-predicate compiler. The semantic comparator is ontology-normalized TF-IDF, not pretrained embeddings. Similar scores here do not establish semantic-model superiority.

The table below excludes synthetic diagnostics; it covers the 33 source-reference query cases only.

| Dataset | Profile | Ranker | Known positive queries | Known scopes | Recall@10 | MRR@10 | Plan statuses | Numeric violations / returned scopes checked |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| private_agent_reference | values | lexical | 17 | 22 | 1.000 | 1.000 | 33/33 | 0/10 |
| private_agent_reference | values | semantic | 17 | 22 | 1.000 | 1.000 | 33/33 | 0/10 |
| agent_reviewed_extraction | values | lexical | 17 | 22 | 0.912 | 0.941 | 33/33 | 0/9 |
| agent_reviewed_extraction | values | semantic | 17 | 22 | 0.912 | 0.941 | 33/33 | 0/9 |
| private_agent_reference | coverage | lexical | 7 | 12 | 1.000 | 1.000 | 33/33 | 0/0 |
| private_agent_reference | coverage | semantic | 7 | 12 | 1.000 | 1.000 | 33/33 | 0/0 |
| agent_reviewed_extraction | coverage | lexical | 7 | 12 | 0.929 | 1.000 | 33/33 | 0/0 |
| agent_reviewed_extraction | coverage | semantic | 7 | 12 | 0.929 | 1.000 | 33/33 | 0/0 |

Recall and reciprocal rank include only queries with explicit known-positive scope labels. Unknown, negative, unsupported, and clarify cases remain in the status/plan denominator, never counted as automatically successful recall. Results rank document/model scopes; repeated documents with different models remain separate.

Numeric violations are checked by a separate authored-predicate oracle against each evaluated catalog's same-model, same-variant observations. This is a retrieval-safety check, not evidence that extracted values match the originals. Unjudged returned scopes are recorded separately; partial labels do not justify corpus-wide precision.

Source reference records live only in private in-memory evaluation indexes. They bypass release solely to diagnose retrieval with agent-reference values and are never saved as an approved bundle. Three synthetic discrete-value/rating queries are explicitly tagged and reported separately in `summary_by_track`; they are excluded from the table above.

The actual development catalog contains selected agent-reviewed/corrected extractions. Its retrieval results must not be presented as automatic extraction precision. The separate complete original-M18 candidate audit (`data/corpus/m18-candidate-audit-v1.json`) records 17/17 numeric transcriptions supported but only 5/17 candidates with essential factual scope, including two duplicates. Nine needed scope repair and three had wrong entities. That one-version, one-document agent audit provides no recall or held-out accuracy estimate.

Model-scoped categories were added after a development diagnosis: the workshop compendium's document category hid its compressors. Q23 is a repaired development case, not an untouched test. Discrete voltage alternatives still produce explicit conflict; they are not interpreted as a continuous range.

## Status and recall differences

- private_agent_reference / values / lexical: all authored status and known-positive expectations met.
- private_agent_reference / values / semantic: all authored status and known-positive expectations met.
- agent_reviewed_extraction / values / lexical: Q11 (unknown; recall 0.0), Q23 (ready; recall 0.5)
- agent_reviewed_extraction / values / semantic: Q11 (unknown; recall 0.0), Q23 (ready; recall 0.5)
- private_agent_reference / coverage / lexical: all authored status and known-positive expectations met.
- private_agent_reference / coverage / semantic: all authored status and known-positive expectations met.
- agent_reviewed_extraction / coverage / lexical: Q23 (ready; recall 0.5)
- agent_reviewed_extraction / coverage / semantic: Q23 (ready; recall 0.5)

Inputs and query fixture hashes, inspectable plans, per-slice case outcomes, ranks, missing coverage, and exact denominators are in `retrieval-development.json`. Synthetic 1k/10k timings and process-memory observations are in `scaling.json`; they do not establish OCR or representative-corpus performance.
