# Retrieval only when it earns its cost

A projected study of adaptive multilingual RAG and evidence-aware evaluation

**Status: Not started. Projected solution and research plan. Implementation and evaluation have not begun.**

Boomer Rawlings | Independent individual portfolio work | October 7, 2026

### Abstract

Retrieval-augmented generation must balance evidence quality against retrieval, reasoning and translation cost. This proposal studies a compact controller that chooses among no retrieval, single-pass retrieval and bounded iterative retrieval, with multilingual query expansion when the available evidence warrants it. The projected evaluation separates the contribution of adaptive retrieval from the contribution of an improved automatic judge. Both are measured against frozen, non-adaptive baselines. [1]

The English evaluation will use a pinned TREC 2024 RAG release. A separately pinned RAGTIME edition will supply multilingual report and retrieval tasks. The proposed judge will score support, completeness and cross-language consistency against source passages and human annotations. Held-out agreement, language-specific error and ranking stability will determine whether its output is usable as an evaluation instrument, rather than assuming that a fluent explanation establishes a reliable judgment. [3] [4]

### Status and scope

> NOT STARTED. Projected solution and research plan only. Implementation, dataset preparation and experimental evaluation have not begun. All proposed targets and budgets are design parameters; no measured results are reported.

Planned as independent individual work by Boomer Rawlings after the original submission and grading dates. The initial contribution would be a reproducible quality-cost comparison and a calibrated judge protocol. The scope is research evaluation, not a claim that one retrieval policy or language model is universally best.

## 1. Motivation, literature and hypotheses

An easy query may be answered with a single relevant passage, while a report request may require several facets and sources. Applying the same retrieval depth to both can waste resources or omit evidence. Cross-language retrieval adds another decision: whether to search shared embeddings directly, translate the query, or combine both. The proposed controller will make these choices under an explicit budget, preserving their costs in the run record.

Adaptive-RAG motivates routing queries to retrieval strategies with different complexity. This proposal will reproduce the routing idea as a baseline and test a controller that also observes retrieved evidence gaps. The intended novelty is a controlled interaction between adaptive budgets, cross-language retrieval and judge reliability; the project does not claim to invent adaptive retrieval. [2]

TREC 2024 RAG defines retrieval, augmented generation and end-to-end RAG tasks with cited answers and evaluation of retrieval, nuggets, support and fluency. RAGTIME emphasizes multifaceted multilingual reports and cited evidence; its current official scope includes English, Spanish, Chinese and Russian. The exact benchmark edition and available judgments will be frozen before experimentation. [3] [4]

AutoJudge is a NIST meta-track for automatic judgments over runs from other tracks. It will inform the evaluation protocol when suitable challenge data is available. LLM-as-a-judge research documents position, verbosity and self-preference biases, which motivate blinded scoring and perturbation tests here. No published agreement level is assumed to transfer to this multilingual setting. [5] [6]

### Falsifiable hypotheses

H1: adaptive retrieval reduces median end-to-end cost at noninferior grounded completeness. H2: language-aware expansion improves multilingual evidence coverage at equal document budget. H3: evidence-conditioned judges outperform answer-only judges on held-out human support labels. Each hypothesis will be tested separately, with interaction effects reported rather than hidden in one aggregate score.

## 2. Proposed system and budget model

| Stage | Projected behavior | Recorded cost |
| --- | --- | --- |
| Query analysis | Identify language, facets and answer constraints | Classifier tokens and latency |
| Route | Choose none, single-pass or iterative retrieval | Policy version and chosen budget |
| Retrieve | Lexical, multilingual dense or fused search | Queries, candidate counts, index time |
| Expand | Translate or reformulate unresolved facets | Translation tokens and calls |
| Generate | Compose claim-linked answer from evidence | Input/output tokens and wall time |
| Evaluate | Score support, completeness and uncertainty | Judge calls, human audit time |

The initial controller will be a small supervised classifier with a transparent fallback policy. Its inputs will be query features and retrieval diagnostics available at decision time, including language, requested facets, score dispersion and evidence overlap. Gold relevance judgments and final answer scores will never be available to the test-time controller. Training labels will be generated only from development runs.

