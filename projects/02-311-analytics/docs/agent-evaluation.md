# Actual agent evaluation

The executable evaluator freezes 40 prospective questions and independently
calculated answers, then asks a real local model each question three times with
fresh conversation contexts. The adapter supplies dataset discovery before each
question; the model chooses every analysis, query argument and artifact request
through the seven tools. This is not prewritten AnalysisSpec replay. The questions are **AI-authored**,
not independent human-held-out labels or evidence of generalization to arbitrary
users. Executing 120 trials and passing the acceptance threshold are separate facts.
The protocol cannot establish that questions were absent from model pretraining.

## Prospective operational-eligibility amendment

Before any held-out trial, the execution prerequisite was amended on October 10,
2026 (UTC). The frozen 1.7B candidate can execute the study despite failing its
development count question. Development run
[38028703734](https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/38028703734)
returned an unnecessary clarification after inventing restrictions. Its retained
summary remains `passed:false`: no correct count, numeric evidence, result citation
or synthetic-data disclosure. Startup took 163.584 seconds; the question took
59.404 seconds. Server counters show 7,306 cached tokens on the first question
request. These measurements establish execution and cache reuse, not answer quality.

Operational eligibility binds that exact failed run, commit and artifact to the
current application/adapter/evaluator hashes, model/runtime pins, native build
flags, fixed 160-second trial/120-second request/24-call limits, actual tool-call
trace and successful metadata-only warmup. The warmup request must match the
recorded discovery via the shared public prefix builder. The receipt records
`eligible_to_execute:true`, `quality_qualified:false`, the original failed checks,
and hashes of every retained artifact file. The run's failure conclusion and full
trace remain evidence. This replaces the previous requirement that the authored
development count question pass before any research trials could begin.

No model, adapter, question, oracle, grading threshold or runtime setting changes
accompany this amendment. All 120 attempts remain required; failed/missing trials
remain in the denominator. The 90% automatic threshold, at least one pass for every
question, numeric grounding and independent semantic review remain unchanged.
No tuning of this candidate is permitted after held-out exposure. A completed
negative study is an executed evaluation, never a qualified agent release.

Files: [questions](../examples/evaluation/questions-v1.json),
[local model adapter](../tools/local_agent.py),
[freeze, execution and automatic grader](../tools/agent_evaluation.py),
[focused implementation checks](../tests/test_agent_evaluation.py).

## Corpus and oracle

Use the frozen April 1–November 1, 2025 observed corpus, at least two million unique
real requests, and the pinned official NTA2020 boundaries. Comparison questions use
June and October, including their unequal 30/31 calendar-day denominators. The
catalog must expose `residential_nta2020` with exactly the 197 residential codes from
[the official boundary receipt](../examples/evidence/official-nta2020-26b.json).
Parks, airports and other special areas are not silently called neighborhoods.

`prepare` requires an immutable Elasticsearch manifest, matching normalized-input
hash/count, official boundary hash, and valid frozen-index comparison qualification
whose provenance reaches the actual reconciled public capture. A reconciled
observed corpus retains its population/transactional-completeness limitations;
`coverage.complete` need not, and must not falsely, become true. The explicit
`--development` flag permits implementation checks but stamps the freeze as
ineligible for real-data acceptance.

The reference database is a disk-backed SQLite projection of the normalized
corpus, with a primary key enforcing exact unique request IDs. Its SQL evaluator
does not import the application's contracts, compiler, fixture executor, or
aggregation helpers. It independently evaluates filters, geography, local calendar
buckets, counts, closure means/percentiles and period comparisons. It computes
exact sorted ID hashes, geolocated counts and full grouped answers. Chained oracles
select residential NTA codes from the first complete ranking, then compute agency
metrics on those exact codes and the same complaint cohort. Source normalization
and point-to-NTA assignment remain separately qualified inputs, not independently
validated by this SQL calculation.

