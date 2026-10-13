# Verification status

The local implementation is version 0.6.0. Static scale reasoning led to normalization disk/byte guards, exact export admission and CSV source-field projection. **119 focused tests passed**, zero failures/errors/skips; [receipt and source hashes](../examples/evidence/test-report-v0.6-focused.json), [reasoning and boundaries](forecast-v0.6.md). No scale simulation, benchmark, stress workload, live service or bulk capture ran for this change. The current build skips installation/workload smoke checks; the complete 0.5 verification below remains historical, not a full 0.6 regression claim.

Core and optional-agent 0.6 wheels are built. Static archive/metadata/hash checks passed for all 36 wheels; all 27 packaged runtime/resource files match current source, and the focused test source hashes still match. Their manifests deliberately retain installation verification `not_run`. [Build receipt](../examples/evidence/build-v0.6.json), [distribution instructions](distribution.md).

The original multi-million-record Elasticsearch/Kibana demonstration is **not yet accepted**. This record separates code checks, a real agent smoke demonstration, public-data sampling, generated workloads and modeled projections from outstanding release evidence. [Reliability workflow](reliability.md), [earlier performance audit](audit-v0.4.md).

## Local checks

The test suite covers strict contracts, query compilation, independently authored fixture answers, DST and missing-data behavior, 10,003-row mocked PIT pagination, a 10,001-row local CSV export, cooperative cancellation, row/byte budgets, source/index identity, checkpoints, NTA geometry, trend publishing and HTTP failure handling. CLI tests launch actual subprocesses and a background export. MCP tests use the installed official SDK over actual stdio and compare returned structured data with the service.

The last full suite, **version 0.5**, had **361 passed, one skipped, zero failures/errors** on Python 3.12.14/Windows (362 tests collected, 29.434 seconds). The skip is unprivileged symbolic-link creation denied by Windows; actual NTFS junction, hardlink, OS lease and interpreter-death checks passed. Exact status: [version 0.5 report](../examples/evidence/test-report-v0.5.json). Earlier [v0.4](../examples/evidence/test-report-v0.4.json), [v0.3](../examples/evidence/test-report-v0.3.json), [v0.2](../examples/evidence/test-report-v0.2.json) and [first milestone](../examples/evidence/test-report.json) reports remain historical evidence. Full-suite command for a later unrestricted verification run:

```text
python -m unittest discover -s tests -v
```

Elasticsearch/Kibana traffic in these tests is mocked. Geographic tests use synthetic polygons. Those tests do not establish real server compatibility, rendered map parity, real-world agent accuracy or physical cluster capacity.

## Reliability findings and actual process trials

The new concurrent export harness reproduced Windows access-denied failures during JSON metadata polling/publication. Actual held-reader and instrumented worker runs identified the failing operations. Narrow retries now cover those Windows errors only, with eight attempts and 225 ms of nominal sleeps; malformed data and persistent failures still fail. [Diagnosis](../examples/evidence/export-io-v0.5.json), [failed trial](../examples/evidence/export-stress-v0.5-initial.json).

A separate probe found that this Windows virtual environment's launcher and executing interpreter have different PIDs. Killing only a launcher was insufficient proof of worker death. Crash tests now signal the executing interpreter to call `os._exit` while holding its lease, verify the exit code and absence of normal cleanup, then check recovery. Four ingestion/job tests use exit77; the portable harness uses exit86.

The [final default trial](../examples/evidence/export-stress-v0.5.json) completed in **3.109 seconds** including cleanup: 11 launches, peak two live owned launch handles, ten CSVs with exactly four expected fixture IDs and matching byte counts/SHA256, plus one deliberate abrupt worker exit, active-worker protection, recovery and re-export. Two-worker batches also cover a changed working directory. Launch counts exclude extra Windows redirector descendants. This is finite software evidence from 32 authored records, not sustained load, capacity or real NYC data. [Reproduce](reliability.md).

The [initial v0.4 timeout](../examples/evidence/test-report-v0.4-initial.json) remains unexplained. Its isolated/full reruns passed unchanged; the new reproduced defects do not establish its historical cause. No timeout or polling interval was relaxed to make these checks pass.

## Production build checks

Version 0.2.0 introduces per-job OS leases, a default two-worker admission limit and explicit recovery. Tests kill real worker processes, verify locks are released by the OS, prevent duplicate writers, reclaim abandoned reservations and preserve unverified orphan CSVs. Actual CLI checks confirm recovery still works after manifest deletion and background exports remain in the original workspace after a caller changes its working directory.

The release builder built both final 0.5 wheels without network dependency resolution and installed each into a clean temporary environment outside the checkout using `pip --no-index`. Both passed discovery, validation, analysis, background export, exact four-row membership, capacity planning and unchanged installed resources. Transferred tools also ran outside the checkout: nine capacity scenarios, five reference cases on 100 generated rows and live-parity argument parsing. Both installed packages also passed seven export-worker launches, exact CSV membership, the changed-working-directory case, abrupt interpreter exit86 and recovery/re-export. The agent bundle additionally passed actual MCP stdio discovery (seven tools), four valid calls, one rejected operation and native Shapely inside/outside geometry checks. Artifact sizes, SHA256 hashes and all 27 packaged runtime/resource files were independently checked against current source. See [distribution instructions](distribution.md), the [core receipt](../examples/evidence/release-core-v0.5.json) and [agent receipt](../examples/evidence/release-agent-v0.5.json).

