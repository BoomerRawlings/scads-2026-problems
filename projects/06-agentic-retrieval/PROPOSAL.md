# From a talk to a traceable dossier

A projected agentic retrieval method for predetermined public resources

**Status: Not started. Projected solution and research plan. Implementation and evaluation have not begun.**

Boomer Rawlings | Independent individual portfolio work | October 7, 2026

### Abstract

A presentation transcript provides an incomplete entry point into its speaker, subject, setting and intellectual history. This proposal asks whether a bounded agent can gather a more useful, source-supported dossier than a fixed retrieval pipeline when both have identical access and resource budgets. The projected system will resolve candidate entities, maintain explicit information needs, select among approved resource adapters and revise its search in response to new evidence. Every output claim will retain a source version and locator. [1]

The principal research contribution would be a controlled comparison of adaptive exploration against reproducible fixed retrieval, rather than an unrestricted demonstration of web browsing. A proposed transcript-level evaluation separates identity errors, evidence coverage, citation support, uncertainty and resource use. Public-source snapshots will support deterministic replay; a separate live condition will measure sensitivity to changing resources. Neither a longer dossier nor a greater number of tool calls will be treated as evidence of better research.

### Status and scope

> NOT STARTED. This is a projected solution and research plan. Implementation and empirical evaluation have not begun. The examples, sample sizes, budgets and acceptance thresholds are proposed; no experimental results are reported.

The work is planned as an independent individual portfolio project by Boomer Rawlings, after the original submission and grading dates. It is not a SCADS group submission. The public product page will present this proposal and its roadmap until an implemented demonstration can be documented.

## 1. Research question and related work

The problem book specifies an input transcript, information about speakers and topics, contextual details such as venue and period, and previous related talks. Retrieval must remain inside a predetermined source set. The proposed interpretation is evidence completeness within a declared collection and budget, rather than the impossible claim that all relevant information on the open web has been found. [1]

### Research questions

RQ1: Does adaptive selection of retrieval actions improve supported coverage at matched cost? RQ2: Does explicit identity uncertainty reduce mistaken speaker merges? RQ3: Does a provenance ledger help a reader verify a dossier more accurately or quickly? RQ4: How much does performance change when a frozen resource snapshot is replaced by live adapters? These questions distinguish planning benefit, reliability, human utility and environmental instability.

ReAct combines language-guided reasoning and external actions, motivating a controller that can revise its next action after observing evidence. This proposal adopts that interaction pattern but tests it under a fixed allowlist and a bounded action budget; it does not assume that agentic planning necessarily outperforms a fixed pipeline. [2]

ALCE treats generation with citations as an evaluation problem involving answer quality and citation support. It motivates claim-level checking here, where merely attaching a URL is insufficient. PROV-DM supplies a vocabulary for entities, activities, attribution and derivation; it motivates a portable evidence record rather than an opaque browsing history. Dataset documentation follows the transparency goals of Datasheets for Datasets. [3] [4] [5]

### Falsifiable contribution

The central hypothesis is a positive paired difference in supported coverage under the same budget without a material loss in claim precision. If a fixed pipeline performs equally well, the appropriate conclusion is that planning adds complexity without demonstrated benefit for this task distribution. A replayable dataset and diagnostic failure taxonomy would remain useful contributions.

## 2. Proposed architecture and data contracts

The projected implementation has four boundaries: transcript admission, a policy-enforcing resource broker, an evidence ledger and a dossier generator. The controller can request actions but cannot add domains, override adapter permissions or convert retrieved instructions into executable directives. Source text remains untrusted input. Only broker-approved fetches can create evidence records.

| Component | Proposed contract | Audit record |
| --- | --- | --- |
| Transcript | Text, speaker hints, segment times, rights record | Input hash; supplied vs inferred fields |
| Source adapter | Search, fetch, metadata, bounded media inspection | Allowlist version; query; response hash |
| Claim ledger | Subject, predicate, value, date, modality, support | Source version; passage or frame locator |
| Controller | Choose next information need and approved action | Action reason code; budget before/after |
| Dossier | Claim-linked narrative plus unresolved alternatives | Citations; coverage; abstentions; trace |

Each source record will contain a stable ID, original URL, retrieval time, publication time when supplied, content hash, media type, rights note and adapter identity. Time fields will remain separate. A transcript reference to last year will be interpreted only if the talk date is sufficiently supported. Multiple mirrors of the same biography will belong to one origin cluster rather than count as independent corroboration.