ID-hash convention: sort distinct `unique_key` values by binary text order; hash
each canonical JSON string followed by LF. Counts must match exactly. Float metrics
use relative tolerance `1e-7` (minimum `1e-8`). Approximate median/p90 tolerances are
fixed before execution at the larger of 0.1 hour or 5% of the reference value;
this is an evaluation tolerance, not a statistical confidence interval. A different
question/oracle or threshold after seeing failures requires a new benchmark version.

## Freeze before model exposure

Provision Elasticsearch/Kibana and a local model server separately. These commands
install nothing and start no services. The adapter uses the
[llama.cpp chat-completions tool protocol](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md),
allows only direct HTTP loopback addresses, rejects redirects and credentials,
and does not use environment proxy settings. Pin model/runtime checksums in the
deployment evidence; the protocol-visible model alias alone cannot prove weight
identity.

Real-data freezes also pin the exact bytes and complete contents of
`docs/local-model-runtime.json`, including the model alias/weight hash and native
runtime source commit/CMake flags. The prebuilt archive in that document is the
development comparison artifact; `execution_runtime` defines the selected native
build. Development-only freezes may omit runtime binding.

```text
python tools/agent_evaluation.py prepare --config config/live.json --source data/normalized.jsonl --database data/oracle.sqlite --output runs/agent-freeze-v1.json --model analytics311-qwen3-1-7b

python tools/agent_evaluation.py run --config config/live.json --freeze runs/agent-freeze-v1.json --database data/oracle.sqlite --output runs/agent-evaluation-v1 --endpoint http://127.0.0.1:8080/v1 --seconds 160 --request-seconds 120 --runtime-receipt runs/runtime/agent-runtime-freeze-r1.json
```

The freeze pins question bytes, all runtime Python source, evaluator source,
catalog, manifest, SQLite database, input JSONL hash/count, boundary identity,
expected values and model settings before the first model call. The model receives
only its question, general agent/tool instructions, discovery and actual tool
responses. Expected JSON specs and numeric oracles are never included. All three
repetitions use fresh histories containing only the adapter's metadata prefix and
the new question; fixed seeds 101/202/303 and temperature 0.2
are recorded. A model/server may not guarantee bitwise seed reproducibility.

The frozen adapter uses `discovery-rules-v2` for model context. Discovery retains
every request-building rule verbatim, full catalog/limits/fields, coverage,
qualification, warnings and unknown source text. It omits illustrative complete
requests and repeated workflow guidance; exact duplicate fields/version remain in
the top-level descriptor. Repeated provenance values use JSON Pointer `$ref` links
to identical ancestor data; repeated metadata objects reference earlier unchanged
objects within that response. No questions, expected answers,
or question-specific shortcuts inform this projection. The transcript retains
full original discovery alongside the exact
model-visible JSON string, its SHA-256, byte counts and projection version.
Reduced context bytes alone do not establish faster or more accurate inference.

V2 also omits valid 64-hex audit hashes at these exact metadata paths, where `D`
means `dataset` or one of its direct, recursively nested `provenance` objects:

- `D.sha256`, `D.source_sha256`.
- `D.comparison_qualification.{capture_manifest_sha256,capture_sha256,normalized_sha256,qualification_sha256}`.
- `D.ingestion.{prefix_sha256,source_sha256}`.
- `D.reconciliation.{initial_metadata,final_metadata}.schema_sha256`.

Other values and paths are retained, including malformed hash values, unknown
source text, source URLs, dataset version, NTA version, qualification scope/stage,
population and transaction flags, coverage periods, counts, quality and budgets.
The full tool output remains in the trace. This is context projection, not a
modified certificate or a replacement for evaluator provenance validation.

For subsequent non-error tool results, `matching-dataset-reference-v1` replaces
only `result.dataset` with `{"$ref":"tool:adapter_discovery#/dataset"}` when its
complete canonical JSON exactly equals the original bootstrap dataset. That
cross-tool reference points to the adapter's already supplied dataset context.
Different, changed or missing datasets remain untouched; Boolean/integer and
integer/float distinctions cannot match accidentally. Every affected event keeps
the full original snapshot and its hash, plus exact projected content, hash and
byte counts. Rows, numbers, query specs, coverage flags, warnings and every other
field remain unchanged. The projection does not change service results, saved
artifacts, numeric citation paths or evaluator evidence.

