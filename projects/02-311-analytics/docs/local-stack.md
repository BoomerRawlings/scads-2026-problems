# Optional local Elasticsearch and Kibana

The [Compose file](../deploy/compose.yaml) provisions an explicitly selected `local` development profile: one Elasticsearch node and one Kibana instance, with persistent named volumes. It has **not been run or integration-tested here**; Docker was unavailable on this development machine. Fixture tests do not establish compatibility with a real Elastic deployment.

Use only public NYC 311 or synthetic development data. Authentication is disabled; published ports bind to `127.0.0.1` only. Other local processes and containers on this Compose network can access the services. Keep these bindings intact. Shared or remotely accessible deployments require a separately secured cluster and configuration.

## Choose a version and resource budget

`STACK_VERSION` is required, with no default or `latest` tag. Both images use that same explicit version. Elastic's current [single-node Docker guide](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-basic) names **9.5.5**, making it a candidate for the first compatibility test, not a project-certified version. Record the selected version and resolved image digests with every live benchmark. Verify that the images support the target CPU architecture before provisioning.

| Setting | Default | Purpose |
| --- | --- | --- |
| `ES_MEMORY` | `2g` | Elasticsearch container memory ceiling |
| `ES_HEAP` | `1g` | Equal JVM initial/maximum heap |
| `ES_CPUS` | `2` | Elasticsearch CPU ceiling |
| `KIBANA_MEMORY` | `1g` | Kibana container memory ceiling |
| `KIBANA_HEAP_MB` | `768` | Node.js old-space heap limit, MiB |
| `KIBANA_CPUS` | `1` | Kibana CPU ceiling |
| `ES_HTTP_PORT` | `9200` | Host loopback Elasticsearch port |
| `KIBANA_HTTP_PORT` | `5601` | Host loopback Kibana port |

These are starting limits, not measured capacity or guaranteed startup requirements. Leave additional host/VM memory for the OS, filesystem cache, Python and Docker. Heap must fit below its container limit. A 3 GiB combined container ceiling does not mean a 3 GiB machine can run this stack. Inventory with `python -m analytics311 doctor`; inspect Docker's available memory and storage as well. Named volumes consume the Docker engine's disk, which may differ from the project's disk reported by `doctor`.

Use `python -m analytics311 plan-capacity --profile local-integration --target-rows 10000` for an explicit sizing model, or select `full-demo` with `--target-rows 2000000`. Inspect all assumptions and resource checks in the [capacity plan](capacity.md). A modeled fit neither provisions services nor establishes measured capacity; no dataset is silently reduced.

The lab disables Elasticsearch memory-mapped storage to avoid depending on host `vm.max_map_count` configuration. It also disables ML and automatic GeoIP downloads; the project computes geography locally. Before larger benchmarks, choose and record storage settings appropriate for that host using Elastic's [Docker production guidance](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-prod). Changing resources does not change the selected dataset or analytical meaning.

## Start manually on a capable host

Run from the project directory after Docker Engine/Desktop and Compose are available. These commands are instructions; the application never launches containers automatically.

PowerShell:

```powershell
$env:STACK_VERSION = '9.5.5'
docker compose -f deploy/compose.yaml --profile local config
docker compose -f deploy/compose.yaml --profile local pull
docker compose -f deploy/compose.yaml --profile local up -d
docker compose -f deploy/compose.yaml --profile local ps
```

POSIX shell:

```sh
export STACK_VERSION=9.5.5
docker compose -f deploy/compose.yaml --profile local config
docker compose -f deploy/compose.yaml --profile local pull
docker compose -f deploy/compose.yaml --profile local up -d
docker compose -f deploy/compose.yaml --profile local ps
```

Review the rendered configuration before `up`. If allocating more resources, set overrides before running the same commands. For example, on a host with sufficient spare memory:

```powershell
$env:ES_MEMORY = '4g'
$env:ES_HEAP = '2g'
$env:KIBANA_MEMORY = '2g'
$env:KIBANA_HEAP_MB = '1536'
docker compose -f deploy/compose.yaml --profile local config
docker compose -f deploy/compose.yaml --profile local up -d
```

Inspect failures with `docker compose -f deploy/compose.yaml --profile local logs --tail 100`. Health checks gate Kibana startup on Elasticsearch and report readiness; they do not validate analytical correctness. An out-of-memory failure calls for a suitable resource allocation or a return to fixture development. No automatic dataset downsampling or cluster expansion occurs.

Stop without removing volumes:

```sh
docker compose -f deploy/compose.yaml --profile local stop
```

## Connect the analytical tools

[Elasticsearch](http://127.0.0.1:9200) and [Kibana](http://127.0.0.1:5601) use the URLs in [the example Elastic configuration](../config/elastic.example.json). If changing ports, update those URLs too. Keep the example's explicit `allow_insecure_local` flags for this loopback lab. Use a separate configuration file for another installation; file paths resolve relative to its containing directory.

Follow the [main README](../README.md) to normalize a bounded source, create the explicit mapping, ingest, and freeze its index/manifest. Inspect `python -m analytics311 ingest --help` before running administrative actions. A sampled source must keep incomplete coverage; `--complete-coverage` requires actual source reconciliation.

Before using real data, run [synthetic live parity](live-parity.md) to compare exact record membership, aggregations and complete CSVs on the selected engine version. It provisions a dedicated fixture index only with explicit `--provision-fixture`; it does not establish map rendering or real-data accuracy.

Create a Kibana data view and saved Maps layer for the exact frozen index, then replace `CONFIGURE_DATA_VIEW_ID` and `CONFIGURE_SAVED_MAP_ID` in the chosen configuration. Those placeholders deliberately do not fabricate saved objects. Configure every relevant layer to honor global filters and dates. Live verification must compare the same saved analysis against the complete CSV and the actual map selection, including radius/polygon filters and missing coordinates. A working link or healthy container alone does not close this gate. Neighborhood trend maps additionally need the pinned NTA boundaries and derived-result layer described in [the build plan](build-plan.md).

## Offline operation and larger installations

Kibana telemetry opt-in is disabled and locked using the documented [telemetry controls](https://www.elastic.co/docs/reference/kibana/configuration-reference/telemetry-settings). Elastic Maps Service connections are disabled using the documented [map setting](https://www.elastic.co/docs/reference/kibana/configuration-reference/general-settings#map-settings). Load local boundary layers; a blank background is acceptable during initial map tests. To use a basemap offline, provision a local tile service and point Kibana's `map.tilemap.url` at it. Disabling the external map service alone does not supply map tiles.

For an offline claim, stage matching container images, Python packages, datasets, NTA boundaries, and any basemap/model assets beforehand. Then test with external networking disabled and verify browser requests as well as container traffic. This Compose file is not a network-isolation proof; telemetry settings do not guarantee every optional plugin is offline.

On stronger hardware, increase explicit container/query budgets only after measuring memory, disk, latency and failures. For multi-node or very large deployments, point the same analytical tool contract at a user-controlled Elasticsearch/Kibana installation with its own security, shard layout, backups and operational configuration. This single-node file does not implement high availability, automatic sharding decisions, or unlimited scaling. Report real-data benchmarks, generated workloads and projected capacity separately; a billion-record design target remains unmeasured until executed.