A candidate speaker will be represented as an unresolved set of identities until distinguishing evidence is available. A shared name and overlapping topic are weak evidence; an official event page linking a talk and an institutional biography is stronger. The model may suggest candidates, but only explicit source-supported links enter the ledger. Identity decisions retain alternatives and the evidence used to choose.

> Planned interface: transcript at left, information-needs board in the center, evidence and citations at right. A user can inspect source support and request a bounded follow-up without silently changing the approved collection.

## 3. Projected retrieval and synthesis method

Initial transcript processing will identify candidate speakers, named topics, event hints and temporal expressions. It will also construct a question list: who is speaking, what concepts require clarification, what event is this, and which earlier talks are explicitly connected? These are hypotheses to investigate, not extracted facts. A deterministic first pass will establish a baseline that can be reused by every comparison condition.

### Bounded adaptive loop

At step t, the controller observes an evidence summary E(t), unresolved needs U(t) and remaining budget B(t). It chooses an approved action a(t), the broker validates it, and the returned source is normalized into the ledger. The controller may expand, verify, backtrack or stop. The initial candidate policy will rank actions by expected reduction of important unresolved needs divided by estimated action cost; estimates are heuristic scores, not calibrated probabilities.

The first implementation will use a transparent finite action menu and a maximum of 12 retrieval actions per transcript. This is a proposed experimental budget, not a measured optimum. A stop action is valid when core needs have support, the remaining sources are exhausted, or further retrieval would exceed the budget. Every stop preserves unresolved items. Backtracking changes the investigation path without deleting earlier evidence or treating rejected hypotheses as findings.

### Multimodal evidence

When approved pages contain relevant images or video, the adapter will return a bounded frame/time locator and provenance. Captions, transcripts and image interpretation will remain separate evidence types. Only explicit visual claims will require visual inspection; unrelated media will not be collected merely because it is available. Authored regression fixtures will include absent attachments and mismatched captions.

The generator will produce short atomic claims before prose. A verifier will check that each citation exists, was actually retrieved and supports the stated subject, relation and time. Contradictory claims remain visible. Unsupported claims are removed or expressed as unresolved questions, and a final narrative is assembled from the checked claim ledger.

## 4. Experimental design and measurement

The proposed pilot contains 24 rights-qualified talks for debugging and annotation calibration. A subsequent target evaluation of 120 transcripts would be split by speaker and event series, keeping related talks in the same partition. Final size will be revised using pilot variance and annotation cost before test access. A topic-only split would allow near-duplicate speaker biographies to leak across partitions.

| Condition | Purpose | Controlled factors |
| --- | --- | --- |
| Transcript only | Value of external evidence | Same generation model and answer limit |
| Fixed retrieval | Non-agentic reference | Same approved sources and fetch budget |
| Adaptive retrieval | Planning effect | Same model, index and cached responses |
| Adaptive, no verification | Verification ablation | Identical initial retrieved evidence |
| Human reference subset | Verification utility | Counterbalanced order; timed tasks |

Two annotators will label transcript-specific information needs and source support; disagreement will be adjudicated before test scoring. The evaluation pool will combine outputs from all methods and independent expert searches inside the allowlist. A sampled audit of documents outside that pool will estimate pooling incompleteness. The resulting reference is bounded by the collection and annotation process, not exhaustive world knowledge.

Claim precision equals supported emitted claims divided by all checkable emitted claims. Supported coverage is the weighted fraction of reference needs satisfied with adequate citations. Citation precision measures whether cited passages support their linked claims; citation completeness measures the fraction of checkable claims with sufficient support. Identity merge errors, contradiction preservation, abstention quality, tool calls, tokens and wall time will be reported separately.

Each stochastic condition will use three prespecified seeds. Differences will be paired by transcript; confidence intervals will resample speaker/event clusters rather than individual claims. Human verification time will be analyzed alongside verification accuracy, so fast but incorrect judgments cannot be described as improved usability.

## 5. Robustness, validity and decision rules

Prespecified perturbations will include ambiguous names, missing event dates, transcript recognition errors, stale biographies, repeated syndicated text, contradictory dates, tool outages and prompt-injection text in retrieved pages. These test mechanism-level behavior. Natural transcripts and authored perturbations will be reported as separate strata so a strong synthetic score does not hide weak performance on ordinary material.

### Decision rules

