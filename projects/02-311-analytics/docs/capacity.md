# Capacity planning

The planner answers “what resources should we investigate?” It does not start services, edit configuration, download rows, sample a requested dataset or certify a deployment. `modeled_fit` means the supplied inventory meets explicit arithmetic assumptions. Every result carries `evidence_kind=modeled_capacity` and `ready_for_production=false`.

```powershell
analytics311 plan-capacity --profile development --target-rows 1000 --storage .
analytics311 plan-capacity --profile full-demo --target-rows 2000000 --storage D:/311-data
analytics311 plan-capacity --profile scale-lab --target-rows 1000000000 --inventory host.json --assumptions assumptions.json
```

Use an existing directory on the actual data filesystem. A host drive and a Docker VM's backing store may have different limits. Custom inventory JSON describes one explicit resource envelope, not proof that resources can be combined across machines.

## Profiles and decisions

| Profile | Intended experiment | Modeled memory floor | CPU floor | Export workers ceiling |
| --- | --- | --- | --- | --- |
| `development` | Bounded in-process fixture | 256 MiB plus rows/buffers | 1 | 1 |
| `local-integration` | Small real Elastic/Kibana integration | 4 GiB plus buffers | 2 | 1 |
| `full-demo` | At least two million real unique requests | 12 GiB plus buffers | 4 | 2 |
| `scale-lab` | Plan physical scaling experiments | 32 GiB plus buffers | 8 | 4 |

These are application-authored starting assumptions, not vendor minimums or measured capacities. Elasticsearch memory requirements depend on query cardinality, shard layout, JVM/native memory and filesystem cache; rows do not determine heap size. Leave Elasticsearch's default automatic heap sizing unless a measured deployment justifies an explicit setting; the planner does not set heap. [Elastic JVM settings](https://www.elastic.co/docs/reference/elasticsearch/jvm-settings)

`insufficient` identifies a known shortage. `unknown` means required observations are missing; missing RAM is never treated as zero or sufficient. An otherwise large host with little currently available memory can fail. Default fixture plans above 100,000 rows fail their existing guard; no smaller sample is substituted. Review a bounded fixture configuration explicitly or use Elasticsearch.

Only scheduling suggestions change with available CPU/RAM: `budgets.page_size`, `budgets.max_concurrent_exports`, capture page size and ingestion batch size. Missing resources suggest one export worker and 100-row pages. Suggestions remain advisory. Row caps, analytical semantics, coverage claims and export completeness remain unchanged.

## Transparent storage estimate

Defaults per record: raw JSON 1,200 bytes; SQLite capture staging 2,000; normalized JSON 900; primary index 1,600; fixture resident memory 4,096. These are estimates awaiting corpus measurements. Raw and normalized copies each default to one. `full-demo` and `scale-lab` assume one replica; other profiles assume zero.

```text
raw       = rows × raw_bytes_per_record × raw_copies
staging   = rows × staging_bytes_per_record
normalized= rows × normalized_bytes_per_record × normalized_copies
indices   = rows × index_bytes_per_record × (1 + replicas)
merge     = indices × merge_overhead_fraction
peak      = raw + staging + normalized + indices + merge + fixed_disk_bytes
required free space = ceil(peak / (1 - free_disk_fraction))
```

Fixture plans omit index/merge storage. Default merge overlap is 50%; free-disk reserve 25%; fixed runtime/files overhead is 1 GiB for fixtures and 5 GiB otherwise. All copies coexist in this conservative model. Backups, snapshots, additional exports, model weights and offline map assets are extra. Actual capture staging/index expansion can exceed these assumptions; calibrate with real files and index statistics.

Replicas need distinct suitable data nodes. The combined storage estimate does not prescribe shard count, per-node placement, redundancy or cluster topology. A billion-row scenario allocates no rows and predicts no timing.

`assumptions.json` may override any documented sizing key. Unknown keys, booleans, negative sizes, nonfinite fractions and invalid ranges fail with `invalid_capacity_plan`.

## Inventory scope

`inventory(path)` returns JSON-safe `cpu`, `memory`, `disk`, `cgroup` and warnings. The planner accepts those fields or a partial custom inventory:

```json
{
  "cpu": {"effective_count": 8},
  "memory": {"effective_available_bytes": 25769803776},
  "disk": {"free_bytes": 966367641600},
  "warnings": ["Hypothetical host, not a measured deployment"]
}
```

Windows physical memory comes from `GlobalMemoryStatusEx`; its available value reports immediately reusable physical memory. Windows job-object limits are not probed. [Microsoft MEMORYSTATUSEX](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/ns-sysinfoapi-memorystatusex)

Linux uses `/proc/meminfo`, CPU affinity when available, and visible cgroup v1/v2 ancestor memory/quota limits. Effective available memory uses the minimum of host availability and each finite ancestor's remaining memory. Unmapped, missing or invalid controller information, unreadable usage, or hidden namespace ancestors produce unknown effective resources. This conservatism can require an explicit deployment inventory. [Linux cgroup v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html), [v1 memory controller](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v1/memory.html)

macOS uses `sysctl hw.memsize` and `vm_stat` free pages with the reported page size; free pages are only a conservative lower bound, excluding reclaimable caches. Failures yield nulls. CPU counts do not measure contention. Filesystem free space does not verify user quotas. Remote clusters, Docker VM limits, GPUs and LLM memory are outside the probe. All observations can change immediately.

## Reproducible model scenarios

[Scenario inputs](../examples/capacity/scenarios.json) contain authored constrained-desktop, 32-GiB workstation and large-server resource envelopes; evaluate each at 1,000 fixture, 2,000,000 full-demo and 1,000,000,000 scale-lab rows. These nine calculations simulate sizing arithmetic only. Unit tests verify exact storage arithmetic, strict/unknown inputs, weak/strong outcomes, unchanged row counts, bounded suggestions, cgroup ancestors and cross-platform memory parsing.

Replay the scenarios from the project checkout with an installed `analytics311` package:

```powershell
.venv/Scripts/python.exe tools/capacity_scenarios.py --source examples/capacity/scenarios.json --output runs/capacity-replay.json
```

The output directory must exist; an existing report is never overwritten. The runner accepts at most 1 MiB of input and 100 host/scenario combinations, preserves every full plan and records package version, timestamp and SHA-256 of the exact input bytes. [Version 0.3 replay evidence](../examples/evidence/capacity-scenarios-v0.3.json) is an actual execution of this arithmetic runner, not an actual dataset-scale experiment.

Next physical experiment: record actual corpus/index bytes per record, ingest batches and failures, peak RAM/disk, representative correctness and latency, concurrent exports, restart recovery and per-node distribution. Repeat at increasing real sizes. Original-brief acceptance still requires the live Elastic/Kibana, unique real corpus, agent and visual checks in [acceptance.md](acceptance.md).
