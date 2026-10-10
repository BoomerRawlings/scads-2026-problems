# Verification status

Version **0.7.0** remediation is in progress. Executable tooling, executed checks,
and acceptance outcomes are distinct. **2,133,268 real unique requests reconcile
through capture, normalization, an immutable Elasticsearch index and an independent
SQLite reference.** Five real-data analytical families and a bounded performance
workload passed. **Rendered Maps and actual-agent acceptance remain incomplete.** The original published findings
remain in [the historical v0.6 record](acceptance-v0.6.md).

| Requested gap | Current evidence | Remaining execution |
| --- | --- | --- |
| Actual ≥2 million requests | All five stages reconcile2,133,268 rows; full raw and normalized hashes, ingested byte offset and frozen index UUID recorded | Acquisition/count target met for this captured window |
| Neighborhood comparisons | Official262 NTA polygons/197 residential codes; qualified observed window; June/October rodent comparison matches independent SQL across196 represented neighborhoods | Agent-led chained comparisons and rendered neighborhood maps; population completeness remains unclaimed |
| Elasticsearch/Kibana | Elasticsearch9.5.5 parity/CSV passed in four real runs; reusable maps/262 boundaries provisioned; fourth run loaded named maps and displayed points/polygons; captured request filters agree | All three checks timed out at Inspector map details; exact rendered membership and joined metric values remain unverified |
| Actual agent |40 prospective AI-authored questions, independent SQLite oracle,3 repetitions and chained analyses implemented; latest development smoke completed but invented restrictions and falsely requested clarification | Execute120 real model trials of the frozen negative candidate under a prospective operational-eligibility amendment; retain quality failure and complete unchanged threshold/semantic review |
| Usable performance | Actual4CPU/16.77GB host:25 serial queries, two5-query batches,9,728-row exports, sampled memory and one abrupt worker recovery passed | Broader sustained load, cold cache, end-to-end model latency and server recovery remain unqualified |
| Two paper descriptions | Corrected administrative closure versus first response; separate Maps processing and CSV-worker paths; changed pages visually checked | Website remains its earlier published edition until separately republished |

## Executed verification

- [Latest archived local regression](../examples/evidence/test-report-v0.7-inspector-id.json):553 tests collected,552 passed, one Windows unprivileged-symlink skip,41.062seconds; includes exact frozen-index document identity for Maps verification. [Default-preview checkpoint](../examples/evidence/test-report-v0.7-preview-default.json):551 collected,550 passed, one skip,37.314seconds; preserves explicit larger previews/exact totals/full CSV exports. Exact source hashes are pinned. Mock transports and authored data do not establish million-record behavior. [Earlier warmup/route checkpoint](../examples/evidence/test-report-v0.7-warmup-route.json):548 collected,547 passed, one skip,43.169seconds; [Maps/schema checkpoint](../examples/evidence/test-report-v0.7-maps-schema.json):535 collected,534 passed, one skip,53.299seconds; [bootstrap checkpoint](../examples/evidence/test-report-v0.7-bootstrap.json):520 collected,519 passed, one skip,22.741seconds; [worker repair](../examples/evidence/test-report-v0.7-post-worker.json):506 collected,505 passed, one skip,35.346seconds.
- [Actual capture and local verification](../examples/evidence/captured-local-verification.json): successful [run37700939902](https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/37700939902),2,133,268 unique requests across2135 page operations. All1,306,911,416 decompressed bytes match SHA256`91d84eb6d02dafc402a892298ba92cb121e8e905a189fb75f31b19d4d43aeec7`. Every record was streamed locally to verify strict ascending unique keys, creation dates inside April1-Nov1 2025 and the maximum source update. The163,696,296-byte gzip and [canonical source manifest](../examples/evidence/captured-manifest.json) are retained. No raw JSONL file or full ID set was materialized locally; verification took47.703seconds. Source before/after counts, metadata and revisions reconcile in the manifest; the local check did not re-query the changing provider.
- [Actual Elastic9.5.5 parity on v0.7](../examples/evidence/live-parity-9.5.5-v0.7.json):14 families,32 authored records, real PIT/composite pagination and full CSV membership. Kibana health was observed separately; browser rendering was not part of this check.
- [Earlier acquisition failures](../examples/evidence/capture-attempts-v0.7.json): first request timeout30s; a local count took43.891s. Second attempt passed counts but timed out on its first5000-row page after bounded120s retries, leaving zero captured rows. The successful third run used1000-row pages. Historical failures remain; success does not establish a general network-throughput guarantee.
- [Official boundaries](../examples/evidence/official-nta2020-26b.json):4,532,381 captured bytes, SHA256`5049760a4d0936e1d3dbf70d745e2cee4286bd163b11c702f15fa28db46a001e`, matching source metadata before/after download.
- [Evaluator and public-contract checks](../examples/evidence/agent-evaluator-v1-checks.json):134 focused tests passed in6.466seconds across contracts, fixture, guide, service, settings and evaluator. They include exact warmup-input binding and default-five previews with unchanged full CSV membership. Authored fixtures and mock responses are not the actual120-trial experiment or native model grammar qualification.

