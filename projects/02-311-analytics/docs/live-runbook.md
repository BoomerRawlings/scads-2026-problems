# Live execution kit — analytics311 0.5.0

Run on a capable host. These commands are an execution path, **not evidence that a live stack or millions of local records have been verified**. The kit adds deployment instructions to the unchanged verified core wheel. It contains no Python, containers, real records, credentials, geography, MCP dependencies or model. CLI use works with any agent able to invoke a process.

Use a fresh extracted directory. Commands below use Linux/POSIX shell and Python 3.11+; on Windows activate `.venv/Scripts/Activate.ps1` instead of `.venv/bin/activate`. The core wheels are platform independent; prior clean-install evidence is Windows CPython 3.12 only. Native Windows ARM64 deployment is not verified. Official 9.5.5 container manifests support **Linux amd64 and arm64**.

`LIVE-KIT-MANIFEST.json` hashes every other kit entry. The unchanged `BUNDLE-MANIFEST.json` covers only its original core entries; its scope does not expand to the added files. Hashes establish integrity, not publisher identity.

## 1. Install and check the target

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --no-index --find-links . --find-links dependencies analytics311==0.5.0
python -m analytics311 --version
mkdir -p data runs
python -m analytics311 doctor
python -m analytics311 plan-capacity --profile full-demo --target-rows 3655041 --storage data
docker version
docker compose version
docker info
```

Stop for missing runtimes or insufficient/unknown resources. Check Docker's actual memory and backing disk, as these may differ from Python's host inventory. A 32-GiB RAM-class machine, four or more available cores and approximately 100 GiB of free working storage is a conservative starting allowance for the full 2025 capture plus coexisting copies and assets, **not a measured requirement or capacity guarantee**. Record the actual CPU, available RAM, disk, topology and limits. Do not automatically reduce the requested population.

## 2. Start the pinned local lab

This Compose lab disables authentication and binds published ports to loopback. Use only public/synthetic data, a dedicated target and the supplied bindings. Remote access requires a separately secured deployment, trusted TLS and environment-managed `ELASTIC_API_KEY` / `KIBANA_API_KEY`; never place keys in URLs or committed JSON.

```sh
export STACK_VERSION=9.5.5
export ES_MEMORY=4g ES_HEAP=2g KIBANA_MEMORY=2g KIBANA_HEAP_MB=1536
docker compose -f deploy/compose.yaml --profile local config
docker compose -f deploy/compose.yaml --profile local pull
docker image inspect docker.elastic.co/elasticsearch/elasticsearch:9.5.5 --format '{{json .RepoDigests}}'
docker image inspect docker.elastic.co/kibana/kibana:9.5.5 --format '{{json .RepoDigests}}'
docker compose -f deploy/compose.yaml --profile local up -d
docker compose -f deploy/compose.yaml --profile local ps
curl --fail http://127.0.0.1:9200/
curl --fail http://127.0.0.1:5601/api/status
```

Wait for both healthy. Record actual server versions, image digests and rendered resource settings. For failures, inspect `docker compose -f deploy/compose.yaml --profile local logs --tail 100`; do not treat health as analytical acceptance. Both images must match. [Official installation guide](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-kibana).

Registry manifest-list digests observed October 7, 2026; metadata only, not downloaded or executed here:

| Image tag | Manifest-list SHA256 |
| --- | --- |
| `elasticsearch/elasticsearch:9.5.5` | `13b4a40bb095774f5fda635e45fd5677cc6a26565e42b24997b0c72b88e75984` |
| `kibana/kibana:9.5.5` | `13b72ce7222c36e4213229004ae62a87aeb32fd372ebfa6fb38f7a3285fdbb78` |

Compare current registry identity before execution; investigate changed tags. A platform-specific digest differs from its manifest-list digest. Sources: [Elasticsearch registry](https://www.docker.elastic.co/r/elasticsearch/elasticsearch:9.5.5), [Kibana registry](https://www.docker.elastic.co/r/kibana/kibana:9.5.5).

## 3. Prove authored live parity first

```sh
python tools/live_parity.py --elastic-url http://127.0.0.1:9200 --allow-insecure-local --provision-fixture --output-dir runs/live-parity-001
```

Require exit zero and `report.json` passing all fourteen cases, exact CSV membership and continuation/PIT checks. It creates a dedicated random index containing 32 authored records and retains it. This proves only those cases on that server; it does not prove Kibana rendering or real-data scale. Use a new output directory for every run. Investigate failures before large ingestion.

## 4. Acquire a real, bounded creation-date window

A current official-source probe observed **3,655,041 rows and distinct request keys for 2025**. This is an upstream observation, not locally captured records or certified source isolation. Reconciliation must succeed on the actual run. [NYC source](https://data.cityofnewyork.us/resource/erm2-nwe9.json).

On adequately sized storage, run the resumable capture with explicit whole-job limits and a one-hour invocation limit:

```sh
python -m analytics311 capture --start 2025-01-01 --end 2026-01-01 --output data/2025-raw.jsonl --page-size 1000 --max-rows 5000000 --max-bytes 6000000000 --max-storage-bytes 18000000000 --max-pages 10000 --max-seconds 3600 --min-free-bytes 10000000000
python -m analytics311 capture-status data/2025-raw.jsonl
```

Resume by repeating the same capture command; inspect status first. Budget pauses retain progress. A provider-stale response pauses safely; a changed source revision quarantines the capture. Never edit a checkpoint or discard freshness checks to force completion. A quarantined job requires investigating the source and a new output name. Daily source updates can prevent a long capture from reconciling; obtaining a qualified immutable export is then an external data requirement. No output JSONL is published before reconciliation.

After successful publication, normalize exactly that capture:

```sh
python -m analytics311 normalize data/2025-raw.jsonl --output data/2025-normalized.jsonl
```

For actual neighborhood analysis, stage official versioned [NTA GeoJSON](https://data.cityofnewyork.us/City-Government/2020-Neighborhood-Tabulation-Areas-NTAs-/9nt8-h7nd) in WGS84, with `NTA2020` / `NTAName` properties. Install matching Shapely 2.x wheels and their dependencies separately; core does not include them. Replace the preceding normalization command with:

```sh
python -m analytics311 normalize data/2025-raw.jsonl --output data/2025-normalized.jsonl --boundaries data/nta2020.geojson
```

Do not execute both normalization variants against the same output. Preserve the boundary release/source/hash and join-quality counts. New enrichment after ingestion requires a new normalized file and versioned index.

## 5. Configure, ingest and freeze

Create a local configuration alongside its example. Use a fresh concrete index and manifest for this attempt:

```sh
python - <<'PY'
import json
from pathlib import Path
p = Path('config/live.json')
c = json.loads(Path('config/elastic.example.json').read_text())
c.update(index='nyc311-2025-v1', manifest_path='../data/2025-index.manifest.json', runs_dir='../runs/2025')
with p.open('x', encoding='utf-8') as f:
    json.dump(c, f, indent=2)