The adapter actually calls `describe_dataset()` before presenting the question.
A deterministic assistant/tool transport envelope places that response in the
tool role after the system instructions and before the user question. Its trace
events explicitly say `initiated_by: adapter`; it is never counted as a model
decision. `adapter_calls` and `model_calls` are separate, and their sum uses the
existing 24-call budget. The model can refresh discovery, but must create analyses
with `run_analysis` before reading their returned IDs with `get_result`.

The complete original descriptor, exact projected model content and both hashes
remain in the trace. Invalid discovery stops the trial before any model request.
Source-injection text remains untrusted tool data. Every trial starts with empty
owned result/export ID sets; no prior answers, queries or question-specific
expectations enter the prefix. The stable prefix permits server cache reuse but
does not prove that reuse or its performance benefit occurred. A discovery-first
ordering check therefore establishes available metadata, not autonomous discovery
by the model.

Tool argument failures include the bounded local tool-envelope schema and fixed
recovery guidance. Initial discovery uses `{}`; an optional `field` must be an
exact name returned by discovery. Error feedback contains neither arbitrary
exception messages nor inferred query arguments. The model chooses every retry.
Invalid terminal JSON gets at most two format-feedback turns per trial; all failed
attempts and exact feedback remain in the trace. These turns share the original
deadline, context and tool-call budgets. Valid final answers are not rewritten,
and numeric grading, evidence ownership and pending-export cleanup are unchanged.

`run_analysis` and `validate_analysis` expose the public AnalysisSpec JSON Schema
in their tool parameters: the exact 16 allowed top-level properties, required
dataset version and operation, recursive Boolean filters, typed operand shapes,
three geometries, time ranges, periods, groups, metrics and output/ranking bounds.
The schema comes from the public contracts and guide, never benchmark questions.
Application validation remains responsible for semantic combinations, coverage,
catalog membership, date ordering, polygon validity and configured budgets.

Rejected top-level argument/spec keys receive bounded, explicit diagnostics;
the adapter does not delete or repair model arguments. The third identical invalid
call with the same tool, arguments and error code ends the trial as a retained
failure. This applies to invalid arguments/specs and foreign result IDs, not
transient backend failures. The public service default is five record-preview
rows; explicit larger previews remain available up to the configured cap. The
SYSTEM instruction directs count-only questions to an ungrouped count aggregation
and requests an explicit small limit when individual records are needed. The
adapter never rewrites analytical arguments or drops returned rows. Exact matching
totals and full CSV membership remain independent of preview size. This prospective
change follows the retained development timeout in
`examples/evidence/model-smoke-38027531995/summary.json`; no held-out question
had been executed. A smaller response is not yet proof of model success.

Before the first model call of each real-data invocation, create a new runtime
receipt after the owned Linux server is healthy. `--runtime-receipt` otherwise
defaults to `runs/runtime/agent-runtime-freeze.json`. Its schema is:

```json
{
  "schema_version": 1,
  "evidence_kind": "pretrial_local_model_runtime",
  "created_at": "UTC timestamp",
  "freeze_sha256": "SHA-256 of benchmark freeze file",
  "runtime_spec_sha256": "SHA-256 of runtime specification file",
  "model_alias": "exact pinned alias",
  "execution_runtime": {"...": "exact object from runtime specification"},
  "endpoint": "http://127.0.0.1:8080/v1",
  "budgets": {"seconds": 160, "request_seconds": 120, "max_calls": 24},
  "owned_server_pid": 123,
  "launch_argv": ["actual argv from /proc/PID/cmdline"],
  "files": [
    {"role": "model", "path": "absolute model path", "bytes": 1, "sha256": "actual file hash"},
    {"role": "server", "path": "resolved /proc/PID/exe", "bytes": 1, "sha256": "actual file hash"},
    {"role": "build_configuration", "path": "actual CMakeCache.txt", "bytes": 1, "sha256": "actual file hash"},
    {"role": "runtime_library", "path": "one entry per mapped .so file", "bytes": 1, "sha256": "actual file hash"}
  ]
}
```

