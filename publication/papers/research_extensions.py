"""Formal methods, primary literature, evaluation protocols and proposed roadmaps.

Proposed experiments are explicitly distinguished from recorded observations.
External bibliographic entries were checked against primary sources 2026-10-07.
"""

RESEARCH = {
'01-sensemaking': {
 'refs':[
  ('Yao et al. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. ICLR; arXiv:2210.03629.','https://arxiv.org/abs/2210.03629'),
  ('Liu et al. (2024). Lost in the Middle: How Language Models Use Long Contexts. TACL; arXiv:2307.03172.','https://arxiv.org/abs/2307.03172'),
  ('Moreau and Missier, eds. (2013). PROV-DM: The PROV Data Model. W3C Recommendation.','https://www.w3.org/TR/prov-dm/'),
  ('Project integration and report contracts','docs/integration.md'),
  ('Implemented directed traversal and evidence retrieval','sensemaking.py'),
 ],
 'formal': {'title':'1. Research framing and formal scope','blocks':[
  ('p','ReAct interleaves language-model decisions with actions that gather information from an external environment. That is a useful architectural precedent for this project\'s model-selected tools; the present work concentrates on typed organizational paths and provenance rather than reproducing ReAct\'s benchmark claims. [8]'),
  ('p','Liu et al. found that a model\'s use of evidence can depend on where relevant information appears in a long context. This motivates testing the present system\'s selective retrieval and compact synthesis, but does not prove that its policies improve accuracy. W3C PROV-DM supplies a vocabulary for entities, activities, derivation and attribution; the project ledger is a concrete traceability mechanism, not a claim of complete PROV conformance. [9] [10]'),
  ('h','Problem formulation'),
  ('p','Let G=(V,E) be a directed typed entity graph; let D be versioned evidence items, each with an ID, source locator, date and content fingerprint. An investigation receives target v, question q and resource budget B. A tool trace T selects a reachable scope V_T, retrieves D_T, and produces claims C with citation map P:C -> subsets(D_T). This notation formalizes the implemented contract; it is not an additional trained model. [1] [11]'),
  ('code','For each reported claim c:\n  P(c) is nonempty and refers to retrieved source versions.\n  subject(c) is within the declared investigative scope.\n  cited paths retain relation types and edge evidence.\n  unsupported factual resolution is replaced by qualification.'),
  ('p','A valid citation map is necessary but insufficient: a source can be read correctly yet fail to entail the claim. The central research question is therefore whether the workflow improves source-supported analytic coverage while keeping attribution, uncertainty and resource cost inspectable. The evidence in this paper addresses feasibility for one known synthetic case.'),
  ('note','Prospective hypothesis: compared with an evidence-packet baseline, selective tool use can recover dependency-path evidence with fewer irrelevant source reads at comparable claim support. This is a testable hypothesis, not an achieved result.'),
 ]},
 'algorithm': {'title':'3. Evidence control and algorithmic choices','blocks':[
  ('p','The abstract procedure below expresses the host/model boundary used by the prototype. Actions and retrieved observations form the public audit record. Private model reasoning is neither required as proof nor substituted for source evidence. The procedure is descriptive pseudocode; the frozen implementation and schema remain authoritative for reproduction. [5] [11]'),
  ('code','resolve target; if ambiguous, request clarification\ninitialize bounded graph scope and retrieved-source ledger\nrepeat while action and time budgets permit:\n  model selects a permitted tool action\n  host validates arguments, executes and records the result\n  add exact returned sources and edge proofs to the ledger\n  inspect available media when the run policy requires it\n  accept finish only after required evidence obligations\nsynthesize from admitted evidence; validate citations\nretain report, trace, media observations and run metadata'),
  ('h','Why graph direction matters'),
  ('p','A project depending on a sensor batch and a supplier providing that batch are distinct directed relations. Reversing the direction or treating them as containment changes the analytic meaning. A bounded search must retain the path explanation, not merely the set of connected names. This also allows exclusion of a name-matching arts event without erasing genuinely relevant external dependencies. [1] [2]'),
  ('h','Context is a resource and an experimental variable'),
  ('p','Retrieving every source can increase context cost and duplicate evidence. The accepted run\'s compact synthesis retained nine exact record versions while removing seven identical repeated occurrences; its review verified the input lineage. A compact representation may improve resource use but could also omit context needed for interpretation. Any causal claim needs an ablation holding model, question, sources and decoding fixed. [2]'),
  ('p','The implemented breadth-first traversal scans the full edge list for each expanded node, giving an O(|V_T| times |E|) upper bound with hop-bounded path copying, excluding source and model work. An adjacency index is a prospective optimization, not the current cost model. End-to-end work additionally includes source bytes, media decoding and inference; report those resources separately rather than extrapolating one CPU run. [12]'),
 ]},
 'evaluation': {'title':'6. Proposed evaluation protocol','blocks':[
  ('note','PROPOSED STUDY. The protocol below defines future research measurements. None of its hypotheses, comparisons or numerical acceptance decisions are reported as completed experiments.'),
  ('table',['Research question','Controlled comparison','Primary observation'],[
   ['Does tool use improve coverage?','Same question/model: static packet versus adaptive retrieval','Supported target claims and necessary path coverage'],
   ['Does compaction preserve meaning?','Exact evidence histories with compaction on/off','Support, contradiction handling and omitted qualifications'],
   ['Does media add unique value?','Text-only versus actual pixels, using nonduplicate evidence','Evidence-dependent claim changes and source entailment'],
   ['Does ambiguity handling transfer?','Held-out aliases and decoy entities','False resolution rate and useful abstention'],
  ],[149,181,158]),
  ('p','Freeze organization families, source revisions and analyst questions before the final evaluation. Split by organization rather than individual document so that repeated templates or names do not cross the boundary. Use independent reviewers to annotate required claims, relevant paths and source-supported interpretations, with adjudication for disagreements. Retain source truth separately from agreement among copied documents.'),
  ('p','Define supported-claim precision as adjudicated supported factual claims divided by all evaluated factual claims; define coverage over the independently enumerated relevant claims. Score citations for both exact source resolution and entailment. Report ambiguous or unverifiable claims separately. For repeated runs, cluster uncertainty estimates by question and organization, not by correlated claims from one answer.'),
  ('p','A paired analyst study should use matched tasks and counterbalanced order, measuring active analyst time, source-opening actions and answer quality under the same information access. A speed improvement without equivalent support quality would not establish reduced analytic burden. Resource accounting must include setup, failures and retries. Predeclare a practically meaningful effect and feasible sample size before collecting final outcomes.'),
 ]},
 'roadmap': {'title':'7. Research roadmap and validity','blocks':[
  ('table',['Phase','Concrete output','Decision rule'],[
   ['Corpus qualification','Versioned public-source organizations, independent question/claim labels','Freeze families and provenance before final testing.'],
   ['Bounded execution','Measured context/tool/media budgets and resumable evidence storage','Admit runs only under an explicit resource profile.'],
   ['Controlled comparison','Packet/adaptive and compaction ablations with retained failures','Select the simplest approach supported by paired evidence.'],
   ['Analyst validation','Counterbalanced task study and reproducible source packages','Claim utility only within measured quality/time scope.'],
  ],[103,219,166]),
  ('p','This roadmap extends an implemented prototype. It does not relabel the current software as unstarted or predict a completion date. Each phase produces an inspectable artifact before a stronger claim becomes appropriate. New models or larger contexts should be frozen as distinct experimental conditions rather than silently replacing an unsuccessful run.'),
  ('h','Threats to validity'),
  ('p','Construct validity is the largest current constraint: synthetic captions and authored assertions simplify the relation between text and world truth. Internal validity is limited by tuning on the same case and concurrent host workload. External validity depends on organization diversity, realistic ambiguity and source quality. Reviewer independence matters because AI review and model synthesis may share error patterns.'),
  ('p','The source ledger supports reproducibility of what was supplied to a model, not deterministic reproduction of every model output. Runtime version, weight identity, launch profile, sampling and source hashes should accompany each trial. A later better result does not erase earlier evidence; both are part of the research record.'),
  ('h','Conclusion'),
  ('p','The prototype demonstrates an auditable organizational investigation with actual graph, record and media tools. Its strongest result is preserving claim scope and unresolved evidence through a complete recorded workflow. Establishing broader analytic value requires the controlled evaluations above; the current contribution is the implemented method and its inspectable development evidence.'),
 ]},
},
'02-311-analytics': {
 'refs':[
  ('Yu et al. (2018). Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task. EMNLP.','https://arxiv.org/abs/1809.08887'),
  ('Elastic. Paginate search results. Elasticsearch reference, accessed October 7, 2026.','https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results'),
  ('Project verification and live-evaluation requirements','docs/acceptance.md'),
  ('Reproducible export and ingestion recovery','docs/reliability.md'),
 ],
 'formal': {'title':'1. Research framing and semantics','blocks':[
  ('p','Text-to-query research distinguishes understanding a question from executing its program. Spider evaluates transfer to new databases and complex query structures; it motivates keeping natural-language interpretation separate from deterministic backend correctness. This project targets a fixed civic catalog and Elasticsearch, so it is not a Spider reproduction or cross-domain accuracy claim. [8]'),
  ('p','Elastic documents search_after with point-in-time contexts to preserve a stable view across deep pagination. That guidance motivates the adapter\'s snapshot and cursor semantics. It does not establish that the local implementation has passed a live-engine performance evaluation. [9] [10]'),
  ('h','Formal analytical object'),
  ('p','Let D_v be the immutable dataset version and q=(v,F,I,G,M,Z) a validated specification: version, non-time filter, half-open interval, grouping, metric definitions and timezone. Let C(q)={r in D_v: F(r) and time(r) in I}. Preview, CSV and map are projections of this saved cohort, not independent reconstructions from the user\'s natural language. [2]'),
  ('code','n(g,I) = number of cohort records in group g\nrate(g,I) = n(g,I) / calendar_exposure_days(I,Z)\nchange(g) = rate(g,I_after) - rate(g,I_before)\nmean_closure(g) = sum(valid durations) / count(valid durations)'),
  ('p','The denominator of mean closure is neither all requests nor all closed requests when usable timestamps are missing. Calendar exposure uses the requested timezone; elapsed hours are a different quantity. The cohort is descriptive of reported requests, so neither incident incidence nor causal agency performance follows from these expressions. [2] [3]'),
  ('note','Prospective research question: can a bounded analytical contract improve end-to-end semantic correctness and artifact agreement across different agents without unacceptable interaction cost? Current fixture outcomes establish selected behaviors, not a population-level answer.'),
 ]},
 'algorithm': {'title':'3. Execution and artifact invariants','blocks':[
  ('p','The service records the normalized specification, catalog and dataset identity together with its result. This supports a useful invariant: a later artifact must refer to the same analytical selection, even if the initial result was truncated for display. The following pseudocode summarizes that contract. [2]'),
  ('code','discover catalog and immutable dataset identity\nvalidate specification, supported operation and coverage\ncompile typed filters, grouping and metric definitions\nexecute under declared limits; save result envelope\nfor export or map:\n  load saved result and verify version compatibility\n  require all_matching or explicit selected group IDs\n  compute exact planned cohort size; check admission\n  stream with stable ordering and source-identity guards\n  verify membership/counts; publish artifact and manifest'),
  ('h','Failure is a typed outcome'),
  ('p','Invalid requests, insufficient coverage, unsupported operations, exceeded budgets and partial execution are distinct errors. An empty complete result is valid evidence of no matching records within the selected data; a timeout or unobserved date is not. Artifact status counters describe persisted progress and must not be read as proof that a worker is currently alive. [2] [11]'),
  ('h','Why admission and streaming both matter'),
  ('p','Exact row admission prevents a known oversized task from consuming a worker slot, but byte size still depends on encoded fields. Stream-time limits are therefore necessary after admission. Disk observations can prevent obvious exhaustion without reserving the space; cooperative deadlines can overrun a blocked I/O call. These distinctions shape how the interface describes pending and failed artifacts. [6] [11]'),
  ('p','For N selected rows and k projected columns, serialization work is proportional to encoded output bytes, not merely N x k. Backend aggregation costs depend on cardinality and index layout, while agent latency includes tool planning and synthesis. Separating these costs avoids extrapolating a small fixture benchmark into physical cluster capacity.'),
 ]},
 'evaluation': {'title':'6. Proposed end-to-end evaluation','blocks':[
  ('note','PROPOSED STUDY. The real-data and agent evaluation below is a research plan, not a claim that the million-record or live visualization gates have been passed.'),
  ('table',['Layer','Independent reference','Evaluation unit'],[
   ['Dataset integrity','Unique keys, frozen revisions, date coverage and geometry versions','Qualified immutable capture'],
   ['Deterministic analytics','Separately calculated counts, rates and valid-duration statistics','Query and complete result cohort'],
   ['Agent interpretation','Human-authored questions with accepted/clarify specifications','Question across repeated runs and agent hosts'],
   ['Artifacts','CSV key set and map cohort/metric comparison','Saved result, export and rendered map'],
   ['Resources','Measured hardware, index size, latency and failure recovery','Workload profile and concurrent task count'],
  ],[110,235,143]),
  ('p','The project acceptance design specifies at least two million real unique requests and a held-out set of 40 questions repeated three times, with a second agent comparison. These are planned gates, not achieved measurements. Query families should include dates, multiple filters, geography, grouping, comparisons and clarification cases, with final prompts hidden from implementation tuning. [1] [10]'),
  ('p','Score intent correctness separately from execution correctness. Count a question as artifact-consistent only when narrative numbers, saved result, full CSV selection and requested map metric agree. For geography, report both matched and unmapped counts. Preserve all attempted runs, errors and unsupported questions in denominators; selective success-only timing would bias the result.'),
  ('p','Use paired question-level comparisons between agent hosts and report uncertainty at the question level, with repeated outputs nested within questions. Resource experiments should vary row count, filter selectivity, group cardinality and export width independently. Measure actual cold/warm conditions and sustained concurrency rather than deriving tail latency from three observations.'),
 ]},
 'roadmap': {'title':'7. Roadmap and analytical validity','blocks':[
  ('table',['Phase','Research artifact','Progression criterion'],[
   ['Qualify data','Frozen real capture, uniqueness audit and versioned geography','Coverage claims independently justified.'],
   ['Verify parity','Live backend, full CSV and rendered Maps comparisons','Agreement across declared query families.'],
   ['Evaluate agents','Held-out question set, repeated runs and second host','Intent/answer/artifact scores reported together.'],
   ['Measure operations','Hardware-specific scale and recovery report','Capacity claims tied to observed workloads.'],
  ],[110,220,158]),
  ('p','The present implementation is In progress. The roadmap strengthens evidence for an existing service and does not project performance numbers or a completion date. Static reasoning can improve admission and storage safeguards before expensive workloads, but only execution on a qualified target can support a measured capacity claim. [6] [10]'),
  ('h','Threats to validity'),
  ('p','Data capture is a source of uncertainty independent of query correctness. A provider\'s count and sampled records may be internally consistent without proving a transactionally complete local population. Complaint rates reflect reporting behavior and access as well as underlying conditions. Administrative closure is a process field, not a direct observation of first response or resolution. [3] [10]'),
  ('p','Agent demonstrations may benefit from examples exposed by tool discovery, while development fixtures make difficult cases unusually legible. Final questions should test unseen combinations and realistic ambiguity. Engine metrics that approximate percentiles must retain that approximation rather than borrowing the fixture engine\'s exactness. [2] [3]'),
  ('h','Conclusion'),
  ('p','The implemented service makes the analytical specification and selected population durable objects. The recorded fixture demonstrates how this protects rates, missingness, coverage and full exports. Its research value lies in a reproducible architecture and falsifiable evaluation plan; broad conversational and physical-scale claims remain tied to future measured evidence.'),
 ]},
},
'03-semantic-discovery': {
 'refs':[
  ('Pfitzmann et al. (2022). DocLayNet: A Large Human-Annotated Dataset for Document-Layout Analysis. KDD; arXiv:2206.01062.','https://arxiv.org/abs/2206.01062'),
  ('Auer et al. (2024). Docling Technical Report. arXiv:2408.09869.','https://arxiv.org/abs/2408.09869'),
  ('Project query, release and evidence contracts','docs/implementation-contract.md'),
  ('Frozen evaluation protocol','eval/protocol.md'),
 ],
 'formal': {'title':'1. Research framing and information scope','blocks':[
  ('p','DocLayNet addresses document-layout diversity with human-annotated pages across varied sources. Its motivation is relevant because success on a narrow family of manuals does not establish robustness to other layouts. Docling combines specialized layout and table models in a document-conversion toolkit. These are research precedents and possible comparators; the current VOPT implementation uses PyMuPDF, RapidOCR and explicit rules. [8] [9] [1]'),
  ('h','Formal extraction and release objects'),
  ('p','Represent an extracted assertion as a=(d,r,m,v,t,x,u,k,e): document, revision, model, variant, attribute type, value/range, unit, condition and evidence. A candidate is not a full technical fact unless its scope and condition are supported. Let R_pi(A) be the approved release under policy pi; discovery receives only C=R_pi(A), not A or the source PDFs. [1] [10]'),
  ('code','coverage profile: document/model + reviewed attribute presence\nvalues profile: coverage + approved values/units/conditions\nsearch(q,C): validate q; apply exact predicates; rank scopes\nexplanation(result): use released catalog fields only'),
  ('p','The key boundary can be stated as an invariance property: for two private workspaces producing the same released catalog C, a deterministic discovery query q must return the same result. This is a proposed formal interpretation of the implemented isolation tests. It constrains hidden use of OCR or private values, while not claiming a proof against every side channel. [5] [7]'),
  ('h','Research questions'),
  ('p','RQ1 asks whether complete model-attribute-value-condition assertions can be extracted reliably from representative scans. RQ2 asks whether approved metadata satisfies discovery needs with hard-constraint correctness. RQ3 asks whether release changes remove information from all search paths. These require separate denominators: excellent retrieval cannot repair incorrect extracted facts, and deliberate policy omission is not an extraction error.'),
 ]},
 'algorithm': {'title':'3. Scoped extraction and query evaluation','blocks':[
  ('p','The pipeline uses page geometry and local OCR, then applies model/header and unit rules. Per-page state distinguishes processed, failed and unknown material. Evidence review is bound to source and extraction fingerprints so that a prior decision cannot silently approve changed source bytes. [1] [7] [10]'),
  ('code','for each admitted document revision:\n  verify source identity; process bounded pages/checkpoints\n  recover text/layout; retain page and region coordinates\n  emit candidates only with supported model/attribute scope\n  normalize units without changing physical attribute role\n  record original candidate plus explicit review events\nexport only approved policy fields as a versioned bundle\nimport atomically into the source-free discovery database'),
  ('h','Conjunction is not a document-level keyword join'),
  ('p','For a model scope s, a conjunctive request requires all predicates to have compatible support in that scope. A document containing model A at 230 V and model B at 2 kW cannot automatically satisfy a request for one model having both properties. Operating conditions must also align. Discrete alternatives are not continuous ranges, and an unresolved qualifier prevents an unjustified positive match. [1] [3] [10]'),
  ('code','match(s, q1 AND q2) requires compatible support for both\nunknown attribute -> unknown; not zero and not false\ncoverage-only + numeric constraint -> unsupported\nambiguous physical role -> clarify before ranking'),
  ('p','Ranking is downstream of these constraints. A lexical or semantic similarity score may order valid scopes but cannot override an unsupported numeric predicate. This preserves meaning even when user language is abbreviated. The guided UI compiles the same query contract rather than maintaining a separate permissive search path. [3] [4]'),
  ('p','Pipeline cost separates page rendering/OCR, extraction, review and metadata indexing. Synthetic catalog timings measure the last stage only. A deployment claim should specify page count, scan resolution, layout, OCR engine, retry policy, memory and review effort rather than scaling catalog-query speed into document throughput.'),
 ]},
 'evaluation': {'title':'6. Proposed independent evaluation','blocks':[
  ('note','PROPOSED STUDY. Independent labels and untouched families are a prospective validation design. Existing development matches and agent reviews must not be reused as final-test evidence.'),
  ('table',['Track','Unit and reference','Measure'],[
   ['Extraction','Complete source-supported assertion; exhaustive human annotation','Precision/recall including model, variant, unit and condition'],
   ['Evidence location','Page/region supporting the full assertion','Localization correctness and review time'],
   ['Reference catalog search','Independent queries and adjudicated relevant scopes','Recall@k, reciprocal rank and hard-constraint errors'],
   ['Extracted catalog search','Same queries with reviewed and automatic conditions separated','Downstream loss attributable to extraction'],
   ['Release lifecycle','Fixed-source catalogs under downgrade/withdrawal/rollback','Invariance, removed-field and stale-index checks'],
  ],[125,223,140]),
  ('p','Partition manuals by equipment family and related edition before tuning. Independent annotators should capture all supported assertions in sampled pages, including negative and ambiguous cases, rather than selecting only promising leads. Adjudicate component identity, rating and conditions. Freeze queries and threshold choices before opening final families. [7] [11]'),
  ('p','Use exact-match scoring on the full assertion tuple, with separately reported numeric transcription and unit normalization diagnostics. For retrieval, labels must distinguish information in the original manual from information actually released by a profile. Compare lexical and semantic rankers on the same candidate scopes and hard constraints; use paired query-level uncertainty estimates and report unjudged results.'),
  ('p','Operational validation should cold-start on an actual target with networking unavailable, original sources inaccessible to discovery and packaged model assets verified. Inject interruption, changed-source, malformed import, downgrade and revocation events. Measure review effort against manual cataloging at comparable factual quality before claiming labor reduction.'),
 ]},
 'roadmap': {'title':'7. Roadmap and scientific interpretation','blocks':[
  ('table',['Phase','Output','Decision rule'],[
   ['Qualify diversity','Rights-qualified corpus stratified by layout, scan and model scope','Freeze representative families and excluded rights cases.'],
   ['Create independent references','Exhaustive assertions, relevance labels and adjudication','Keep human and agent provenance separate.'],
   ['Run controlled studies','Raw/reviewed/reference extraction-search comparisons','Choose methods by full-scope quality and effort.'],
   ['Qualify deployment','Target-machine offline lifecycle and package inventory','Reproduce exact scope and failure behavior.'],
  ],[112,228,148]),
  ('p','The implementation already supports private extraction, review, controlled release and metadata search. The proposed roadmap expands its research qualification. A future local model should be introduced only when measured rule failures justify its cost, with the same evidence and release constraints. The current TF-IDF comparator provides no basis for claiming pretrained semantic retrieval benefits. [1] [3]'),
  ('h','Threats to validity'),
  ('p','The historical equipment corpus is narrow, and every family was inspected during development. Agent-selected leads favor observable fields and do not exhaustively enumerate source facts. Damaged pages create unknown coverage. Corrected review records improve a catalog but change the estimand: retrieval over reviewed data is not raw extraction accuracy. [2] [3]'),
  ('p','Policy itself affects relevance. A manual can contain a value that discovery correctly refuses to expose. Scoring that refusal as retrieval failure would conflate intended information control with an engineering defect. Conversely, a high search score cannot authorize release of a private field. Evaluation should therefore report both source relevance and profile-visible relevance.'),
  ('h','Conclusion'),
  ('p','VOPT demonstrates an offline workflow in which source interpretation and disseminated discovery are distinct, auditable stages. Development evidence shows why full technical scope, not numeric transcription alone, is the appropriate research unit. The next scientific step is independent, family-separated evaluation of that unit and its effect on document discovery.'),
 ]},
},
'04-org-knowledge-graphs': {
 'refs':[
  ('Prabhakaran and Rambow (2014). Predicting Power Relations between Participants in Written Dialog from a Single Thread. ACL, pp. 339-344.','https://aclanthology.org/P14-2056/'),
  ('Guo et al. (2017). On Calibration of Modern Neural Networks. ICML; arXiv:1706.04599.','https://arxiv.org/abs/1706.04599'),
  ('Implemented conservative inference baseline','orggraph/inference.py'),
  ('Corpus qualification and evaluation research','research/data-and-evaluation.md'),
 ],
 'formal': {'title':'1. Research framing and relation types','blocks':[
  ('p','Prabhakaran and Rambow study power relations between participants in written dialog. That task motivates language-based authority signals, but relative power within an interaction is not identical to a direct reporting edge. This prototype explicitly separates contextual approval authority, direct reporting, formal membership and communication communities. [6] [8]'),
  ('p','Guo et al. distinguish classification scores from calibrated probabilities of correctness and evaluate post-processing calibration. Their work is a methodological reference, not evidence that temperature scaling applies automatically to this heuristic graph baseline. Calibration must be fitted and evaluated on labels representative of the relation, selection rule and target population. [9]'),
  ('h','Formal target'),
  ('p','Let P be people, M observed messages and A_s attributed source assertions. The inference target is a set of candidate directed relations R subset of P x Types x P with evidence and temporal scope. A selected primary reports_to edge is a separate projection, not the complete set of candidates. The system may leave a person unresolved. [2]'),
  ('code','Candidate: (subject, relation, object, score, evidence, time)\nOrigin: source | model | analyst\nReview: unreviewed | accepted | rejected\nSelection != truth; raw score != calibrated probability'),
  ('p','The main research question is whether communications support useful direct-report reconstruction under partial labels and domain transfer while preserving uncertainty. A second question concerns exploration: can all relevant people and claims remain reachable without requiring an unreadable global layout? These questions need separate evidence; browser navigation cannot validate manager accuracy.'),
  ('note','Proposed inference estimand: correctness of selected direct-manager edges at a declared time among people with independently verified labels, alongside selection coverage and abstention. Relative authority and team membership require their own labels.'),
 ]},
 'algorithm': {'title':'3. Conservative baseline in detail','blocks':[
  ('p','The implemented baseline caps behavior-only scores below the default selection threshold. Let f and r be eligible directional interaction counts, s=f/max(1,total outgoing), and rho=min(f,r)/max(1,f,r). Its communication score is the following deterministic heuristic; the coefficients are implementation choices, not learned or calibrated parameters. [10]'),
  ('code','b = 0 when there are no eligible pair records; otherwise:\nb = min(0.52, 0.08 + 0.20*s + 0.14*rho\n               + 0.10*min(1, log(1+f+r)/log(11)))'),
  ('p','An explicit sender self-report gives a higher candidate score based on distinct claim text and interaction count, capped at 0.96. A contradictory negated report caps the score at 0.30. Quoted text is conservatively excluded from sender claims. Approval requests produce a separate higher_authority_than relation rather than a direct-manager score. [10]'),
  ('code','rank candidates per person by score, then stable ID\nselect a primary candidate only if:\n  no explicit contradiction\n  highest score >= 0.55\n  highest score - second score >= 0.08\n  dated-view requirements are satisfied\notherwise retain the person with an unresolved reason'),
  ('p','A useful consequence follows directly: pure communication behavior cannot exceed 0.52, so under the default 0.55 threshold it cannot independently select a manager. This intentionally favors abstention over converting frequent contact into formal authority. The reported number of selected links therefore reflects the designed evidence profile of the synthetic corpus, not an empirically calibrated confidence level. [10]'),
  ('h','Sparse structure and display cost'),
  ('p','Candidate generation retains each person\'s top eight observed communication contacts plus all explicit positive/negative reporting targets, instead of evaluating every person pair. If C is the retained candidate set, scoring work is tied to messages and C rather than an unavoidable dense |P|^2 matrix. The browser separately bounds its local scene. Actual throughput still depends on communication density, parsing and storage. [1] [2] [10]'),
 ]},
 'evaluation': {'title':'6. Proposed inference and user study','blocks':[
  ('note','PROPOSED STUDY. The synthetic implementation evidence is not a substitute for independently labeled organizations or transfer validation. The following is the planned research design.'),
  ('table',['Question','Design','Evidence to report'],[
   ['Direct-report reconstruction','Partial-label source organization; held-out people/time blocks','Candidate recall, selected precision, coverage and abstention'],
   ['Authority versus reporting','Separate labels for contextual power and direct management','Relation-specific errors and confusion'],
   ['Calibration','Fit on validation labels; assess untouched matched scope','Reliability curves, Brier score and calibration error'],
   ['Transfer','Freeze model before different organization; acquire audit labels','Domain shift, errors and applicability limits'],
   ['Exploration utility','Counterbalanced analyst tasks with bounded versus baseline views','Correct answers, active time, navigation and frame-time traces'],
  ],[119,221,148]),
  ('p','A transfer corpus with no labels can test operability, but cannot establish accuracy or calibration by itself. Obtain an independent audit sample before making those claims. Keep departments or temporal blocks together where leakage through repeated correspondents would inflate performance. A communication edge is not an independent observation if many edges arise from the same person or thread. [11]'),
  ('p','Compare at least a communication-only baseline, explicit linguistic baseline and a learned candidate when data justify it. Select thresholds on validation data, then report risk versus coverage on the untouched test set. Calibration should target the selected edge distribution, not merely arbitrary candidate pairs; abstention changes that distribution.'),
  ('p','For the interface, preserve information equivalence across conditions and randomize task order. Measure correctness of evidence-based answers before time savings. Record viewport, browser, graph density, network and hardware; reachability and closure tests remain correctness checks, while frame time and analyst effort are separate empirical outcomes.'),
 ]},
 'roadmap': {'title':'7. Roadmap and limits of inference','blocks':[
  ('table',['Phase','Output','Decision rule'],[
   ['Qualify relations and data','Authorized corpora with explicit direct-report/time labels','Separate authority, membership and influence targets.'],
   ['Train and calibrate','Frozen feature/model selection and matched calibration split','Compare quality at stated selection coverage.'],
   ['Transfer and review','Independent target audit and reversible identity/membership review','Retain uncertainty where evidence is insufficient.'],
   ['Evaluate exploration','Density-aware browser tests and analyst study','Claim navigability, performance and utility separately.'],
  ],[109,228,151]),
  ('p','This extends an existing local workbench. Identity reconciliation and richer review can change graph topology, so later evaluations must bind both model and identity-decision versions. Exported histories should keep original evidence and analyst interventions distinguishable, enabling a study of whether corrections improve subsequent inference rather than merely altering a displayed chart. [2] [7]'),
  ('h','Threats to validity'),
  ('p','The present generator shares authored organization structure and language templates with its labels. Label exclusion prevents direct input leakage, but it does not create an independent distribution. Explicit self-reports are unusually clean compared with real archives. Selection totals therefore demonstrate conservative behavior under the fixture design, not performance on a workforce. [4]'),
  ('p','Storage benchmarks use source-only hierarchies and seven warm reads. Their p95 equals a small-sample order statistic and should not be interpreted as a service-level guarantee. Conversely, a graph that renders rapidly may still communicate unjustified certainty. Unresolved nodes, origin labels and evidence access are part of the scientific meaning of the interface. [3] [5]'),
  ('h','Conclusion'),
  ('p','The prototype connects conservative typed inference with a durable, navigable evidence workbench. Its implemented abstention policy and bounded display provide a concrete basis for testing reconstruction and analyst utility. The scientific claim remains feasibility and inspectability on authored data, with real inference quality reserved for the proposed labeled study.'),
 ]},
},
'05-graphrag-discovery': {
 'refs':[
  ('Edge et al. (2024; revised 2025). From Local to Global: A Graph RAG Approach to Query-Focused Summarization. arXiv:2404.16130.','https://arxiv.org/abs/2404.16130'),
  ('Moreau and Missier, eds. (2013). PROV-DM: The PROV Data Model. W3C Recommendation.','https://www.w3.org/TR/prov-dm/'),
  ('Implemented exact vectors and rank fusion','graphrag_discovery/vectors.py'),
  ('Research comparison and resource evaluation design','research/data-and-evaluation.md'),
 ],
 'formal': {'title':'1. Research framing and temporal model','blocks':[
  ('p','Edge et al. introduce GraphRAG for query-focused summarization over large text collections, using graph-derived organization to address corpus-level questions. The present implementation is a different, narrower design: evidence-level lexical/vector seeds, bounded relationship expansion and temporal baseline comparison. It does not implement or reproduce community-summary quality results from that work. [8] [2]'),
  ('p','W3C PROV-DM distinguishes entities, activities, derivations, revisions and invalidation. Those distinctions motivate keeping original source versions, extraction activities and later withdrawal separate. The application\'s contract is project-specific; this correspondence is a conceptual comparison rather than a PROV interoperability claim. [9]'),
  ('h','Formal eligibility'),
  ('p','Let an assertion a have source revision d, exact span e, modality m, validity interval [v_start,v_end), and publication time k. A query specifies knowledge cutoff K and optional world time t. Eligibility first requires the assertion and relevant source state to be queryable at K; strict event-time support additionally requires a known interval containing t. Preparation is not publication. [2] [7]'),
  ('code','E(K,t) = eligible evidence under knowledge K and world time t\nknowledge change: compare E(K1,t) with E(K2,t)\nworld comparison: compare E(K,t1) with E(K,t2)\nwithdrawal: change in support; not proof of a world event'),
  ('p','The notation abstracts the implemented event history rather than replacing its full schema. Open-ended validity means no stated end, while unknown bounds require different handling. Planned modality remains planned when a date passes. Comparing rankings alone is insufficient because a relationship can retain support while moving out of top-k results. [2] [3]'),
  ('note','Research hypothesis: bounded graph expansion may improve source-supported discovery for relational questions under a fixed resource budget. Temporal correctness is an independent prerequisite, not evidence that the hypothesis is true.'),
 ]},
 'algorithm': {'title':'3. Retrieval and comparison algorithms','blocks':[
  ('p','Dense retrieval uses exact cosine on normalized finite vectors. Hybrid retrieval combines dense and positive lexical ranks using reciprocal-rank fusion with constant 60. Stable IDs break score ties. These details are verified in the implementation rather than inferred from a generic GraphRAG description. [10]'),
  ('code','cosine(q,x) = dot(normalize(q), normalize(x))\nRRF(x) = sum over available channels j of 1/(60 + rank_j(x))\nchannels = dense rank, positive lexical rank\neligibility -> scoring -> bounded seeds -> graph expansion'),
  ('p','Filtering before scoring prevents future or ineligible evidence from shaping the result pool. Exact query scoring costs O(Nd) vector work over N eligible precomputed vectors of dimension d, before sorting and graph expansion. Index construction additionally includes model embedding generation. Limits on items, dimensions and scalar cells are admission guardrails, not measured throughput. [2] [10]'),
  ('h','Baselines are scoped objects'),
  ('p','A saved-findings baseline retains selected source lineages and assertions. A neighborhood baseline retains fixed entity seeds and radius. Reconciliation revalidates the baseline scope independently of current top-k ranking. Paired citations explain corrections or lost support; the export preserves before and after evidence rather than writing only an uncited change label. [2] [7]'),
  ('code','load baseline query, scope and snapshot\nproject eligible before and after endpoint states\nmatch tracked lineages / explicit supersession / fixed seeds\nclassify source revision, new support, correction, withdrawal\nretain unresolved exclusive-group disputes\nexport paired original spans, hashes and scope limits'),
  ('p','Endpoint comparison can miss a change that occurs and reverses between endpoints. It should not be presented as an exhaustive event ledger. This is why the authored demo compares conflict and withdrawal snapshots separately. A future resumable ledger enumeration needs its own completeness and cumulative-budget contract. [2]'),
 ]},
 'evaluation': {'title':'6. Proposed retrieval and temporal study','blocks':[
  ('note','PROPOSED STUDY. The design below evaluates quality and scale beyond the small fixture and local-model smoke. No graph-over-baseline improvement is asserted.'),
  ('table',['Experiment','Control','Primary outcome'],[
   ['Lexical / dense / hybrid / graph','Same corpus, eligible time scope, model and resource budget','Relevant supported findings and ranking'],
   ['Temporal updates','Independent event/availability/receipt annotations','Future leakage, modality and change classification errors'],
   ['Extraction','Human-labeled mentions, relations, scope and dates','Full assertion quality, abstention and identity errors'],
   ['Graph expansion ablation','Seed-only versus bounded hops, matched evidence budget','Incremental relevant discoveries per added cost'],
   ['Operational scale','Increasing sources, revisions, degree and vector dimensions','Latency, memory, indexing/update cost and completeness'],
  ],[139,207,142]),
  ('p','Freeze questions by relation type and difficulty, separating local fact lookup, multi-hop dependency and baseline-change tasks. Split related document families and revisions together so that near duplicates do not leak labels across development and test. Annotators should judge source-supported relevance, temporal eligibility and identity separately. [11]'),
  ('p','Report precision/recall of supported discoveries within declared candidate scope, citation-span correctness and the rate of unsupported temporal transitions. Assess rank quality only on judgments with adequate coverage; unknown relevance cannot be silently treated as a negative. Pair query-level differences across retrieval variants and include confidence intervals clustered by source family where appropriate.'),
  ('p','Measure query and ingestion costs together. Graph construction can move work from query time to preprocessing, while updated histories require invalidation and reindexing. Compare systems under a fixed measured budget and report failures or truncation. A negative graph result remains informative if the strongest non-graph baseline and resource scope are documented. [1] [11]'),
 ]},
 'roadmap': {'title':'7. Roadmap and validity of discovery','blocks':[
  ('table',['Phase','Output','Progression criterion'],[
   ['Qualify corpus and time','Versioned public sources and independent temporal/relevance labels','Separate world events from publication and receipt.'],
   ['Complete comparison semantics','Resumable event ledger and cumulative resource accounting','Demonstrate declared scope completeness or explicit truncation.'],
   ['Resolve and review identities','Versioned reversible identity/assertion decisions','Retain originals and prevent silent historical rewriting.'],
   ['Evaluate retrieval and scale','Paired baselines, temporal audit and measured cost curves','Publish useful positive or negative results within scope.'],
  ],[117,221,150]),
  ('p','The existing application is In progress. These phases extend its inspectable local reference implementation rather than promise a medium- or large-scale outcome. Approximate indexes or another database should follow a measured bottleneck and be evaluated against the exact reference, including update and cutoff behavior. [2]'),
  ('h','Threats to validity'),
  ('p','The pump fixture assumes explicit exclusivity and exact entity names. Real contradictions require more than similar relation text, and mention-scoped IDs can fragment repeated entities. Exact quotation prevents fabricated spans but not misinterpreted relations. The local smoke uses simple sentences and a decoder model for embedding plumbing, so it cannot estimate extraction or semantic retrieval quality. [3] [5]'),
  ('p','Historical replay also requires care: a later vector artifact over retained source text can be cutoff-safe without reproducing the model or index that actually existed at that historical time. Model identity, pooling, source versions and index fingerprints must therefore accompany a comparison. Display animations illustrate returned support; they do not reveal a model\'s internal reasoning. [2] [5]'),
  ('h','Conclusion'),
  ('p','The implementation demonstrates temporally scoped discovery with inspectable source history, explicit plans and corrections, saved baselines and local inference integration. Its research contribution is an executable framework for asking whether graph assistance adds useful discovery under measured constraints. The answer must come from the controlled evaluation rather than the visual appeal of a graph.'),
 ]},
},
}