PY
python -m analytics311 --config config/live.json ingest data/2025-normalized.jsonl --normalized-input --create-index --mapping config/mapping.json --checkpoint data/2025-ingest.json --batch-size 500 --freeze --coverage-start 2025-01-01T00:00:00-05:00 --coverage-end 2026-01-01T00:00:00-05:00
```

Resume an interrupted ingestion with identical arguments **except `--create-index`**. Keep one writer and the same checkpoint. Checkpoint v2 verifies acknowledged and attempted source prefixes. Do not reuse a populated index for another capture or unfreeze a published index. The included mapping uses one shard and zero replicas; this is a local lab, not high availability.

Capture's `coverage.complete` remains **false** even after observed reconciliation. The command intentionally omits `--complete-coverage`. Freezing establishes local immutability, not transactional upstream coverage. Comparisons and calendar zero-fill remain blocked until independently qualified immutable source evidence satisfies the separate coverage gate. Never promote this capture by editing its manifest.

Check actual local source, normalization and unique-index counts; no million-row claim follows from a provider count alone:

```sh
python - <<'PY'
import json
from pathlib import Path
from analytics311.workloads import source_manifest
raw = source_manifest('data/2025-raw.jsonl')  # Rehashes actual bytes.
normal = source_manifest('data/2025-normalized.jsonl')
index = json.loads(Path('data/2025-index.manifest.json').read_text())
assert raw['source_kind'] == 'real_public_records' and raw['source_dataset'] == 'erm2-nwe9'
assert raw['observed_complete'] is True
n = raw['row_count']
assert n >= 2000000 and raw['unique_key_count'] == n
assert normal['row_count'] == index['row_count'] == index['ingestion']['processed_rows'] == n
assert normal['source_sha256'] == raw['sha256']
assert index['ingestion']['source_sha256'] == normal['sha256']
assert index['immutable'] is True and index['coverage']['complete'] is False
assert not any(normal['quality_counts'].get(k, 0) for k in ('rejected', 'invalid_json'))
print(json.dumps({'locally_reconciled_real_unique_requests': n, 'index': index['index'], 'coverage_complete': False, 'quality_counts': normal['quality_counts']}))
PY
python -m analytics311 --config config/live.json describe
```

Retain source manifests, hashes, checkpoints, index UUID and quality counts. These cross-checks use the acquisition/ingestion ledgers; they are not independent semantic truth. Independently verify source IDs, sample filters, dates, category vocabulary and geometry before acceptance. Missing/invalid/DST-ambiguous dates and absent coordinates remain exclusions, not zero values.

## 6. Configure real Kibana assets

Open `http://127.0.0.1:5601`. Create a data view whose title is **exactly `nyc311-2025-v1`**, with **no time field**. Create and save a Maps document with a document/point layer using `location` from that view. Enable global filters, clear saved query/layer filters and disable external basemaps or use a staged local layer. Store the actual IDs in `config/live.json` under `kibana.data_view_id` and `kibana.map_id`; keep the other settings. IDs come from the created assets, never guessed placeholders.