A proposed research success rule is a positive lower bound on the paired supported-coverage difference against fixed retrieval, while the lower confidence bound for claim-precision difference remains above a preregistered noninferiority margin of -0.02. The margin represents a design tolerance to discuss before annotation; it is not evidence that a two-point loss is acceptable in every application. Budget compliance and zero unapproved fetches are deterministic gates.

Coverage, precision and latency will also be plotted as a Pareto frontier across budgets of 4, 8 and 12 actions. This avoids declaring a method superior merely because it spends more. Every timeout, parser failure and empty response will count in the denominator for the relevant task-level measure. Successful cases alone will not define the evaluation cohort.

### Threats to validity

Approved sources may overrepresent prominent English-speaking presenters. A dossier benchmark may reward readily discoverable biographies while neglecting topic synthesis. Automatic citation checkers can mistake topical overlap for entailment. The proposed mitigations are source-coverage reporting, a stratified transcript sample and manual auditing of high-confidence judgments. A separate human study would be needed before claiming reduced analyst burden.

Public availability does not justify assembling unnecessary personal profiles. The planned dossier scope is professional context directly relevant to the talk. It excludes sensitive personal inference and unrelated contact details. Rights and retention decisions will be made per source; the release will prefer hashes, locators and admissible excerpts over redistributing complete third-party media.

## 6. Implementation roadmap and reproduction plan

| Phase | Planned work | Exit evidence |
| --- | --- | --- |
| A: specification | Freeze approved resources, claim schema, inclusion rules | Reviewed contracts and dataset sheet |
| B: deterministic core | Build broker, snapshots, fixed retrieval and ledger | Replay equality; allowlist denial tests |
| C: agent loop | Add planning, verification, budgets and abstention | Authored cases pass without live services |
| D: pilot | Annotate24 talks; estimate cost and variance | Adjudication guide; frozen scoring protocol |
| E: evaluation | Freeze methods; run held-out transcript clusters | Complete traces; paired confidence intervals |
| F: release | Publish accessible viewer, paper and reproduction kit | Independent clean-environment replay |

The roadmap is ordered by dependencies, not a promise of calendar dates. Source licenses and annotator availability are feasibility gates. If the approved collection cannot support the required information needs, the protocol will narrow its population explicitly rather than silently supplementing it with unrestricted search.

The planned run manifest will pin the input transcript, allowlist, adapter versions, model/revision, prompt templates, seed, tool budget, source hashes and scoring configuration. A replay mode will read frozen adapter responses; a live mode will write a separate record. Their results will never be pooled without an explicit environmental-change analysis.

A future demonstration will use an authored talk fixture to let visitors expand an information need, inspect candidate identities and follow a dossier citation. Until implementation begins, the product page will offer the projected workflow and this research plan. The present repository directory contains documentation only; there is no runnable agent or evaluation dataset.

> Expected contribution: evidence about when bounded adaptive retrieval helps, together with a reproducible provenance workflow. A null result remains publishable if the comparison is controlled and failures are reported.

## 7. References and publication record

Primary sources consulted October 7, 2026. They motivate the research design; they do not validate the projected implementation. Source [1] is the user-supplied problem book, and the requirement summary is paraphrased. No source document is redistributed in this proposal.

1. SCADS 2026 Problem Book, Project 6, p. 8. User-supplied research brief.
2. [Yao et al. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. ICLR.](https://arxiv.org/abs/2210.03629)
3. [Gao et al. (2023). Enabling Large Language Models to Generate Text with Citations. EMNLP.](https://arxiv.org/abs/2305.14627)
4. [Moreau and Missier, eds. (2013). PROV-DM: The PROV Data Model. W3C Recommendation.](https://www.w3.org/TR/prov-dm/)
5. [Gebru et al. (2021). Datasheets for Datasets. Communications of the ACM.](https://arxiv.org/abs/1803.09010)

### Planned release materials

The intended future release comprises source adapters, a documented claim schema, authored regression fixtures, hash-pinned public snapshots where rights permit, annotation instructions, a frozen run manifest and an evidence viewer. Data-access restrictions will be recorded alongside reproduction instructions. Documentation will identify all transformations from transcript to claim and all human adjudication steps.

### Current publication record

This document is an independently authored research proposal. All architectural choices, sample counts, action budgets and acceptance rules are projected choices subject to preregistration. No software execution, model accuracy, analyst-time improvement or retrieval advantage is claimed. Status: Not started.

