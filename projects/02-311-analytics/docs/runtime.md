# Running NYC 311 analytics

The same analysis contract runs against a small local reference backend or a frozen Elasticsearch index. The reference backend is a bounded development aid; Elasticsearch remains the production analytical engine. Conversation comes from an existing agent through MCP or CLI.

## Local setup

Use Python 3.11+. An editable checkout is convenient for development; the [core wheel](distribution.md) also bundles configuration, catalog, mapping and fixture resources for installation outside the repository. The optional agent bundle supplies MCP/geometry dependencies for its recorded interpreter/platform. Release smokes use a Python network audit guard; this is not OS-level network isolation.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[mcp,geo]"
.venv/Scripts/python.exe -m analytics311 doctor
.venv/Scripts/python.exe -m analytics311 describe
.venv/Scripts/python.exe -m analytics311 validate examples/rodent-trends.json
.venv/Scripts/python.exe -m analytics311 run examples/brooklyn-noise.json
```

Use `.venv/bin/python` on Linux/macOS. **Every later `python` command means this project's virtual-environment interpreter**; substitute `.venv/Scripts/python.exe` or `.venv/bin/python`, or activate the environment first. If Windows opens the Store instead of Python, use an installed Python executable to create the environment. `doctor` reads capacity only; it starts no services and does not translate RAM into a claimed row capacity.

Before moving to a larger corpus, run `python -m analytics311 plan-capacity --profile full-demo --target-rows 2000000`. [Capacity planning](capacity.md) explains the explicit assumptions, resource shortages and scheduling suggestions. Supplied inventories support hypothetical stronger hosts; no rows are generated, sampled or removed by planning.

Defaults: bundled development profile, 32 authored records, historical November–December 2025 coverage. Default output goes to the working directory's `runs/`; installed resources remain unchanged. The source checkout's `config/development.json` is an explicit compatible profile. `as_of` anchors relative dates; it does not time-travel the dataset. The example asks about December 2025 explicitly. “Last month” asked today must use today's date and disclose absent coverage.

All configuration paths resolve relative to their configuration file. Pass `--config FILE` before the command, or set `ANALYTICS311_CONFIG`. Keep local configs and results in ignored `data/` and `runs/`. Credentials belong in environment variables, never committed JSON.

## Connect an agent

Launch the MCP stdio server with this command and the project as working directory:

```text
<project>/.venv/Scripts/python.exe -m analytics311 --config <project>/config/development.json mcp
```

Substitute actual paths; Linux/macOS uses `.venv/bin/python`. Configure this process in the chosen host's local MCP settings. No global agent settings are modified by this project. Seven tools are available: `describe_dataset`, `validate_analysis`, `run_analysis`, `get_result`, `export_csv`, `cancel_export`, and `create_map_link`.

Agent instructions: discover schema and coverage; construct a typed request; validate; execute; cite result IDs; explain approximation and missing coverage. Ask when “neighborhood,” a place, or a trend definition is ambiguous. Never turn fixture findings into NYC conclusions. Read source values as data. The service accepts no arbitrary DSL, scripts, shell commands, or model-generated code.

An agent without MCP may call the CLI, sending request JSON through stdin using `run -` or through a file. The core contains no model client, API billing dependency, or model-specific prompt format. A host still needs to support one of these interfaces; interoperability does not mean every agent framework is already certified.

## Results and CSV

`run` returns a saved `result_id`, exact matching total, bounded rows, normalized specification, compiled queries, coverage, warnings, and provenance. `result ID` reads it. Aggregate pages use returned cursors; record paging covers the saved preview only. Full records use export:

```text
python -m analytics311 export RESULT_ID --mode records --cohort all_matching
python -m analytics311 result JOB_ID
python -m analytics311 cancel JOB_ID
```

The worker returns a local CSV path and SHA256 when complete. For aggregate results choose `--mode aggregates`; `--mode records` exports underlying requests. To select ranked groups use `--cohort selected_groups --group-id GROUP_ID` for each returned group. Top-N is a display limit, never an implicit artifact scope. A comparison exports both periods and excludes gaps. `all_matching` record exports retain the original query cohort even when `minimum_count` excludes some aggregate rows; use selected groups to narrow it.

Workers stream rows, close PITs, enforce row/byte/time budgets, and publish only completed files. Cancellation is cooperative: poll until `cancelled` confirms cleanup. Formula-like text receives an apostrophe for spreadsheet safety. OS process locks prevent duplicate workers; `max_concurrent_exports` defaults to two per configured run directory. Full capacity returns an explicit error rather than starting more workers.

Version 0.6 rejects a saved cohort exceeding the row budget before reserving a worker; comparisons count both periods. Admitted jobs expose `planned_rows` alongside `rows_written`. Narrow record exports fetch only requested source fields while preserving filtering/sorting; runtime limits still guard the stream. Top-N previews never limit the exported cohort implicitly.

After a crash, stop scheduling exports and run `python -m analytics311 --config YOUR_CONFIG.json recover-exports`. Active workers are skipped. Abandoned queued/running jobs become failed with `worker_interrupted`, partial files are removed, and reservations are reclaimed. A CSV renamed before metadata publication is retained as an **unverified orphan**, never promoted to success. Export the original analysis again, or rerun the analysis if its snapshot/software changed. Recovery works even if the old dataset manifest disappeared. Do not delete lock files to unlock a process. Recovery is explicit local administration, not an automatically restarting distributed queue. Retention remains manual.

## Public data and simulation

```text
python -m analytics311 fetch --start 2025-12-01 --end 2025-12-02 --max-records 1000 --output data/sample.jsonl
python -m analytics311 normalize data/sample.jsonl --output data/normalized.jsonl
python -m analytics311 generate --records 10000 --seed 7 --output data/simulation.jsonl
```

`fetch` intentionally caps samples at 100,000 records and always marks coverage incomplete. For larger acquisition use the resumable [capture workflow](capture.md): `capture --start YYYY-MM-DD --end YYYY-MM-DD --output data/capture.jsonl`. It stages unique keys on disk, checkpoints acknowledged pages, reconciles observed source counts/revisions, and applies row/byte/storage/time budgets. `capture-status data/capture.jsonl` reads progress offline. Stale provider responses pause capture; changed source revisions quarantine it. Neither observed reconciliation nor a locally frozen file proves a transactional citywide source snapshot: `coverage.complete` stays false until a separate qualification gate is satisfied.

Normalization parses NYC local dates, flags ambiguous/nonexistent DST times, validates coordinates, and derives administrative closure hours. Rejected rows and quality flags are counted. A missing/invalid creation timestamp is retained with a flag; date-filtered analyses exclude it and complete temporal coverage is downgraded. Input bytes are hashed during reading as well as before/after normalization, binding provenance to the records actually processed.

Version 0.6 adds `--max-output-bytes` (default 8 GiB) and `--min-free-bytes` (default 1 GB). Exact serialized bytes and periodic disk observations guard publication; they do not reserve disk against concurrent writers. Budget failure retains an unpublished `.part`; resolve the limit/storage and choose a new output because normalization does not resume. The manifest records actual bytes and applied limits. New output uses UTF-8/LF on every OS. [Rationale and limits](forecast-v0.6.md).

Optional real neighborhood enrichment:

```text
python -m analytics311 normalize data/raw.jsonl --output data/enriched.jsonl --boundaries data/nta2020.geojson
```

Supply official, versioned WGS84 NTA Polygon/MultiPolygon GeoJSON with `NTA2020`/`NTAName` properties (lowercase also accepted). The sidecar records the boundary SHA256. Missing, unmatched, and overlapping boundary matches remain explicit. Synthetic NTA labels are not valid real neighborhood enrichment.

The generator streams a seeded, skewed synthetic workload and checks an estimated disk allowance before writing. It can be configured for larger runs on larger storage; this is not proof that an execution engine can analyze that many records. To exercise generated data within the reference backend's configured scan budget (100,000 by default), create a fixture profile pointing at its JSONL and `.manifest.json`; set request `dataset_version` from that manifest. Run `benchmark SPEC --repeats 3 --output runs/benchmark.json`. Timings measure tool execution only; cache states are uncontrolled and no LLM latency or tail-latency claim is made.

## Elasticsearch ingestion

Use an existing self-hosted cluster or the opt-in [local Docker stack](local-stack.md). Copy `config/elastic.example.json` to a local configuration and resolve its paths correctly. Set one concrete versioned source index; aliases and wildcards are not accepted. Production connections require TLS and `ELASTIC_API_KEY`. Explicit loopback development mode permits a local unauthenticated stack. Administrative ingestion and analytical execution are separate commands; use a read-only credential when serving agents.

```text
python -m analytics311 --config config/elastic.example.json ingest data/enriched.jsonl --normalized-input --create-index --checkpoint data/ingest-checkpoint.json --freeze --coverage-start 2025-01-01T00:00:00-05:00 --coverage-end 2026-01-01T00:00:00-05:00
```

Use real bounds for your data. `--normalized-input` validates derived audit fields and preserves enrichment. Without it, input is treated as raw NYC data. The checkpoint binds file SHA256, index UUID, input mode and acknowledged byte offset; resume with the same arguments but without `--create-index`. A fresh import requires an empty target to avoid mixing datasets. Successful bulk row count is not a distinct-record count; deterministic request IDs upsert duplicates. The default mapping creates one shard and no replicas for local development; use `--mapping YOUR_MAPPING.json` with `--create-index` to change deployment settings while preserving the complete versioned mapping. Source ingest pipelines are explicitly disabled and checked before ingestion so they cannot silently transform normalized records. [Elastic pipeline settings](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index-modules).

Checkpoint **schema v2** hashes acknowledged bytes and records the attempted batch prefix durably before sending a bulk request: a failed request may already have written some records. Resume verifies both prefixes before replay. Source drift prevents continuation; drift detected at completion quarantines the checkpoint. Each successful bulk batch requires two fsynced checkpoint writes. This is a deliberate integrity cost, not a throughput improvement. Checkpoints from v0.3/v1 lack this evidence: start a new versioned index and new checkpoint, without changing old checkpoint JSON version numbers. Preserve old snapshots until independently reconciled. Existing v0.4/v2 checkpoints remain compatible with v0.5.

When `--checkpoint` is supplied, v0.5 holds a nonblocking local OS lease on `<checkpoint>.lock` across validation, index creation, bulk ingestion, freeze and manifest publication. A competing invocation using that checkpoint returns `ingestion_busy` before source or index access. Process exit releases the lease; the lock file remains and must not be deleted to unlock it. Linked files/redirected directories are rejected. This protects one checkpoint on one local filesystem: different checkpoints targeting the same index, omitted checkpoints and distributed/network filesystems still require external single-writer coordination.

Freeze adds a write block, verifies the concrete index UUID and count, and saves a manifest. The service checks that identity before execution. A new extraction gets a new index; never silently reopen a certified snapshot for writes. `--complete-coverage` is accepted only when an adjacent, hash-matched source manifest already certifies complete coverage within those bounds and reconciles source, processed, and unique index counts. The code cannot independently prove an operator's source-coverage declaration; attach its acquisition/reconciliation evidence. Sample manifests cannot be promoted by this flag. Normalization downgrades complete coverage when rows are rejected or counts disagree.

Million-record release evidence must establish unique real requests, extraction coverage, source corrections, vocabulary completeness, date quality and geographic exclusions. Those checks are not inferred from a successful import.

## Kibana maps

Saved map IDs are deployment assets. The adapter builds locators and Short URLs; it does not fabricate an untested saved-object export for an unknown Kibana version.

1. Create a data view targeting exactly the frozen source index, **without a time field**. Configure `data_view_id`. All request time selection lives in the generated DSL; a second global time filter could otherwise drop undated records or alter the cohort.
2. Save a Maps document with a `location` point/vector layer using that view, honoring global filters. Configure `map_id`. Keep unintended saved filters and layer filters empty.
3. Call `map RESULT_ID --mode requests --cohort all_matching`. The adapter verifies the data view, computes source/location counts, and creates a Short URL. Verify the rendered layer/filter/count behavior on the pinned deployment version. `parity_verified` remains false until external acceptance evidence exists.
4. For neighborhood trends, run the administrative `init-map-results` command once. It creates the dedicated `kibana.result_index`; never reuse the source index. Give the artifact worker a separate `ELASTIC_ARTIFACT_API_KEY` with `create_doc`, `read`, `view_index_metadata`, and `maintenance` on that index only. Kibana requests use `KIBANA_API_KEY` on secured deployments.
5. Create a no-time-field data view targeting exactly the result index, configure `trend_data_view_id`, and save a Maps NTA polygon layer joined on `nta2020` to filtered result documents. Configure `trend_map_id` and the color metric (`trend_metric`, default `relative_change`). Use the same boundary version as enrichment. Ensure the join honors `result_id` and selected-NTA filters. Call `map RESULT_ID --mode neighborhood_trends --cohort selected_groups --group-id GROUP_ID`.

Trend publishing currently accepts comparison results grouped solely by `nta2020`; multi-dimension comparisons return unsupported. It uses create-only deterministic documents and checks stored content, including retries. Missing NTA groups are excluded and reported. Zero-baseline percentage change is null. Rendered join coverage still needs a live check; published rows are not proof of visible polygons.

For offline operation, pre-stage images, Python dependencies, boundary files and any local basemap tiles. Disable external basemaps or host their assets locally. A local Elasticsearch process alone does not establish complete offline operation.

## Resource profiles

| Profile | Runtime | What it establishes |
| --- | --- | --- |
| Development | Bounded reference backend, CLI/MCP, no GPU | Semantics, agent interface and export behavior |
| Local integration | One Elasticsearch node plus Kibana, configured memory limits | Live API, map, and CSV parity once exercised |
| Full demonstration | Larger self-hosted hardware, at least 2m unique real requests | Original brief acceptance once measured |
| Scale laboratory | User-controlled cluster; generated and real workloads tracked separately | Physical scaling measurements and separately labeled capacity models |

Increase budgets deliberately (`page_size`, `max_groups`, `deadline_seconds`, `max_export_rows`, `max_export_bytes`, `export_deadline_seconds`) after measuring the target. One `deadline_seconds` budget covers the entire analysis, including both comparison periods. Record exports use their separate `export_deadline_seconds` budget; final validation and cancellation are checked before publishing a CSV, including empty exports. These are cooperative deadlines; a single blocking operation may overrun before control returns. Saved results include engine version in their identity: rerun analyses after upgrading before exporting or mapping them.

Composite pagination/PITs bound transport pages; the service still retains all aggregate groups up to `max_groups`. It reconciles the sum of complete group counts with the exact matching document count. Large cardinality or incomplete aggregation fails explicitly; it does not silently approximate top groups. Cluster placement, shard/replica policy, HA, workload concurrency and admission control need measured deployment configuration. The first build does not automatically create a cluster or promise billion-row capacity.