## Actual model development: latest retained failure

[Smoke38028703734](https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/38028703734),
commit`ffbbd5811c2b6ca949417b926dd56e3807e1e34d`, completed its one authored
32-record count question but failed quality. Exact [summary](../examples/evidence/model-smoke-38028703734/summary.json)
and [trace](../examples/evidence/model-smoke-38028703734/trace.json) retain all
failure flags. The runtime,24,576-token context and160s/120s trial/request budgets
were unchanged; the prospective public preview default was five.

Its [metadata-only warmup](../examples/evidence/model-smoke-38028703734/runtime/metadata-prefix-warmup.json)
took163.584s, processing7,312 prompt tokens and one discarded output token. The
first response reported7,306 cached tokens/55 new tokens and completed in32.110s.
Despite an explicit unrestricted count request, the model invented a category
filter, polygon, last-month period and borough/day grouping. Validation returned
`needs_clarification`; the model then blamed missing user details. After one
format-only repair it returned a structured clarification, with no analytical
result, count, citation or synthetic-data disclosure. Trial elapsed59.404s excludes
startup; measured smoke wall time including startup was223.025s. This is a
semantic failure, not a timeout or a successful count.

[Independent review](../examples/evidence/model-smoke-38028703734/independent-review.json)
verified exact metadata identities, hashes, invented arguments, validation output,
cache counters, final response and timing arithmetic. The compact archive retains
18 exact files plus this review,66,987 bytes. Three completed model response events
are distinct from the trace's one model-initiated tool-call counter. Raw benchmark
and resource measurements remain; their RSS belongs to `llama-bench`, not the
model-server trial. No live inference was rerun for this review.

Before any held-out exposure, the study decision is to stop development tuning
and measure this negative candidate on all40 questions x3 runs. A prospective
operational-eligibility gate will establish that the frozen runtime can execute
bounded requests; it must not relabel this quality failure as passed. The120-trial
denominator,90% threshold, all-case coverage and independent semantic review stay
unchanged. The gate amendment and actual campaign results remain separate evidence;
this smoke itself contains zero held-out trials.

### Earlier retained warm-prefix timeout

[Smoke38027531995](https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/38027531995),
commit`07617587eb8908cd5d5fea2e95c46cbe086a3f41`, failed on the authored
32-record fixture. The exact [summary](../examples/evidence/model-smoke-38027531995/summary.json)
and [trace](../examples/evidence/model-smoke-38027531995/trace.json) remain unchanged.
The Qwen3-1.7B native OpenBLAS candidate used24,576 context tokens with context
shifting disabled and the declared160s trial/120s request budgets.

