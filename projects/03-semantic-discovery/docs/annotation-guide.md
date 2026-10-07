# VOPT annotation guide

Reference labels must describe what the source establishes, including scope and uncertainty. Current corpus leads are agent-inspected development examples. They are incomplete and cannot establish extraction precision, recall over whole manuals, or independent human accuracy.

## Label a source claim

1. Record source SHA, PDF page, printed page if different, bounding region and exact supporting text. Inspect the raster; embedded OCR alone is insufficient.
2. Identify the system, model, component and variant. A model appearing elsewhere in the manual is not evidence that every numeric statement applies to it. Mark ambiguous scope unresolved.
3. Record attribute, original value/unit, normalized value/unit, rating qualifier and operating conditions. Preserve ranges, tolerance, alternative configurations, footnotes and revision changes. Never convert electrical input watts into mechanical output horsepower.
4. Separate explicit observation, absent-from-reviewed-region, unreadable region, ambiguous value and out-of-schema attribute. Whole-document absence requires complete review; automatic non-extraction is unknown.
5. Mark duplicate claims and contradictory claims separately. Retain conflicting source statements; do not resolve them by majority count or latest OCR confidence.
6. Independently review a random sample and every difficult/ambiguous case. Save original labels, disagreements, adjudication and reviewer kind. Record active labeling/review time separately from machine time.

## Full assertion matching

A correct match needs document revision, model/component, variant, attribute, value/range/tolerance, canonical unit, rating/operating conditions and source localization. Matching only the scalar number is a weaker diagnostic. Report both; never name number-only matches full-assertion accuracy.

Use exact discrete labels and numerical tolerance only for deterministic unit-conversion roundoff. OCR mistakes, rounded/approximate ratings and conflicting editions are not roundoff. Discrete `125/250 V` is not a continuous interval. `About 600 rpm` supplies no precise interval unless the source defines one.

## Query relevance

Label each query against original-source reference metadata and separately against coverage/value release profiles. List relevant document/model/variant scopes, expected status, hard predicates and unsupported predicates. A document whose relevant value is not released may be source-relevant but ineligible for value filtering. Conditional matches require compatible conditions; unrelated facts cannot satisfy a conjunction.

Record no-match, unknown, clarification, conflict and unsupported cases explicitly. Include unfamiliar paraphrases authored independently after parser freeze. Query families and near duplicates stay in one partition.

## Review is not evaluation

Operational approval changes what can be released; it does not itself validate the extractor. Keep raw automatic, reviewed and source-reference results separate. Agent review, fixture review and human review are distinct actor kinds. Do not relabel an automatic matching script as human review. Authenticated identity and organizational approval workflows require a separate deployment design.