A budget vector B = (retrieval calls, retrieved tokens, generation tokens, elapsed time) will be enforced by the orchestration layer. Monetary cost, when applicable, will be derived from separately recorded dated prices; it will not substitute for token and time measurements. Local models will report hardware, power mode and concurrency. Translation, reranking, routing and failed calls are part of total cost.

The first study will compare at most three retrieval iterations and matched final context limits. These are projected bounds chosen for interpretable experiments. A controller that exhausts its budget must return a partial supported answer or abstention. It cannot silently increase the context window, call an uncounted search service, or reuse test judgments as a confidence signal.

> Projected data path: query -> route -> retrieve/expand -> evidence ledger -> cited answer. Evaluation consumes the frozen ledger and answer; it cannot alter the submitted response.

## 3. Multilingual retrieval and answer attribution

Four baseline retrieval conditions are proposed: lexical search in the query language, multilingual dense search, translate-then-lexical search, and reciprocal-rank fusion of lexical and dense candidates. Index construction, chunk boundaries and final evidence budgets will be identical where meaningful. Model revisions and tokenizer differences will be recorded so a better encoder is not misattributed to the controller.

### Separate languages and task directions

RAGTIME report generation into English from multilingual evidence is distinct from answering arbitrary questions in each source language. The primary evaluation will follow the selected track edition exactly. Any additional translated-query experiment will form a separate dataset with its own annotation and translation provenance. Scores from different task directions will not be pooled under a generic multilingual label.

Every translated query will retain its original text, target language, translation model and revision. Named entities, dates, quantities, negation and uncertainty markers will be checked explicitly. A translated passage is a derived artifact; its citation points to the original source and an aligned passage locator, while the translation is retained for inspection. Back-translation is a diagnostic, not proof of semantic equivalence.

### Evidence-aware stopping

The controller will maintain unresolved report facets and the sources supporting each candidate claim. It may stop when requested facets have adequate evidence, when no new sources appear, or when the budget is exhausted. A learned stopping model will be compared with a fixed iteration count and a simple novelty rule. An ablation will remove language labels to test whether language-aware routing provides benefit beyond generic uncertainty.

Cross-language agreement between two passages will not automatically count as independent corroboration: translated mirrors and syndicated copies will be clustered by origin where metadata permits. Contradictions will retain source language and time. Evaluation will distinguish missed evidence, translation distortion and generation error so a final wrong answer can be attributed to a specific stage.

## 4. Projected judge and human reference protocol

The planned judge input contains the request, answer, cited passages, source languages and a rubric. It produces structured judgments for atomic claim support, missing required facets, contradiction and cross-language semantic fidelity. Each decision must name the relevant passage span or state insufficient evidence. A score without such a locator is treated as an invalid evaluation output.

| Dimension | Reference question | Primary check |
| --- | --- | --- |
| Support | Does the cited source entail this claim? | Human claim-passage label |
| Completeness | Which required information nuggets are covered? | Frozen nugget inventory |
| Cross-language fidelity | Are entities, quantities and modality preserved? | Bilingual adjudication |
| Contradiction | Does the answer hide conflicting source claims? | Conflict-bearing task slice |
| Usability | Is the report coherent and task-responsive? | Separate ordinal human rubric |

The proposed pilot will double-annotate at least 200 claim-passage pairs, stratified by source language and support class. The final annotation target will be set from pilot disagreement and confidence-interval width before held-out evaluation. Annotators will see blinded system identities. Disagreements will be adjudicated, while initial labels remain available for estimating reliability. Language proficiency and adjudication instructions will be documented.

Judge calibration will use development labels only. A held-out set will report macro-F1, class-specific recall, confusion matrices, abstention coverage and calibration error where the judge emits probabilities. System-level ranking agreement will be reported alongside item-level agreement, since high overall agreement can still reverse the ordering of close systems.

Bias checks will swap answer order, remove system names, equalize formatting and compare concise versus verbose paraphrases. A model-family holdout will test judge transfer to outputs from unseen generators. No system will receive sole credit from a judge drawn only from its own model family.

## 5. Evaluation design and statistical analysis

The proposed study has two stages. First, reproduce fixed retrieval/generation baselines on a pinned English release and the selected multilingual edition. Second, compare adaptive policies at matched evidence budgets and several prespecified cost ceilings. Training, tuning, judge calibration and final evaluation partitions will be separated by topic family; paraphrases and translated variants stay together.

