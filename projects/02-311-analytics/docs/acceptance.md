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
| Elasticsearch/Kibana | Elasticsearch9.5.5 real-corpus filter/group/closure/geo/comparison parity and exact CSV membership passed | Maps provisioning failed at version discovery; reusable maps and browser-rendered filters/values/membership unverified |
| Actual agent |40 prospective AI-authored questions, independent SQLite oracle,3 repetitions, chained analyses and retained failures implemented | Execute120 real model trials, independent semantic review and report actual threshold outcome |
| Usable performance | Actual4CPU/16.77GB host:25 serial queries, two5-query batches,9,728-row exports, sampled memory and one abrupt worker recovery passed | Broader sustained load, cold cache, end-to-end model latency and server recovery remain unqualified |
| Two paper descriptions | Corrected administrative closure versus first response; separate Maps processing and CSV-worker paths; changed pages visually checked | Website remains its earlier published edition until separately republished |

## Executed verification

- [Current local regression](../examples/evidence/test-report-v0.7-post-worker.json):506 tests collected,505 passed, one Windows unprivileged-symlink skip,35.346seconds. Mock transports and authored data do not establish million-record behavior.
- [Actual capture and local verification](../examples/evidence/captured-local-verification.json): successful [run37700939902](https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/37700939902),2,133,268 unique requests across2135 page operations. All1,306,911,416 decompressed bytes match SHA256`91d84eb6d02dafc402a892298ba92cb121e8e905a189fb75f31b19d4d43aeec7`. Every record was streamed locally to verify strict ascending unique keys, creation dates inside April1-Nov1 2025 and the maximum source update. The163,696,296-byte gzip and [canonical source manifest](../examples/evidence/captured-manifest.json) are retained. No raw JSONL file or full ID set was materialized locally; verification took47.703seconds. Source before/after counts, metadata and revisions reconcile in the manifest; the local check did not re-query the changing provider.
- [Actual Elastic9.5.5 parity on v0.7](../examples/evidence/live-parity-9.5.5-v0.7.json):14 families,32 authored records, real PIT/composite pagination and full CSV membership. Kibana health was observed separately; browser rendering was not part of this check.
- [Earlier acquisition failures](../examples/evidence/capture-attempts-v0.7.json): first request timeout30s; a local count took43.891s. Second attempt passed counts but timed out on its first5000-row page after bounded120s retries, leaving zero captured rows. The successful third run used1000-row pages. Historical failures remain; success does not establish a general network-throughput guarantee.
- [Official boundaries](../examples/evidence/official-nta2020-26b.json):4,532,381 captured bytes, SHA256`5049760a4d0936e1d3dbf70d745e2cee4286bd163b11c702f15fa28db46a001e`, matching source metadata before/after download.
- [Evaluator implementation checks](../examples/evidence/agent-evaluator-v1-checks.json):24 focused tests. These use an authored tiny corpus and mock model; they are not the actual120-trial experiment.

## Real-corpus execution and independent receipt review

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
another working directory exposed an import failure. The506-test run above passes
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
