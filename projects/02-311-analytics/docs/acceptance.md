# Verification status

Version **0.7.0** remediation is in progress. Executable tooling, executed checks,
and acceptance outcomes are distinct. No million-record or agent-quality pass is
claimed before the corresponding receipts exist. The original published findings
remain in [the historical v0.6 record](acceptance-v0.6.md).

| Requested gap | Current evidence | Remaining execution |
| --- | --- | --- |
| Actual ≥2 million requests | Official April–October 2025 source reports 2,133,268 distinct keys; two CI acquisition failures retained | Complete capture; reconcile actual raw, normalized, unique and frozen index counts |
| Neighborhood comparisons | Official NTA2020 release26b downloaded:262 valid polygons,197 residential areas; strict observed-corpus qualification implemented | Qualify captured full periods, enrich real records and execute comparisons |
| Elasticsearch/Kibana | Real9.5.5 services started;14 authored query families and exact CSV membership passed | Real-corpus independent SQL parity; reusable maps and actual browser-rendered filters/values/membership |
| Actual agent |40 prospective AI-authored questions, independent SQLite oracle,3 repetitions, chained analyses and retained failures implemented | Execute120 real model trials, independent semantic review and report actual threshold outcome |
| Usable performance | Real runner observed:4CPU,16.77GB RAM,88.57GB free disk; real-data query/export/concurrency/memory/recovery harness implemented | Execute on the qualified million-record index; publish distributions and finite operational limits |
| Two paper descriptions | Corrected administrative closure versus first response; separate Maps processing and CSV-worker paths; changed pages visually checked | Website remains its earlier published edition until separately republished |

## Executed verification

- [Current local regression](../examples/evidence/test-report-v0.7-prelive.json):471 tests collected,470 passed, one Windows unprivileged-symlink skip,52.759seconds. Mock transports and authored data do not establish million-record behavior.
- [Actual Elastic9.5.5 parity on v0.7](../examples/evidence/live-parity-9.5.5-v0.7.json):14 families,32 authored records, real PIT/composite pagination and full CSV membership. Kibana health was observed separately; browser rendering was not part of this check.
- [Acquisition failures](../examples/evidence/capture-attempts-v0.7.json): first request timeout30s; a local count took43.891s. Second attempt passed counts but timed out on its first5000-row page after bounded120s retries, leaving zero captured rows. Checkpoint preserved; next retry uses1000-row pages. Local1000-row pages succeeded, which does not diagnose the CI network path.
- [Official boundaries](../examples/evidence/official-nta2020-26b.json):4,532,381 captured bytes, SHA256`5049760a4d0936e1d3dbf70d745e2cee4286bd163b11c702f15fa28db46a001e`, matching source metadata before/after download.
- [Evaluator implementation checks](../examples/evidence/agent-evaluator-v1-checks.json):24 focused tests. These use an authored tiny corpus and mock model; they are not the actual120-trial experiment.

The actual workflows and their retained failures are visible on
[the acceptance branch](https://github.com/BoomerRawlings/scads-2026-problems/tree/codex/project2-acceptance-20261007).
The frozen publication commit488c57c is preserved.

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