Primary retrieval metrics will be nDCG and recall at declared cutoffs using the selected release judgments. Generation will use supported nugget coverage, claim-level support and contradiction rates. Unjudged documents will be handled according to the benchmark protocol and sensitivity analyses, not silently treated as irrelevant. Human-grounded metrics will remain distinct from judge-derived estimates.

Quality-cost comparisons will show paired per-topic differences, Pareto frontiers, median latency and tail latency. Topic-cluster bootstrap intervals will account for shared translations and repeated seeds. A prospective noninferiority margin of two percentage points in supported coverage is proposed for discussion; it must be fixed before evaluation. An adaptive system earns an efficiency claim only when its quality condition and cost reduction both pass.

### Ablations and failure accounting

Ablations will remove adaptive stopping, query translation, multilingual fusion and evidence-conditioned judging one component at a time. A factorial subset will test whether translation helps only with particular retrieval policies. All failed runs, budget exhaustion and unavailable documents remain in the task denominator. Cost comparisons will distinguish cold and warm caches, index preparation and online answering.

A negative outcome is informative: the controller may save tokens only by omitting relevant facets, or the judge may agree on easy English cases while failing cross-language negation. Such findings would narrow the deployment recommendation. No single blended score will be used to conceal a quality-cost tradeoff or a low-performing language stratum.

## 6. Roadmap, reproducibility and validity

| Phase | Planned deliverable | Exit criterion |
| --- | --- | --- |
| A: benchmark freeze | Edition, licenses, split and scoring manifest | Data access and evaluation scope verified |
| B: fixed baselines | Lexical/dense/fused retrieval plus cited generation | Reproducible runs and cost accounting |
| C: controller | Routing, translation, stopping and budget enforcement | No hidden test labels; bounded actions |
| D: judge pilot | Bilingual rubric and adjudicated development labels | Bias checks; sample-size decision |
| E: frozen comparison | Held-out runs and paired analyses | All runs included; confidence intervals |
| F: publication | Paper, manifests, scripts and demonstration | Independent reproduction of scoring |

The run manifest will pin collection version, document IDs, chunking, indexes, model revisions, prompts, seeds, language routes, budgets, hardware and cache state. A separate judge manifest will identify rubric, model, calibration split and parser version. Generated evaluation artifacts will never overwrite the original answer or source evidence.

Dataset availability, reuse terms and human judgment coverage are feasibility gates. A newer track release is not interchangeable with the 2024 English benchmark. Likewise, translation quality and document-topic imbalance may dominate nominal language effects. The analysis will report per-language sample sizes and uncertainty, and will avoid claiming typological generality from four languages.

A future product demonstration will display the retrieval route, remaining budget and source-linked answer for an authored multilingual fixture. The current publication offers this plan only. There is no working controller, judge implementation or measured quality-cost frontier in this project directory.

## 7. References and proposed contribution

Primary sources consulted October 7, 2026. Track descriptions are version-sensitive; the experiment must preserve the edition actually used. The following references establish context and evaluation resources, not results for this projected system.

1. SCADS 2026 Problem Book, Project 7, p. 9. User-supplied research brief.
2. [Jeong et al. (2024). Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question Complexity. NAACL.](https://arxiv.org/abs/2403.14403)
3. [TREC RAG organizers (2024). TREC 2024 RAG Track Guidelines.](https://trec-rag.github.io/annoucements/2024-track-guidelines/)
4. [TREC RAGTIME organizers (2026). Official track description and language scope.](https://trec-ragtime.github.io/)
5. [NIST (2026). TREC call for participation, AutoJudge track description.](https://trec.nist.gov/cfp.html)
6. [Zheng et al. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. NeurIPS.](https://arxiv.org/abs/2306.05685)

### Expected research artifact

The intended contribution is a transparent answer to two questions: when does adaptive multilingual retrieval pay for its extra decisions, and when can an automatic judge reliably detect the resulting quality changes? The planned evidence package will retain the underlying answers, citations and human labels so readers can recompute conclusions under alternative metric choices.

> Current status: Not started. All methods, budgets, annotation targets and comparisons in this paper are projected. No performance ranking, measured speedup or empirical judge reliability is claimed.