For neighborhood trends, only after real NTA enrichment and independently qualified comparison coverage:

```sh
python -m analytics311 --config config/live.json init-map-results
```

Create a no-time-field data view for the configured exact `kibana.result_index`. Save a map using the **same pinned NTA boundary version**, joining boundary `NTA2020` (or lowercase `nta2020` only if that property is actually present) to result `nta2020`. Make the join honor `result_id` and selected-NTA global filters; style the configured `relative_change` metric and show null/absent joins distinctly. Set actual `trend_data_view_id` and `trend_map_id`. On secured targets, provide separate `ELASTIC_ARTIFACT_API_KEY` privileges scoped to this derived index (`create_doc`, `read`, `view_index_metadata`, `maintenance`). Source index privileges remain read-only for analytical agents.

The present capture path cannot certify the temporal coverage needed for that trend call. Saving assets alone does not pass the trend-map gate. A returned link never establishes rendered filter/geometry parity.

## 7. Run a bounded real cohort through API, CSV and map

Generate a request from the actual frozen dataset ID. The historical day is explicit, not relabeled “last month.” This uses exact complaint types in the starter catalog; qualify that vocabulary separately.

```sh
python - <<'PY'
import json
from pathlib import Path
m = json.loads(Path('data/2025-index.manifest.json').read_text())
s = {'schema_version':'1', 'dataset_version':m['dataset_version'], 'operation':'records',
     'timezone':'America/New_York', 'preview_limit':10,
     'time':{'gte':'2025-12-01T00:00:00-05:00','lt':'2025-12-02T00:00:00-05:00'},
     'filters':{'all':[{'field':'borough','op':'eq','value':'BROOKLYN'}, {'category_family':'noise'}]}}
with Path('data/live-cohort.json').open('x', encoding='utf-8') as f:
    json.dump(s, f, indent=2)
PY
python tools/live_acceptance.py --config config/live.json --spec data/live-cohort.json --output runs/live-cohort-001.json --map requests
```

Require successful execution, a nonempty useful cohort, exact CSV count/hash checks and a usable real map link. The runner polls exports for at most 120 seconds; the example profile limits exports to one million rows/256 MiB. This validates a bounded cohort **against** the real multi-million index, not a full-corpus export. Do not silently relax a failed budget; investigate and choose explicit measured settings or a documented smaller acceptance cohort.

Open the returned map. Independently compare filters, exact CSV IDs/count, missing-coordinate exclusions and displayed source details. Record screenshots and actual browser requests; point-layer display limits mean rendered symbol count can differ from geolocated population. Verify radius/polygon boundaries and selected-group joins separately. The runner deliberately leaves `visual_parity_verified` and `overall_release_verified` false.

Preserve reports before stopping the lab:

```sh
docker compose -f deploy/compose.yaml --profile local stop
```

Volumes remain. Full release acceptance still requires rendered raw/trend map evidence, independently checked answers, held-out agent evaluation and measured scaling/failure behavior. Fully offline operation additionally needs staged containers/geography/tiles/model assets and actual network-disabled verification.