The [metadata-only warmup](../examples/evidence/model-smoke-38027531995/runtime/metadata-prefix-warmup.json)
took190.317s, processing7,230 prompt tokens and one discarded output token without
a question or analytical call. The first timed model response reported7,224 cached
tokens and55 new prompt tokens; in9.067s it issued a valid unrestricted records
query whose exact total was32. Its projected result contained11,663 UTF-8 bytes.
The following model request timed out before any final answer, numerical claim,
result citation or synthetic-data disclosure. Trial elapsed129.074s excludes
startup; measured smoke wall time including startup was319.442s. Downloads,
compilation and initial server loading precede that interval.

[Independent review](../examples/evidence/model-smoke-38027531995/independent-review.json)
verified warmup/trace hashes, exact metadata identities, query arguments, count,
cache counters, failure and elapsed-time arithmetic. The compact archive retains
18 exact files plus this review,94,075 bytes. Raw benchmark and resource measurements
remain available; their RSS values belong to `llama-bench`, not this model-server
trial. This was one failed development question, zero held-out trials. A valid
intermediate tool call and observed cache reuse do not establish conversational
acceptance. Earlier cold timeouts and invalid-call failures remain preserved.

## Real-corpus execution and independent receipt review

The fourth [core run38027551047](https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/38027551047)
executed commit`6c39592ab00c2271203141ede36a25c98104e6da` on2026-10-10,
05:30:42–05:42:45UTC. Its [acceptance receipt](../examples/evidence/real-core-38027551047/acceptance.json)
retains both overall flags false. All five stages again reconcile2,133,268 requests,
the same raw/normalized hashes and unchanged observed-snapshot qualification.
Frozen index UUID`WiMgFvI_Sp2pbTgsL05Zhw`; normalization201.585s,
ingestion/freeze274.365s. These are separate run observations.

Maps provisioning and the saved-map route passed. Reviewed
[point](../examples/evidence/real-core-38027551047/render-points-failure.png),
[all-trend](../examples/evidence/real-core-38027551047/render-trends-failure.png) and
[selected-trend](../examples/evidence/real-core-38027551047/render-selected_trends-failure.png)
screenshots show named saved maps, visible points/polygons and the Requests
Inspector:242 point hits or262 boundary hits. All three checks timed out at
`inspector_map_details`. Exact paths and no page-error types are recorded in the
[point](../examples/evidence/real-core-38027551047/render-points.json),
[trend](../examples/evidence/real-core-38027551047/render-trends.json) and
[selected](../examples/evidence/real-core-38027551047/render-selected_trends.json)
receipts. Retained browser requests match the saved point filter, exact source
indexes, result-ID predicate and selected NTA codes. Request-side agreement and
visible geometry do not establish complete rendered membership or joined values;
all rendered-parity flags remain false.

Fourth-run [measurements](../examples/evidence/real-core-38027551047/measurements.json)
again contain25 serial queries plus two five-query batches. Median/maximum
milliseconds: filter25.541/29.004, group48.939/98.036, closure29.541/34.555,
geo30.239/39.498 and comparison85.909/114.786. Batches took0.187s at concurrency1
and0.144s at2. The same9,728-row, nine-column,1,139,937-byte export took0.956s
alone,0.990s for two together and0.702s after actual exit86/recovery. All four
complete CSVs retain exact independent membership and identical bytes. Recovery
call0.0159s excludes detection/re-export. Total workload4.585s; six periodic
samples reached runner RSS127,008,768B and Elasticsearch heap1,071,525,576B.
Uncontrolled caches, short load and sampled memory retain the earlier limits.

[Independent offline review](../examples/evidence/real-core-38027551047/independent-review.json)
rechecked all count/provenance seals, five full results,35 measured query digests,
four full-export memberships, point/trend CSVs, request filters and timing arithmetic.
Maximum numerical difference2.84e-14. The archive contains19 JSON receipts and
three unchanged screenshots,530,068 bytes; no raw records or individual-ID lists.
Earlier failures and their distinct observations remain below.

