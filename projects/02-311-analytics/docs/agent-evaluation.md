# Actual agent evaluation

The executable evaluator freezes 40 prospective questions and independently
calculated answers, then asks a real local model each question three times with
fresh conversation contexts. The model chooses and calls the seven analytical
tools; this is not prewritten AnalysisSpec replay. The questions are **AI-authored**,
not independent human-held-out labels or evidence of generalization to arbitrary
users. Executing 120 trials and passing the acceptance threshold are separate facts.
The protocol cannot establish that questions were absent from model pretraining.

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

```text
python tools/agent_evaluation.py prepare --config config/live.json --source data/normalized.jsonl --database data/oracle.sqlite --output runs/agent-freeze-v1.json --model analytics311-qwen35-4b

python tools/agent_evaluation.py run --config config/live.json --freeze runs/agent-freeze-v1.json --database data/oracle.sqlite --output runs/agent-evaluation-v1 --endpoint http://127.0.0.1:8080/v1 --seconds 120 --request-seconds 60
```

The freeze pins question bytes, all runtime Python source, evaluator source,
catalog, manifest, SQLite database, input JSONL hash/count, boundary identity,
expected values and model settings before the first model call. The model receives
only its question, general agent/tool instructions, discovery and actual tool
responses. Expected JSON specs and numeric oracles are never included. All three
repetitions use empty initial histories; fixed seeds 101/202/303 and temperature 0.2
are recorded. A model/server may not guarantee bitwise seed reproducibility.

The frozen adapter uses `discovery-rules-v1` for model context. Discovery retains
every request-building rule verbatim, full catalog/limits/fields, coverage,
qualification, warnings and unknown source text. It omits illustrative complete
requests and repeated workflow guidance; exact duplicate fields/version remain in
the top-level descriptor. Repeated provenance values use JSON Pointer `$ref` links
to identical ancestor data within that response. No questions, expected answers,
or question-specific shortcuts inform this projection. All other tool results are
unchanged. The transcript retains full original discovery alongside the exact
model-visible JSON string, its SHA-256, byte counts and projection version.
Reduced context bytes alone do not establish faster or more accurate inference.

Defaults: 300 seconds per trial, 90 seconds per model request, 24 tool calls,
2,048 output tokens per request, 256 KiB serialized request context, 1 MiB model
response, and 8 MiB transcript. CLI budgets above deliberately tighten deadlines.
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
