# Bounded measurements on the real snapshot

`tools/measure_live.py` measures actual Elasticsearch queries, bounded record exports and abrupt export-worker recovery against an immutable index backed by a reconciled capture with **at least two million real records**. Generated data and fixture profiles fail preflight. The exact Elasticsearch count must match the manifest before measurement starts.

```text
python tools/measure_live.py --config data/live-profile.json --suite data/performance-suite.json --oracle-csv data/export-expected-ids.csv --work-dir runs/new-performance --output examples/evidence/real-performance.json
```

Install the project on the execution host first so background workers can import it from the isolated working directory. `--work-dir` and `--output` must be new. The original profile, source index and other run stores are unchanged. The copied profile is private runtime state; publish the sanitized report, not that profile.

The suite is one JSON object with `analyses` and `export`. `analyses` contains exactly five named full AnalysisSpecs: `filter` (filtered records), `group` (categorical aggregation), `closure` (administrative closure-duration metrics), `geo` (geographic query), and `compare` (qualified period comparison). `export` is a records AnalysisSpec with an explicit creation-date window. The real acceptance driver prospectively selects all October 2025 Brooklyn `Noise - Residential` requests for performance exports; its point map remains the separate October 1 cohort. All specs must name the actual frozen dataset version and covered dates. Cohorts above the fixed limit fail; none are truncated or narrowed after observing results.

The independent oracle is a one-column CSV with header `unique_key`, containing the complete expected export cohort calculated separately from the captured or normalized artifact, for example by the independent SQLite oracle. It must contain 1–50,000 unique nonempty IDs and fit in 16 MiB. Measured CSVs contain these nine columns, in order: `unique_key`, `created_date`, `complaint_type`, `descriptor`, `borough`, `agency`, `status`, `nta2020`, `closure_hours`. Every normal/concurrent/recovered export must match that header and contain complete CSV rows; IDs must match the independent oracle without regard to ordering. Duplicate, missing and extra records fail. This oracle establishes membership, not independent per-cell value parity for the other eight columns. A same-service export is not an independent oracle. The report pins supplied bytes and sorted membership, and records actual exported columns, bytes and rows. Point-map verification retains its separate one-day, ID-only CSV.

## Workload and limits

- Five serial repetitions per query family by default, retaining every duration and output digest. Optional repetitions: 1–10. Fresh service initialization and result persistence are included in client timings.
- The same five queries execute with thread-pool limits of one and two, using fresh service instances and one frozen snapshot. Repeated/concurrent output digests must agree. This checks repeatability; independent semantic parity remains a separate acceptance check.
- A normal bounded CSV export, two requested concurrent exports, and a re-export after deliberate worker death must match the independent membership oracle. The concurrent stage records observed overlap of its owned launch handles; if two never overlap, concurrency qualification fails even when both exports are correct. Process overlap is not proof of simultaneous row serialization or CPU execution. The inherited export budgets are capped at 50,000 rows, 16 MiB and 180 seconds per worker. A profile with insufficient concurrent-worker capacity fails honestly.
- A privately instrumented worker queries the real index, writes its first row, and holds its OS lease. Recovery must recognize it as active. A gate then instructs that actual interpreter to call `os._exit(86)` without normal cleanup. Recovery must mark exactly its job interrupted, remove its partial CSV and reservation, and permit the verified re-export. The runner never terminates an arbitrary PID from metadata and never restarts the index or service.
- Overall cooperative budget: 900 seconds by default, configurable from 60–1,800 seconds. Pending query futures are cancelled on failure; already-running bounded HTTP calls or thread tasks can finish after the deadline. The report retains partial observations and fails on incomplete execution; it does not silently retry a failed measurement as a success.

The recovery test owns its child process handles and isolated run store. Normal cleanup first requests cooperative cancellation, then terminates only remaining owned handles if needed; forced termination makes the receipt fail. Abrupt death can leave a server PIT until its own expiration. This test establishes local job recovery, not index recovery, host-reboot recovery or distributed queue behavior.

## Memory, cache and interpretation

The runner records [Elasticsearch node statistics](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-nodes-stats) before, approximately every second during, and after the workload: JVM heap, process virtual bytes/CPU, query/request-cache counters and search counters. Node host/name fields are excluded. These APIs do **not** make virtual memory equivalent to resident memory. Actual runner RSS and RSS of owned launch handles are sampled from Linux `/proc`; unavailable values remain null. The gated worker also reports its actual interpreter RSS. A separate `docker stats` receipt may describe container memory accounting; label it separately from process RSS.

Empty or invalid heap/virtual-memory observations fail the memory gate. Any
sampler exception is retained; a silently stopped sampling thread cannot qualify
complete observations. Cleanup continues across every owned handle even if one
wait or termination attempt fails, and retains each failure.

Serial repetitions precede concurrency one, concurrency two, exports and recovery. **Cache state is uncontrolled**; first-query timings are not labeled cold-cache measurements. No cache clearing occurs. The sampler adds overhead and can miss short peaks; observed launch-handle concurrency and sampled memory are not OS-wide process counts or guaranteed maxima.

The report provides raw latency samples, medians and observed maxima, finite batch query rates, CSV bytes/rows/time, memory observations and exact recovery checks. It does not invent SLA thresholds after seeing results or claim tail latency, maximum supported throughput, arbitrary scale, overall agent quality or full release acceptance. Live results must be executed and retained before citing usable performance.