def extend_papers(papers):
    """Compose ten substantive pages while preserving existing evidence citations."""
    for p in papers:
        p['refs'][0]=(p['refs'][0][0],'IMPLEMENTATION.md')
        p['title']={
            '01-sensemaking':'Evidence-bounded organizational sensemaking',
            '02-311-analytics':'Reproducible agentic analytics for civic records',
            '03-semantic-discovery':'Offline discovery from technical-document metadata',
            '04-org-knowledge-graphs':'Evidence-aware organizational graph inference',
            '05-graphrag-discovery':'Temporally grounded graph-assisted discovery',
        }[p['slug']]
        e=RESEARCH[p['slug']]
        p['refs'].extend(e['refs'])
        old=p['pages']
        old[1]['title']='2. Method and implemented architecture'
        old[2]['title']='4. Worked example'
        old[3]['title']='5. Recorded results and interpretation'
        last=old[4]
        last['title']='8. Reproducibility and research record'
        last['blocks']=[b for b in last['blocks'] if b[0]!='refs' and not (b[0]=='h' and b[1]=='Evidence-linked references')]
        last['blocks'].extend([
            ('h','A reproducible research record'),
            ('p','The public nested project source contains implementation, documented contracts and retained development evidence. The publication evidence manifest records SHA-256 fingerprints for each local source cited in this paper. External references link to primary publications or official technical documentation, verified for this edition.'),
            ('p','A future rerun should record the exact commit, dependency/runtime identities, input hashes, configuration and environment, plus each attempt and its outcome. Keep generated outputs separate from source and mark any changed implementation as a new condition. Reproduction of a software check does not automatically reproduce a model judgment, benchmark distribution or independent human label.'),
            ('h','Authorship and project status'),
            ('p','Boomer Rawlings developed this work individually after the original submission and grading dates. The current project is In progress. The implemented methods and recorded observations in this paper are separated from the explicitly proposed research protocol and roadmap. No group-project, graded-submission or completed-research claim is made.'),
        ])
        refs={'title':'References','blocks':[
            ('p','Repository references identify the evidence used for the implementation and result claims. Primary literature supports the research framing; its published results are not attributed to this project.'),('refs',),
        ]}
        p['pages']=[old[0],e['formal'],old[1],e['algorithm'],old[2],old[3],e['evaluation'],e['roadmap'],last,refs]