Audit-summary correction: the second, third and fourth derived reviews previously
serialized `captured:3` after reusing a map-cohort loop variable. Full offline
checks were rerun; all five reconciliation fields now read2,133,268. Each corrected
review records its previous hash and correction. Original execution receipts,
CSV evidence, screenshots and analytical results remain byte-identical; the first
review's count was already correct.

The third [core run38025638157](https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/38025638157)
executed commit`03fd0c094f99396f9af1106823811c3a5c5d1c55` on2026-10-10,
04:56:56–05:08:26UTC. Its [acceptance receipt](../examples/evidence/real-core-38025638157/acceptance.json)
retains both overall flags false. The same2,133,268 rows and raw/normalized hashes
reconcile across all five stages; frozen index UUID`_U8LIYhTRiSH69BdO3yTBw`.
Normalization took155.052s and ingestion/freeze301.047s. Observed-snapshot
qualification and its population/transaction-isolation limitations remain unchanged.

[Maps provisioning](../examples/evidence/real-core-38025638157/maps-provision.json)
again passed. Links were created and source/published-group count checks completed.
All three [point](../examples/evidence/real-core-38025638157/render-points.json),
[all-trend](../examples/evidence/real-core-38025638157/render-trends.json) and
[selected-trend](../examples/evidence/real-core-38025638157/render-selected_trends.json)
browser checks then failed with `TimeoutError`. Reviewed screenshots show the
Maps/Create breadcrumb, a filter chip, empty canvas and Inspector reporting no
requests. The captured search records contain only index-pattern metadata lookup.
This establishes browser navigation, not loading the intended saved layers or
correct DSL, rendered geometry, membership or joins. The exact
[point screenshot](../examples/evidence/real-core-38025638157/render-points-failure.png),
[trend screenshot](../examples/evidence/real-core-38025638157/render-trends-failure.png)
and [selected screenshot](../examples/evidence/real-core-38025638157/render-selected_trends-failure.png)
remain archived. The suspected locator defect requires a corrected live run.

Third-run [measurements](../examples/evidence/real-core-38025638157/measurements.json)
again include25 serial queries and two five-query batches. Median/maximum
milliseconds: filter22.237/28.918, group45.513/98.267, closure24.338/29.240,
geo25.050/29.652 and comparison71.292/103.995. Batches took0.174s at concurrency1
and0.126s at2. The9,728-row export took0.696s alone,0.800s for two together and
0.594s after actual first-row exit86/recovery; all four CSVs retain the same exact
independent membership and bytes. Recovery call0.0137s excludes detection and
re-export. Total measured workload3.711s; five periodic samples observed runner
RSS125,046,784B and Elasticsearch heap1,609,966,624B. These remain finite,
uncontrolled-cache observations, not peak capacity or an optimization comparison.

The [independent offline review](../examples/evidence/real-core-38025638157/independent-review.json)
rechecked provenance/counts, certificate seals, all five saved results,35 measured
result digests, four full CSV memberships, point/trend CSVs and timing arithmetic.
Maximum numeric difference2.84e-14; no new analytical mismatch found. The compact
archive contains19 JSON receipts and three unchanged failure screenshots,
408,173 bytes total after the derived-summary correction. No raw corpus, individual-ID lists or CSV bodies were copied.
The saved-map route repair now has source-matching r3 packages below; renewed
live checks remain necessary. Packaging does not promote this failed render run.

The second [core run38004540380](https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/38004540380)
executed commit`78bae7eac0e33d28deb0cb404295f6f900a85db7` on2026-10-09,
23:31:03–23:38:53UTC. Its [acceptance receipt](../examples/evidence/real-core-38004540380/acceptance.json)
retains `passed:false` and `overall_release_verified:false`. Capture, normalization,
completed ingestion, frozen index and SQLite again reconcile2,133,268 rows with
the same raw/normalized byte counts and hashes below. The new frozen index UUID is
`7FQfb9nTR2S2JB0E7tIsmQ`. Normalization took136.674s; ingestion/freeze226.918s.
Different single-run timings are not a controlled optimization comparison.

