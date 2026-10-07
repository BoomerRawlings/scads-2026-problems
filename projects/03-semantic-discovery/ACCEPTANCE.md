# VOPT comprehensive completion criteria

The solution must establish reliable technical-metadata extraction and useful natural-language discovery across a declared, representative scope. A successful demonstration on selected manuals is an initial milestone, not completion. Implementation now exists; the matrix below remains the completion standard. Engineering regressions, development references, and synthetic scaling must not be presented as independent accuracy evidence.

The whole pipeline operates offline. Discovery is primary, but both extraction and retrieval need independent evidence. Coverage-only and approved-value profiles are required; direct specification answers remain deferred.

## Required capabilities and evidence

| ID | Required capability | Completion evidence |
| --- | --- | --- |
| A1 | Rights-qualified, representative corpus with stable document/product/revision identity | Per-file rights and provenance manifest; duplicate-family grouping; coverage matrix for every claimed category, language, layout, and attribute. Authentic scans establish real-scan performance. |
| A2 | Durable ingestion and explicit processing coverage | Idempotent reruns, bounded retry, interrupted-run recovery, per-page success/failure records, and rejected/partial/complete states. A failed page never becomes evidence that an attribute is absent. |
| A3 | Layout-aware extraction with correct technical meaning | Complete assertions retain model/variant, attribute, typed value/range/tolerance, unit, operating/rating qualifiers, and page/region evidence. Tables, inherited headers, footnotes, and multi-model applicability are evaluated explicitly. |
| A4 | Review and correction with traceability | Reviewers inspect original evidence beside candidates; corrections preserve raw output. Independent annotation review includes a random sample and difficult cases. Changed source, extractor, or schema flags affected reviews/releases for reconciliation. |
| A5 | Controlled metadata release and catalog lifecycle | Strict allowlist, explicit profile, deterministic bundle, schema/policy versions, integrity manifest, atomic import, compatibility checks, and rollback. Replacement/withdrawal removes stale records from all indexes, derived vectors, and caches. |
| A6 | Compositional natural-language discovery | Unseen paraphrases, exact identifiers, synonyms, units, thresholds/ranges, conjunctions/disjunctions, and supported negation translate into inspectable query plans. Every hard constraint is enforced on the same model/variant. Ambiguity and unsupported predicates are explicit. |
| A7 | Honest result semantics and document requests | Distinguish no match, unknown, incomplete processing, unsupported query, and conflicting/revision-dependent evidence. Explanations use released fields. Results provide versioned document/request references without fetching private sources. |
| A8 | Enforced metadata-only boundary | Separate discovery installation receives only released bundles. Test source absence, forbidden fields, content-only sentinel phrases, explanations, traces, derived indexes, and profile downgrades. Private content/unreleased-value changes cannot change results for a fixed export. |
| A9 | Complete offline operation and recovery | On a clean target, install from packaged dependencies/models and licenses, run preflight and cold-start all stages with network blocked. Missing/incompatible assets fail locally with useful diagnostics. No remote inference, login, telemetry dependency, or automatic download fallback. |
| A10 | Generalization and reproducibility | Untouched manual/model families and query paraphrases; frozen labels/configuration; per-slice results; independent rerun. Record versions, hardware, time, memory, failed pages/queries, and review effort. |
| A11 | Complete user workflows | Working batch commands, evidence-review interface, and discovery interface cover ingest, inspect/correct, release, import, query, clarify, revise, withdraw, and prepare a document request. Test workflows with an operator beyond the implementation author where available; identify any validation gap. |
| A12 | Auditable publication package | Runnable solution, corpus/rights manifest, schema and annotation guide, fixed evaluation suite, machine-readable results, failure analysis, reproduction instructions, and a PDF chapter tying each claim to evidence. |

One local application with separate extraction and discovery launch modes can meet these requirements. Services, orchestration frameworks, and incremental indexing are not requirements. Whole-catalog replacement is acceptable if it passes lifecycle and rollback tests.

Rollback must satisfy the latest imported policy and withdrawal state; an older catalog that restores revoked values is not eligible. If no eligible catalog remains, fail closed. Offline discovery learns upstream changes only through explicit replacement/revocation imports. Upstream changes invalidate upstream approvals immediately, but cannot silently alter the disconnected catalog; document this distribution boundary and test it.

Treat document text and user queries as data. Any model-generated query plan must pass an allowlisted schema and use parameterized execution; it cannot execute arbitrary SQL, commands, or file paths. Embedded document instructions cannot change extraction policy, release fields, or tool access. Include these cases in validation if models participate in the pipeline.

