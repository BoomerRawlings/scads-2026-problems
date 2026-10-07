# Verification status

Version **0.7.0** remediation is in progress. Executable tooling, executed checks,
and acceptance outcomes are distinct. **2,133,268 real unique requests have been
captured and independently rechecked locally.** Normalization/index reconciliation,
real-corpus Maps, agent quality and performance acceptance remain pending. The original published findings
remain in [the historical v0.6 record](acceptance-v0.6.md).

| Requested gap | Current evidence | Remaining execution |
| --- | --- | --- |
| Actual ≥2 million requests | Captured2,133,268 real unique requests;1,306,911,416 raw bytes; local streaming hash, row count, strict key order and date bounds verified | Reconcile normalized and frozen index counts with the acquired raw corpus |
| Neighborhood comparisons | Official NTA2020 release26b downloaded:262 valid polygons,197 residential areas; strict observed-corpus qualification implemented | Qualify captured full periods, enrich real records and execute comparisons |
| Elasticsearch/Kibana | Real9.5.5 services started;14 authored query families and exact CSV membership passed | Real-corpus independent SQL parity; reusable maps and actual browser-rendered filters/values/membership |
| Actual agent |40 prospective AI-authored questions, independent SQLite oracle,3 repetitions, chained analyses and retained failures implemented | Execute120 real model trials, independent semantic review and report actual threshold outcome |
| Usable performance | Real runner observed:4CPU,16.77GB RAM,88.57GB free disk; real-data query/export/concurrency/memory/recovery harness implemented | Execute on the qualified million-record index; publish distributions and finite operational limits |
| Two paper descriptions | Corrected administrative closure versus first response; separate Maps processing and CSV-worker paths; changed pages visually checked | Website remains its earlier published edition until separately republished |

## Executed verification

- [Current local regression](../examples/evidence/test-report-v0.7-prelive.json):471 tests collected,470 passed, one Windows unprivileged-symlink skip,52.759seconds. Mock transports and authored data do not establish million-record behavior.
- [Actual capture and local verification](../examples/evidence/captured-local-verification.json): successful [run37700939902](https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/37700939902),2,133,268 unique requests across2135 page operations. All1,306,911,416 decompressed bytes match SHA256`91d84eb6d02dafc402a892298ba92cb121e8e905a189fb75f31b19d4d43aeec7`. Every record was streamed locally to verify strict ascending unique keys, creation dates inside April1-Nov1 2025 and the maximum source update. The163,696,296-byte gzip and [canonical source manifest](../examples/evidence/captured-manifest.json) are retained. No raw JSONL file or full ID set was materialized locally; verification took47.703seconds. Source before/after counts, metadata and revisions reconcile in the manifest; the local check did not re-query the changing provider.
- [Actual Elastic9.5.5 parity on v0.7](../examples/evidence/live-parity-9.5.5-v0.7.json):14 families,32 authored records, real PIT/composite pagination and full CSV membership. Kibana health was observed separately; browser rendering was not part of this check.
- [Earlier acquisition failures](../examples/evidence/capture-attempts-v0.7.json): first request timeout30s; a local count took43.891s. Second attempt passed counts but timed out on its first5000-row page after bounded120s retries, leaving zero captured rows. The successful third run used1000-row pages. Historical failures remain; success does not establish a general network-throughput guarantee.
- [Official boundaries](../examples/evidence/official-nta2020-26b.json):4,532,381 captured bytes, SHA256`5049760a4d0936e1d3dbf70d745e2cee4286bd163b11c702f15fa28db46a001e`, matching source metadata before/after download.
- [Evaluator implementation checks](../examples/evidence/agent-evaluator-v1-checks.json):24 focused tests. These use an authored tiny corpus and mock model; they are not the actual120-trial experiment.

The471-test receipt is the last persisted successful full local run, not a claim
that every later change passed. A subsequent499-test local run had one failure,
five errors and one skip after free disk fell below the unchanged1GB normalization
reserve. A later CI run collected500 tests:498 passed, one failed and one skipped
in65.215seconds; a worker launched from another working directory exposed an import
failure. Repairs and the full rerun remain pending. Two actual4B model smokes timed
out; the third smoke workflow stopped at its test stage and did not run the model.
The native-build candidate remains prospective.

The actual workflows and their retained failures are visible on
[the acceptance branch](https://github.com/BoomerRawlings/scads-2026-problems/tree/codex/project2-acceptance-20261007).
The frozen publication commit488c57c is preserved.
The current capture is also retained locally. The proposed30-day CI artifact
retention setting is pending workflow publication; it is not claimed for the
already-created artifact.

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