[Maps provisioning passed](../examples/evidence/real-core-38004540380/maps-provision.json):
actual Elasticsearch/Kibana9.5.5,262 indexed boundaries, three exact-index data
views without time fields, and reusable point/trend saved maps. The provisioner
read back stored layers/references. All three subsequent checks stopped at
`map_link`: [points](../examples/evidence/real-core-38004540380/render-points.json)
reported `backend_unavailable`; [all trends](../examples/evidence/real-core-38004540380/render-trends.json)
and [selected trends](../examples/evidence/real-core-38004540380/render-selected_trends.json)
reported `coverage_gap`. CSV cohorts242/196/3 had already passed. No browser,
screenshot, rendered membership, joined metric or browser-filter success occurred.

The second [performance receipt](../examples/evidence/real-core-38004540380/measurements.json)
contains25 serial queries plus two five-query batches. Median/maximum milliseconds
were22.898/34.373 for filter,42.799/71.068 for grouping,23.901/27.675 for closure,
24.474/27.897 for geo and46.866/91.814 for comparison. Batch times were0.152s at
concurrency1 and0.138s at2. The same9,728-row nine-column export took0.617s alone
and0.788s for two together. All four retained CSVs match the independent IDs and
the prior run's exact bytes. Actual first-row worker exit86, lease protection,
cleanup and exact re-export passed again; recovery call0.0129s excludes detection
and re-export. Total measured workload3.437s; uncontrolled caches and five periodic
memory samples do not establish sustained capacity, tail latency or peak memory.
Those samples reached107,851,776B runner RSS and1,090,519,040B Elasticsearch heap;
externally sampled owned-worker RSS reached32,387,072B individually/59,174,912B
combined. Non-ID CSV cells and broader crash recovery remain unqualified.

[Independent receipt review](../examples/evidence/real-core-38004540380/independent-review.json)
rechecked all provenance/count seals, five complete saved results,35 query-result
digests, four export memberships, point/trend CSVs and timing arithmetic. Maximum
numeric difference remains2.84e-14. Provision IDs match the generated profile;
all pre-browser failures remain explicit. Sixteen compact JSON artifacts are
archived; raw records, individual-ID lists and CSV bodies are excluded. This
offline review does not repeat the live service or independently reassign polygons.

The [v0.7 r4 offline packages](../examples/evidence/build-v0.7-r4.json) passed fresh
clean-install checks with the public default-five-record preview on CPython3.12 Windows x64
only. All36 wheels,3,959 RECORD entries,23 source modules, five resources and both
bundle inventories passed independent integrity checks. The original0.7, r2 and r3 packages
remain unchanged and source-specific. Neither package smoke runs real services or
qualifies model/Maps acceptance. [Distribution details](distribution.md).

The earlier run remains below as a separate, preserved observation.

[Core run37705537519](https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/37705537519)
executed commit`40a52917373bc54a0685b3b8ae35d261967c504f` on Linux. Its
[unaltered acceptance receipt](../examples/evidence/real-core-37705537519/acceptance.json)
retains `passed:false`: Maps provisioning failed and the separate development-model
gate blocked held-out inference. Passing stages are reported individually.

| Reconciliation stage | Rows | Bytes or identity |
| --- | ---: | --- |
| Captured unique real requests | 2,133,268 | 1,306,911,416 raw JSONL bytes |
| Normalized requests | 2,133,268 | 1,582,275,376 JSONL bytes |
| Completed ingestion | 2,133,268 | Exact normalized byte offset and SHA-256 matched |
| Frozen Elasticsearch index | 2,133,268 | `nyc311-real-2025-v1`; UUID `JVlj8cmQQWmf-7R8ESy3IA` |
| Independent SQLite reference | 2,133,268 | Same complete normalized-file SHA-256 |