Core wheels total 434,331 bytes; agent wheels total 29,952,073 bytes across the project wheel and 33 dependency wheels. The agent target is CPython 3.12 x64 on Windows (`win_amd64`), even though the host is ARM64. Use a separately built wheelhouse for native ARM64 Python or other OS/interpreter targets. The Python audit hook blocks ordinary sockets and DNS while permitting standard-library socketpair initialization, which uses loopback TCP on Windows. This is test instrumentation, **not OS-level network isolation**. Neither bundle includes Python, model assets, Elasticsearch or Kibana.

Transfer ZIPs additionally include installation instructions, four checked tools and capacity inputs. Core ZIP: **498,271 bytes / 11 entries**; agent ZIP: **30,040,551 bytes / 43 entries**. Every entry was independently re-read, CRC-checked and SHA256-checked against its input and embedded inventory. [Archive receipts](../examples/evidence/handoff-bundles-v0.5.json). This confirms archive contents; it is not a separate target-OS or live-engine test.

Capture has 26 mocked transport/storage tests covering interrupted pages, resume, uniqueness, source drift, stale replicas, budgets and interrupted artifact publication, including a deadline during SQLite resume reconciliation. A live bounded December 1 2025 preflight on October 7 UTC returned `source_stale`: the provider marked the count response out of date. The job paused at **zero rows/pages**, with no JSONL or completed manifest published. [Probe evidence](../examples/evidence/capture-probe-v0.2.json). This establishes correct failure handling, not successful bulk acquisition. A successful observed reconciliation still leaves `coverage.complete=false`; provider transaction isolation remains unproven.

## Capacity and portable live verification

The October 7 live-completion attempt remains blocked by the execution target. A fresh [host preflight](../examples/evidence/live-preflight-host.json) observed 640,290,816 bytes available RAM, 5,766,598,656 bytes free disk, no Docker/Podman/Java, WSL not installed, and closed loopback ports 9200/5601. No configured alternative host was found. The existing two-million-row capacity model reports memory and disk shortages; those assumptions are not measured engine requirements. No other project's workloads were stopped and no heavy services or bulk corpus were started.

The latest bounded [source preflight](../examples/evidence/live-preflight-source.json) cleared the earlier observed stale-response condition: the provider reported **3,655,041 rows and distinct keys for 2025**, with matching nonstale revision headers on the aggregate and 50 ordered records. Only 57,142 response bytes were fetched. This is upstream aggregate/sample evidence, not local acquisition or complete coverage. A later capture must repeat freshness checks. The [standalone live runbook](live-runbook.md) covers target inventory, pinned containers, authored parity, real capture/ingestion, Kibana assets and bounded API/CSV acceptance. The separate [live kit](../examples/evidence/live-kit-v0.5-r2.json) preserves all original core entries and adds six verified deployment assets; no runtime changed. Coverage qualification and rendered maps remain separate gates.

The actual [scenario replay](../examples/evidence/capacity-scenarios-v0.3.json) executed nine bounded arithmetic combinations: three hypothetical hosts at 1,000 fixture, two million full-demo and one billion scale-lab rows. Six met the stated assumptions; three reported shortages. These are **modeled estimates**, not generated datasets or engine benchmarks. Every plan retains the requested row count and reports `ready_for_production=false`. The [observed-host plan](../examples/evidence/host-plan-v0.3.json) separately records this machine's inventory and modeled shortages. [Planning assumptions and reproduction](capacity.md).

The [live parity runner](live-parity.md) now provides 14 authored query families, exact full CSV membership and duplicate checks, selected independent metric anchors, and forced PIT/composite continuation. Its 15 local tests check oracle behavior and failure/cleanup safeguards using fake transports. **No live engine run occurred here**: Docker remained unavailable, and loopback ports 9200/5601 were closed. A fixture substituted for Elasticsearch deliberately fails the transport-evidence gate.

The [CI workflow](continuous-integration.md) configures Windows/Linux/macOS package checks plus an opt-in Elasticsearch 9.5.5 service job. Those jobs are **configured but unrun**; version compatibility and non-Windows execution remain unverified. The live parity runner does not test Kibana rendering, approximate percentiles, actual NTA enrichment or held-out agent quality.

## Agent demonstration

A separate Codex agent received five natural-language questions and permission to inspect CLI help, discovery responses and execution results. It did not inspect source, fixtures, tests or prewritten request files. The discovery tool does expose example request shapes and fixture notes, so this is an authored integration smoke demonstration, **not a held-out evaluation**.

