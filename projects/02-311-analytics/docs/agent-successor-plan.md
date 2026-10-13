# Bounded agent successor plan

**Status: proposed only; no successor implementation, question authoring, model
calls or experiment launch authorized by this document.** The completed study
remains **1/120 overall passes, 0/9 chained passes and 52 timeouts**. Preserve its
candidate, grades and all original evidence. This plan authorizes no new checkout,
dataset, model, package copy, cleanup or drive transfer.

## Evidence and diagnosis

The [completed summary](../examples/evidence/agent-campaign-38084773557/result-summary.json),
[final review](../examples/evidence/agent-campaign-38084773557/final-review.json) and
[diagnostics](../examples/evidence/agent-campaign-38084773557/actual-diagnostics.json)
establish 56 terminal answers, 64 missing finals, 11 repeated-invalid-call failures
and eight automatic numeric-evidence failures. Separate AI reviewers flagged
unsupported claims or false completion in 32 trials; these categories overlap.
Whole-trial median was 126.159 seconds, including failed attempts; it is not
successful-answer latency. Backend qualification does not establish agent quality.

Observed failures identify specific repair targets:

| Evidence | Demonstrated problem | Proposed repair hypothesis |
|---|---|---|
| [Q01-r1](../examples/evidence/agent-campaign-38084773557/replica-1/agent-v1/Q01-r1.json) | Returned whole-corpus count for a borough/month; invented result/export IDs. | Bind every factual answer and artifact claim to completed tool results and verified scope. |
| [Q17-r2](../examples/evidence/agent-campaign-38084773557/replica-2/agent-v1/Q17-r2.json) | Geography matched, but wrong time/category cohort was described as the requested cohort. | Validate requested constraints against the executed specification before answering. |
| [Q36-r2](../examples/evidence/agent-campaign-38084773557/replica-2/agent-v1/Q36-r2.json) | Unsupported first-response request became closure analysis for the wrong month, then false coverage clarification. | Explicit metric capability checks and deterministic calendar resolution. |
| Aggregate diagnostics | Timeouts, invalid calls and no successful chains. | Smaller validated planning stages, bounded repair and concise discovery may reduce avoidable calls. |

These are hypotheses, not proven causes or predicted improvements. The archive
does not isolate model capacity, prompting, context size, adapter design or CPU
speed. More time alone would not repair wrong cohorts or unsupported claims.

## Development budget and freeze

After separate authorization, reuse the **same pinned Qwen3-1.7B weights, existing
2,133,268-record corpus, official boundaries and runtime**. Change only the adapter,
planning/validation and evidence-bound answer construction. Keep agents replaceable;
do not encode benchmark IDs, answers, borough-specific shortcuts or question lookup.
Preserve administrative-closure and observed-snapshot limitations.

Budget: **two development revisions, at most 24 model trials total**, and two hours
of model/server wall time including startup. Before revision one, select 12 exposed
development tasks: four chains, three multi-condition analyses, two ambiguity
cases, two unsupported requests and one map/CSV task. The old 40 questions are now
development material only. Added synthetic development cases must be labeled and
included in the exposure ledger. Re-execute a development task only against a
changed candidate with its concrete repair reason recorded; no original-matrix rerun.

Use synthetic fixtures for focused validation tests. Keep the existing 120-second
request, 160-second trial and 24-call ceilings; a rejected or timed-out answer still
fails. One revision advances only with at least 11/12 combined passes, all four
chains passing and zero unsupported claims or false completion. If neither revision
passes, stop and publish the development failure; do not buy a larger model, extend
budgets or consume new held-out questions.

Freeze one passing candidate before any successor questions are selected: source,
prompt, tools, weight/runtime hashes, model settings, timeouts, reference evaluator,
rubric, resource plan and acceptance gates. Retain both development revisions;
report the selection procedure. A freeze is prospective registration, not a result.

## Genuinely untouched successor questions

Use a separate question author/custodian with no role tuning the candidate. They
receive the capability contract, corpus metadata and the complete development
exposure ledger; developers receive no candidate questions, expected answers or
item-level scores. **Do not generate the questions now.** After the candidate
freeze, the custodian selects 40 new questions: 20 analyses, six chains, four
ambiguities, four unsupported requests, three coverage cases and three adversarial
requests. Analytical cases must include temporal, geographic, grouped-statistic and
artifact obligations. No question may require acquiring more data.