Raw SHA-256 is `91d84eb6d02dafc402a892298ba92cb121e8e905a189fb75f31b19d4d43aeec7`;
normalized SHA-256 is `70ceb22b8f9f79cc03c5dcd4d1955ff0ef7148b63d07e54e9610d726c94dc18e`.
Normalization took277.390s; ingestion and index freeze324.558s. These are single-run
stage timings. [Normalized manifest](../examples/evidence/real-core-37705537519/normalized.manifest.json),
[frozen manifest](../examples/evidence/real-core-37705537519/index.manifest.json).

The captured creation-date window is April1–November1,2025, NYC local time, end
exclusive. Qualification binds the official NTA hash and the197-code residential
whitelist. No records were dropped;32,843 lack geometry and474 have coordinates
unmatched to a polygon. Other retained quality flags include35,944 missing closed
dates,415 negative closure durations and14 ambiguous closed dates; flags can overlap.
Affected records remain in counts; invalid durations do not contribute to closure
means. Closure measures describe administrative closure recorded in the October2026
capture, not first response or reconstructed historical status.

[Independent SQL parity](../examples/evidence/real-core-37705537519/independent-parity-summary.json)
covered242 Brooklyn residential-noise requests on October1;336,612 October requests
across81 borough/agency groups;1,935 October rodent requests with agency closure
metrics;3,286 October requests within1km of the declared downtown coordinate; and
June versus October rodent reporting across196 represented residential NTAs.
The comparison includes3,680 June and1,928 October requests, with30/31-day rate
denominators. Exact point CSV membership242, complete trend CSV196 groups and
selected trend CSV3 groups passed. SQL shares the normalized records and spatial
assignments; it independently checks querying, not the correctness of every polygon
assignment. The chained natural-language neighborhood/agency task remains untested.

| Real-index query family | Median ms | Maximum ms | Serial runs |
| --- | ---: | ---: | ---: |
| Filter and record preview | 27.991 | 30.111 | 5 |
| Borough/agency aggregation | 55.000 | 109.768 | 5 |
| Administrative closure mean | 31.223 | 35.684 | 5 |
| Geographic radius | 36.095 | 38.413 | 5 |
| Neighborhood period comparison | 61.901 | 114.754 | 5 |

The [performance receipt](../examples/evidence/real-core-37705537519/measurements.json)
also records one5-query batch at concurrency1 in0.199s and one at concurrency2 in0.151s.
An October Brooklyn residential-noise export contained9,728 rows, nine columns and
1,139,937 bytes:0.854s individually,1.087s for two concurrent exports together,
and0.703s for a fresh export after recovery. All four CSVs match the independent
ID set and have identical SHA-256. Non-ID cells lack an independent cell-by-cell
real-corpus oracle. The1-day map cohort is separate from this full-month export.

The actual worker exited86 after reaching first-row streaming. Recovery protected
its active lease before exit, then marked the abandoned job failed, removed its
partial file/reservation and allowed exact re-export. The recovery call took0.0179s;
that excludes worker launch, failure detection and re-export. This is a local export
worker test, not Elasticsearch/node or mid-ingestion crash recovery.

Six memory observations found runner RSS up to105,132,032 bytes and Elasticsearch
heap use up to783,136,704 bytes with a2GiB configured heap. Externally sampled worker
RSS reached33,099,776 bytes individually and57,856,000 bytes combined; the fault
worker separately reported33,693,696 bytes at its gate. These are sampled values,
not guaranteed peaks. Elasticsearch's process-memory field is virtual memory,
not RSS; ingestion and Kibana peak memory were not measured.

The entire measured workload lasted4.607s, after prior queries on the same index.
Caches were uncontrolled; client timings include service initialization and result
persistence but exclude LLM and browser latency. Five repetitions and two short
batches cannot establish p95/p99, sustained throughput, capacity ceilings or an SLA.
Observed worker-process overlap does not establish simultaneous CPU execution.