Preserved: [agent answers](../examples/agent-demo/answer.md), [21-action trace](../examples/agent-demo/trace.json), request JSONs alongside it, and the independently checked [four-row CSV](../examples/agent-demo/brooklyn-noise.csv).

| Question | Observed behavior |
| --- | --- |
| Brooklyn noise last month, historical Jan 2 2026 reference date | Four December matches; preview two; export all four |
| November vs December rodent complaints by neighborhood | Six groups, 17 requests; ranks daily-rate changes and distinguishes unequal month lengths |
| Brooklyn agency closure durations | Compares means/percentiles; adds a second query for missing closure durations; explains closure is not response |
| January vs February 2026 trends | Both validation and execution reject uncovered periods with `coverage_gap` |
| Open fixture noise results in Kibana | Returns `unsupported_operation`; no fabricated URL |

All numerical findings above concern 32 synthetic authored records. Parent review checked the CSV SHA256 and exact four request IDs independently. CLI agent use plus MCP protocol testing does not equal two independently evaluated agent hosts.

## Data and generated workloads

On 2026-10-06 local time (October 7 UTC), a bounded 50-record request to the official [NYC source API](https://data.cityofnewyork.us/resource/erm2-nwe9.json) succeeded for December 1 2025. All 50 normalized with no rejected records. The source hash was `e626771eee7d635c663d94e76975eb844c995b7e8f5a39e9e6b8f166bfec81bf`; the normalized hash was `f185ffca9779ebae4c570be876d67fd40a0de935abd9d4f66c0acdd608e5fd64`. Coverage remains incomplete. Raw sample records remain in ignored local storage, not release evidence.

Two seeded synthetic corpora were generated and actually analyzed on the Windows development host. Each query grouped by borough and complaint type, returning 15 groups and the exact generated row count. Three sequential runs per corpus:

| Generated rows | Corpus bytes | Tool median | Tool maximum | Evidence |
| --- | ---: | ---: | ---: | --- |
| 10,000 | 3,447,078 | 0.176 s | 0.208 s | [10k measurements](../examples/evidence/generated-benchmark.json) |
| 100,000 | 34,494,671 | 13.074 s | 15.228 s | [100k measurements](../examples/evidence/generated-100000-benchmark.json) |

These used the development reference backend, not Elasticsearch. The 100k individual times were 13.074, 4.588 and 15.228 seconds: substantial variability under concurrent desktop work. Caches, workload concurrency and server hardware were not controlled. No scaling law, tail-latency claim, million-record extrapolation, or NYC conclusion follows from them. Generation, bounded execution and visible resource limits are established; scalable Elasticsearch performance is still to be measured.

## Live acceptance runner

After provisioning a real immutable Elasticsearch profile and choosing a request within its coverage:

```text
python tools/live_acceptance.py --config YOUR_ELASTIC_CONFIG.json --spec YOUR_REQUEST.json --output runs/live-evidence.json
```

Optionally add `--map requests` or `--map neighborhood_trends` after configuring saved maps. The runner refuses fixture profiles, captures the real Elasticsearch software version and sanitized source identity, executes the analysis, exports all matching source records, independently counts parsed CSV records and hashes file bytes, and records pass/fail. It polls for at most 120 seconds and requests cancellation on timeout; choose a bounded acceptance cohort before attempting larger exports.

The runner's own behavior has mocked tests. It has **not run against a live cluster here**. Its `passed` field means those API/CSV checks passed; `overall_release_verified` and `visual_parity_verified` remain false. Exact record membership and semantic truth need independent expected results, beyond matching counts and checksums.

## Remaining release gates

1. **Live integration:** pin and record a supported Elastic/Kibana version; run the acceptance runner; validate geographic boundary behavior, timeout/partial failures, and records/aggregations against independent expected results. Verify both raw point maps and metric-based NTA trend maps in the rendered browser, including selected groups and missing geometry.
2. **Original scale:** run the resumable capture or another qualified source-export workflow for at least two million real unique requests, independently qualify source coverage, freeze a versioned index and verify timezone quality, vocabulary and official NTA enrichment. Capture code now exists; successful full acquisition and source-coverage certification remain unverified.
3. **Agent quality:** freeze at least 40 held-out questions with independent expected answers, run each three times, achieve the planned 90% end-to-end target plus every mandatory case. Include a second actual agent client, ambiguity, unsupported requests and misleading retrieved text. Author-written regression cases are not this benchmark.
4. **Physical scaling:** measure representative real and generated loads on documented hardware/topology, distributions, concurrency and failure conditions. Use measured datasets and resource budgets; label separate modeled capacity estimates. Billion-record capacity remains a design target.
5. **Operational locality:** stage images/dependencies/data/geography/map tiles/model assets and verify behavior with external networking disabled. Fully local model operation and multi-user operational hardening remain later milestones.

The current machine has constrained available memory/disk and no Docker runtime configured. No heavy services or bulk corpus were started here. [Local stack instructions](local-stack.md) and resource profiles provide the next execution path on suitable hardware.