Deduplicate against all original 40 questions, demos, documentation examples,
synthetic development cases and exposed tests. Record normalized-text comparisons
and a manual semantic comparison of each item's intent, constraint structure,
operation sequence, ambiguity and expected response. A borough/date/category
substitution, paraphrase or reused sequence with different constants is a duplicate.
Reusing necessary backend primitives is allowed; copying the same task template is
not. A second reviewer verifies novelty and solvability before sealing the set.
If 40 defensibly distinct supported tasks cannot be authored, stop; do not silently
fill the set with template variants.

Store questions and independently computed oracle outputs outside developer/agent
accessible paths, with access controls, hashes, custody log and a timestamped sealed
manifest. Use existing data read-only. Separate reviewers validate oracle scope,
counts, IDs and limitations without changing the candidate. The runner receives one
question at a time and never receives oracle answers. Log every disclosure. A leak
before the first trial retires the entire set to development and requires a new
registered set; a leak after launch terminates the study as contaminated. Do not
replace selected failures or splice unaffected trials into a passing report.

“Untouched” means unexposed to successor development and answering contexts. It
cannot establish absence from model pretraining. AI authors/reviewers remain
AI-assisted evidence; independent human gold requires actual human labels and
adjudication. Disclose roles and overlaps rather than claiming human independence.

## One successor evaluation; fixed stopping gates

Subject to later launch authorization, execute **40 × 3 = 120 trials once**, fresh
contexts, seeds 101/202/303, on one reserved host sequentially. Interleave repetitions
in a preregistered order; preserve per-trial timing and cache state. No model or
grader changes after exposure. Retain every failed, missing and interrupted trial
in the fixed denominator. Stop for resource failure, contamination or invalid
provenance, publishing an incomplete failed qualification; no replacement run is
included in this plan.

Pass requires all of:

- At least **108/120 combined automatic and semantic passes**, at least one pass
  for every question and **17/18 chained passes**. No missing semantic reviews.
- **Zero** fabricated/mismatched numeric evidence, unsupported factual claims or
  false completion. Refusal does not count as success on an answerable request.
- Exact filters, membership and counts; unchanged numeric tolerances; correct
  chaining, citations, requested artifacts and substantive limitations. Reviewers
  judge unscored answers against returned evidence before viewing automatic grades.
- The same quality gates must pass **before** usability is claimed. Preregistered
  interactive target: median at most 30 seconds and nearest-rank p95 at most
  120 seconds across all 120 attempts, with failed/noncompleted attempts assigned
  the greater of 160 seconds or their recorded elapsed time for this acceptance calculation. Also publish raw elapsed
  times, failures, successful-answer latency and their denominators separately.

Startup/download/build time stays separate and visible. Record prompt/cache and
generation time when available, tool/export/map elapsed time, host/process memory
and resource-stop events. No pooled success-only speedup, tail-SLA claim or inference
of causal improvement from a changed question set. This is one bounded successor
qualification, not a head-to-head accuracy comparison with the original benchmark.

## Capacity and storage gate; no launch now

First use of an existing suitable host requires a signed-off inventory, measured
free disk/RAM and exclusive heavy-job reservation. Proposed conservative envelope:
**4 dedicated logical CPUs, 32 GiB total RAM, at least 20 GiB available before
startup**, and all required existing model/data/index/runtime assets present and
hash-matched. This is a budget, not a measured minimum. Current low free RAM does
not qualify. Missing assets or a required reindex/model build need a separately
approved plan; do not acquire or duplicate them under this plan.

Allow **4 GiB additional disk**: traces/reports 1 GiB; bounded exports/Maps artifacts
1 GiB; application database journals 512 MiB; scratch 512 MiB; one final evidence
archive 1 GiB. Backups, raw-data copies, model copies and database rebuilds: **0**.
Keep at least **8 GiB free beyond this budget** (12 GiB free at start). Open the
existing oracle read-only; any unexpected journal/rebuild requirement stops work.
The proposed ceilings must be enforced before output creation, not by deleting
evidence afterward. Keep originals; archive creation is budgeted separately.

Reserve at most **eight host-hours** for the successor run, including one metadata
warmup of at most 900 seconds; unchanged per-trial ceilings bound inference to
5 h 20 min. No concurrent inference, ingestion, packaging or sibling heavy jobs.
Sample available RAM/disk during execution; stop owned work if available RAM falls
below 4 GiB, free disk falls below 8 GiB or an output cap would be exceeded.
Report the exact shortfall and retained evidence, then continue lightweight
analysis. No denied-cleanup retry, drive move or budget increase is implicit.