[Independent offline review](../examples/evidence/real-core-37705537519/independent-review.json)
rechecked provenance hashes/counts, qualification seals, all five saved query results,
all35 performance-result digests, timing arithmetic and all retained CSV memberships.
Maximum numerical difference was2.84e-14 with tighter1e-10 relative/1e-9 absolute
tolerances. Thirteen compact JSON artifacts are archived; no raw records, individual
oracle-ID lists, CSV bodies or locks were copied. This is a review of retained
execution evidence, not a second live run.

[Maps failure](../examples/evidence/real-core-37705537519/maps-provision.json)
occurred before map creation or rendering. The captured Kibana health payload lacks
version metadata, so the version-check failure does not prove a different version
was running. No rendered Maps parity is claimed.

The [archived verification source](../examples/evidence/capture-verification-source.py)
is byte-identical to the executed script: its SHA-256 matches the local receipt's
`local_verification.script_sha256`. The receipt preserves the original run-directory
path. This is frozen study code with exclusive output creation, not a general CLI;
archiving it did not rerun verification.

Earlier failures remain part of the record: the499-test local run had one failure,
five errors and one skip when disk fell below the unchanged1GB reserve; CI500 had
498 passes, one failure and one skip in65.215seconds after a worker launched from
another working directory exposed an import failure. The506-test worker-repair run passed
after the repairs. Initial4B development smokes timed out; an intermediate smoke
workflow stopped at tests without running the model. The smaller1.7B candidate
and generic bounded repair remain development work. No120-trial quality outcome
is claimed.
Real-corpus processing run37705537519 ran2026-10-08 00:05:35–00:17:14UTC; its
successful analytical stages and retained Maps failure are documented above.

The actual workflows and their retained failures are visible on
[the acceptance branch](https://github.com/BoomerRawlings/scads-2026-problems/tree/codex/project2-acceptance-20261007).
The frozen publication commit488c57c is preserved.
The current capture is also retained locally. GitHub metadata for the renewed
capture artifact in [core run37705537519](https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/37705537519)
reports creation2026-10-08 00:05:20UTC and expiry2026-11-07 00:05:16UTC, confirming
the new30-day retention setting for that copy.

## What each gate means

Source-reconciled observations qualify comparisons only inside their captured
creation-date window. `coverage.complete` remains false: public reporting is not
population completeness, and matching revisions do not prove transaction isolation.
Comparison answers retain this scope. Missing creation timestamps or lost records
block qualification. Residential NTA areas are distinguished from parks, airports
and other special areas. [Qualification rules](qualification.md).

The real-corpus runner hashes the captured bytes, enriches with the pinned polygons,
normalizes without dropped records, verifies indexed counts and UUID, then builds
an independent SQLite reference. Browser checks inspect the actual rendered source
IDs and joined metrics plus the browser's filters; a locator URL alone cannot pass.
[Runner](real-acceptance-runner.md), [maps](live-maps.md).

Agent cases are frozen before model exposure. Questions are prospective and held
out from answering contexts; they are AI-authored, not independent human labels or
proof of unseen pretraining content. Missing, malformed and failed trials remain
in the120 denominator. Passing requires the declared90% threshold, mandatory
case coverage, numerical/artifact checks and separate semantic review.
[Protocol](agent-evaluation.md), [pinned local runtime](local-model-runtime.json).

Performance measurements report actual query distributions, concurrent requests
and exports, client/worker RSS and Elasticsearch JVM/process/cache observations.
The recovery trial terminates its own interpreter while holding a job lease and
checks exact re-export membership. These finite observations establish neither
maximum capacity nor a production SLA. [Measurement protocol](live-performance.md).

## Reproduction and limits

Run `python -m unittest discover -s tests -q` for implementation checks. The
acquisition and evaluation workflows run on a capable host; they do not require
a paid model provider. Installation/staging needs network access. Fully offline
operation, a second independently evaluated agent client and billion-record
physical capacity remain separate later milestones, not claims from this study.

The corrected paper remains a historical report with editorial repairs; its
original empirical claims were not promoted to new outcomes. The scope, hashes and
visual checks are recorded in
[the paper correction receipt](../../../publication/papers/paper-02-corrections.json).