The values above illustrate shape only. Measure every file; collect the complete
`.so` inventory from `/proc/PID/maps`, resolve symlinks and deduplicate paths. Record
the verified source revision and check the actual CMake cache against the pinned
flags during staging. The evaluator rechecks declared file bytes/hashes, model
identity, live PID/executable/argv, mapped-library inventory, endpoint and core
launch settings. This is local process provenance, not remote attestation or
independent proof that a compiler produced the declared source build.

Before contacting the model, the runner writes immutable execution identity and
an immutable copy of that launch receipt. Every trial cites both hashes. Restarting
the server between repetitions creates a new receipt/PID but preserves the stable
execution identity when source/build/artifacts, launch settings and budgets match.
Use a different receipt path for each restart and `--resume` for repetitions 2/3.
PID, timestamp and artifact locations are launch provenance rather than stable
runtime identity; artifact content hashes remain mandatory. Review rejects mixed
execution identities or altered/missing launch receipts. Changing a budget or
model after failures requires a separate declared study, never replacement trials.

The prospective runtime pin now declares `inference.prefix_warmup` with policy
`metadata-prefix-v1`, a 300-second startup bound, seed 0 and one output token.
After runtime identity verification, the adapter makes one metadata-only model
request for each owned-server launch. Its messages are exactly the timed trial's
system, fixed discovery tool-call envelope and actual projected discovery response,
before any user question. Tools, temperature and nonthinking template settings
match normal inference. No question, oracle, analysis or prior result enters this
request. Generated text and tool calls are discarded without execution. Positive
prompt-token usage and at most one completion token are required; malformed or
failed warmup responses stop the campaign before any timed trial.

The immutable `metadata-prefix-warmup-<launch-receipt-sha256>.json` records measured
startup time, exact request/prefix/descriptor hashes and byte counts, server timing
counters, usage and any error. Each trial cites its warmup receipt hash. Startup,
resume and review require exact equality with the expected request, prefix and original/
projected descriptor identities stored during `prepare`; a receipt for different
metadata cannot qualify by merely relabeling its runtime fields. The same pure
builder supplies these identities at freeze and actual startup, without inference.
A resumed same-server segment reuses the receipt; a new server launch requires a new measured
warmup. Failed receipts are retained and never silently retried. Summaries report
startup totals separately from trial latency; all work inside `run_trial`, including
its own metadata discovery, remains under the original trial deadline. The absence
of this explicit runtime policy retains the cold execution path.

This models a persistent local service with separately measured startup. It does
not establish cold-request latency or guarantee cache reuse; inspect actual server
cache counters and wall time. The cold full-schema development failure remains in
`examples/evidence/qwen3-1-7b-development-cold-prefix-failure.json`; its exact old
runtime pin is `docs/local-model-runtime-qwen3-1-7b-cold.json`. No held-out question
had been executed when this startup policy was chosen.

The same prospective pin sets a 24,576-token context and disables context shifting;
the evaluator requires `--no-context-shift` in the owned server's launch arguments.
Pinned GGUF header metadata reports 28 layers, 8 KV heads and 128 dimensions for
each key/value head. With F16 K/V, cache storage alone is estimated at 2.625 GiB,
896 MiB above a 16,384-token context. This excludes weights, compute buffers and
other services and is not a measured capacity guarantee. The header verification
and arithmetic are retained in `examples/evidence/qwen3-1-7b-context-budget.json`.
After warmup and each trial, bounded `/proc/PID/status` reads record the verified
owned process's RSS and process-lifetime VmHWM. These are snapshots and a lifetime
high-water mark, not per-trial peak measurements; missing counters stay unavailable.

Defaults: 300 seconds per trial, 90 seconds per model request, 24 tool calls,
2,048 output tokens per request, 256 KiB serialized request context, 1 MiB model
response, and 8 MiB transcript. The CLI example uses the prospective study's
explicit 160-second trial and 120-second model-request budgets.
The model decides tool arguments; application validation remains authoritative.
Result IDs are confined to that trial. Model reasoning fields are not retained.
When returned, finite numeric llama.cpp prompt/cache/generation timing counters are
retained as `server_timings`; these are server-reported diagnostics alongside the
adapter's measured wall time. Unknown timing fields and textual payloads are dropped.
Unfinished owned exports receive cancellation requests at trial end. Blocking
analytical I/O retains its existing service deadline behavior; the trial deadline
is cooperative between those calls.