## Corpus and scenario coverage

Define the supported scope and acceptance protocol before final testing. The corpus must cover the scenarios used to justify the comprehensive claim; a missing critical scenario remains a gap to resolve, not a reason to silently remove the requirement.

| Dimension | Required scenario inventory |
| --- | --- |
| Scan conditions | Authentic clean and poor scans; rotation, skew, low contrast; mixed scanned/text pages; explicit unreadable-page handling |
| Layout | Prose specifications, tables, multi-column pages, continued tables, and qualifying footnotes |
| Identity | Multiple models per page/manual, variants, exact identifiers, document versus product revisions, contradictory specifications |
| Technical meaning | Electrical input versus mechanical output; rated versus peak; categorical and numeric values; units, ranges, tolerances, and conditional operating values |
| Coverage meaning | Model-specific specifications versus generic mentions; observed presence versus not found versus unreadable/unknown |
| Queries | Held-out paraphrases, synonyms, model names, multiple constraints, ranges, units, ambiguity, negation, unsupported terms, and no-answer cases |
| Release modes | Coverage-only, approved values, value-to-coverage downgrade, changed revision, withdrawal, incompatible or damaged bundle |
| Operation | Reprocessing, interruption, bad input, missing model/language assets, offline cold start, resource limits, and recovery |

The scope need not be an exhaustive Cartesian product of these dimensions. Select high-risk combinations deliberately, including poor scans containing multi-model tables. Report the supported languages and categories explicitly. Synthetic cases supplement authentic coverage and are labeled separately; they cannot establish real-world accuracy.

## Evaluation design

1. **Qualify and label.** Annotate source coverage and full technical assertions, including applicability and evidence locations. Define document relevance both against original content and against each release profile. Record reviewer disagreements before adjudication.
2. **Split before tuning.** Keep duplicate editions, model families, and generated scan derivatives together. Separate development data from final manual families and independently authored queries. Hold out unfamiliar layouts wherever layout generalization is claimed.
3. **Diagnose the stages.** Run identical queries against source-derived reference metadata, raw automatic extraction, and reviewed extraction. Use reference query plans on a diagnostic subset to separate query interpretation errors from retrieval and extraction errors. Raw outputs enter an explicitly unreviewed private evaluation catalog, never the approved publication catalog.
4. **Compare methods.** Compare a simple OCR/rule baseline with the chosen layout-aware extraction approach. Compare lexical metadata retrieval with a local semantic candidate on the same data. Retain the simpler approach if it meets the fixed requirements; extra model complexity must demonstrate a benefit.
5. **Measure usefulness and effort.** Report full-assertion precision/recall, correct model/unit/qualifier association, evidence localization, false coverage claims, relevant-document recall/ranking, query interpretation, exact-constraint violations, abstention, and review time. Report per critical slice and sample counts, not only aggregates. Compare total processing/review effort with manual cataloging before claiming labor savings.
6. **Freeze and evaluate.** After the pilot, set numerical thresholds and minimum evidence per critical slice, then freeze configuration and final data. Include uncertainty where sample sizes support it. Completion requires the frozen criteria to be met; a failed final test remains a recorded result. Fixes become regression evidence, with fresh untouched evidence needed for renewed generalization claims.
7. **Verify isolation and recovery.** Repeat with networking blocked and source/OCR stores absent from discovery. Check cold starts, interrupted jobs, invalid imports, withdrawal, rollback, and profile downgrade. A lack of observed violations only describes the tested cases.

No universal accuracy percentage is claimed before corpus characterization. The final protocol must specify denominators, numerical tolerances, supported-query coverage, and abstention treatment so that answering almost nothing cannot manufacture a passing score. Human correction must not conceal weak automatic extraction.

## Pilot versus completion

The first small corpus establishes feasibility, annotation consistency, offline installation, and failure patterns. It determines component selection and defensible evaluation size. It does not impose a cap of 3-5 attributes or certify comprehensive performance.

Completion requires all applicable A1-A12 evidence and the declared scope's coverage gates. Unmet core cases require more sourcing, engineering, or an explicit scope decision; neither a polished interface nor a successful scripted demonstration substitutes for this evidence.

The PDF follows verification: problem interpretation, offline architecture, corpus and rights, extraction and release semantics, discovery method, controlled evaluation, representative failures, operating requirements, limitations, and reproduction instructions. No operational classified-system validation is implied.