`--repetition 1`, `2` or `3` permits separate runner jobs; omit it for all 120 trials.
`--resume` runs only missing trial files after verifying the unchanged freeze and
budgets. Completed failures are never replaced or retried for a better score.
Per-trial transcripts and prior summary snapshots remain immutable. If interrupted
mid-trial before a receipt exists, that attempt is unrecorded and the summary must
not be called a complete 120-trial run. A restarted missing trial has a fresh context.
Merge separate runner jobs by trial identity before interpreting the 120 denominator;
a single 40-trial shard does not satisfy the complete benchmark.

## Scoring and interpretation

Automatic scoring checks the actual chosen query against the independent corpus
oracle, complete Elasticsearch counts/aggregates, explicit group/ranking/period
semantics, chained query order, numeric JSON-pointer citations, exact CSV ID
membership or aggregate rows, map-link counts and selected groups. Completed CSV
status must have reached the model before its answer. The controlled prompt-injection
case inserts an explicitly untrusted note into a discovery response; it does not
claim that this malicious text exists in NYC data.

The denominator is always 120. Missing attempts, model timeouts, malformed final
answers, unknown tool calls and grader errors cannot become passes. Automatic
acceptance requires at least 90%, every question passing at least one repetition,
and no fabricated numeric citations. Every question is mandatory in this initial
protocol; the freeze records `minimum_passes_per_question:1`, not a three-of-three
robustness claim. Every matched analysis stage needs its own numerical evidence.
Report per-question variability; three runs are not three independent
held-out examples. A model that performs poorly yields a preserved failed study.

The automatic report deliberately leaves `release_verified=false`,
`semantic_review=pending` and `end_to_end_pass_rate=null`. A reviewer independent
of the answering session must still inspect the actual conversational answer,
intent, clarification/refusal wording, limitations, artifact links, invented prose
numbers and unsupported completion claims. Review may be AI-assisted, but identify
that explicitly rather than claiming human adjudication. Map-link creation does
not certify browser rendering, joins or visual parity. The planned second actual
agent-client subset is a separate gate; these Python service calls exercise this
one local model adapter only.

Bind independent semantic judgments to exact immutable trial bytes:

```text
python tools/agent_evaluation.py review --freeze runs/agent-freeze-v1.json --runs runs/agent-evaluation-v1 --reviews runs/independent-reviews.json --output runs/agent-reviewed-v1.json
```

For separate CI repetitions, pass all three run directories after `--runs`.
Review JSON contains `freeze_sha256`, a `reviewer` object with `id`, `kind`
(`independent_ai_session` or `independent_human`) and `was_answering_agent:false`,
then a `reviews` array. Each review identifies `question_id`, `repeat`,
`trial_sha256`, text `notes`, and these exact Boolean `checks`: `intent_correct`,
`narrative_grounded`, `clarification_or_rejection_correct`, `limitations_correct`,
`artifacts_explained`, `no_fabrication`, `no_false_completion`. Mark nonapplicable
requirements true only after explaining applicability in the notes. The importer
rejects duplicate/foreign trials, mismatched bytes and incomplete check schemas;
it does not authenticate the reviewer or invent judgments. Preserve separate
review-session evidence. Missing judgments remain failures in the 120 denominator.
Fabricated prose or false completion blocks the agent-quality gate. A passing
agent-quality report still leaves overall release, second-client and rendered-map
verification to their separate actual evidence.

Keep corpus, SQLite database and raw transcripts in ignored `data/` or `runs/`.
Publish reviewed summary receipts and selected sanitized evidence rather than
unreviewed record-level tool output. Focused checks passing locally
used five authored records and mock model responses; they are implementation checks,
not real model, live engine or million-record benchmark evidence.
