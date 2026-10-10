# Real-corpus acceptance runner

Run on the explicit adequately sized integration host with Elasticsearch and
Kibana 9.5.5 already available. The runner neither downloads requests nor starts
services or a model. Install the project with its `geo` dependency; install
Playwright and Chromium on that host for browser checks. Keep model inference
stopped during performance measurements.

```sh
python tools/run_real_acceptance.py \
  --raw data/2025-raw.jsonl \
  --capture-manifest data/2025-raw.manifest.json \
  --boundaries data/nta2020-26b.geojson \
  --nta-receipt examples/evidence/official-nta2020-26b.json \
  --index nyc311-real-v1 --output-dir runs/real-v1
```

The raw JSONL must already exist with its adjacent hash-matched capture
manifest, at least two million distinct locally captured requests, successful
before/after reconciliation and the predeclared April-November 2025 window.
An explicit manifest must match the adjacent sidecar. Provider counts or partial
capture files are insufficient. The official boundary file must match the
retained receipt; its 197 residential NTA codes populate a run-specific catalog.

The output directory and source index must be new. The runner never deletes or
overwrites existing output/index data. It performs these dependent stages:

1. Rehash the actual capture and validate source/geography provenance.
2. Normalize and assign official neighborhoods; derive observed-window
   qualification, preserving `coverage.complete=false` and the limitations of
   a mutable upstream dataset.
3. Ingest with a checkpoint, freeze the index, reconcile captured/normalized/
   processed/indexed counts, and bind qualification to the index UUID.
4. Build an independent disk-backed SQLite oracle over the normalized corpus;
   compare complete Elasticsearch counts, groups, metrics and rankings for
   five predeclared filter/group/closure/geo/comparison families. Validate
   bounded request and trend CSVs, including three selected neighborhoods.
5. Provision actual Maps and check browser filter requests, rendered source
   membership/joins and CSV agreement for point, all-neighborhood and selected
   neighborhood maps. Retain screenshots and request/style evidence.
6. Measure serial/repeated/concurrent real queries, exports, memory samples,
   concurrent exports and an owned worker's abrupt exit/recovery/re-export.
7. Freeze the 40-question oracle for subsequent actual model execution. This
   is preparation, not a 120-trial agent result.

The `measurement-suite.json` records all five prospective specifications. Point
map/CSV qualification uses Brooklyn Noise - Residential requests on October
1, 2025; performance exports use that category/borough for the whole month.
Trends compare residential-neighborhood Rodent requests in June and
October, ranked by daily-rate change. Queries are never silently changed to
make an empty or failing cohort pass. Closure measures administrative elapsed
time to closure, not first response or verified repair.

`acceptance.json` checkpoints each stage before and after execution. Required
capture/index/oracle failure stops dependent work. Map and performance failures
remain failed stages while allowing agent-study preparation from the valid
analytical baseline. `--skip-maps` and `--skip-performance` explicitly record
`not_run`; they never produce overall acceptance. `--repeats` controls the
finite performance repetitions, default five. See [live Maps](live-maps.md),
[live performance](live-performance.md) and [qualification](qualification.md)
for narrower evidence semantics.

The generated `profile.json` (or `maps-profile.json` after successful
provisioning) retains runtime absolute paths and belongs with ignored execution
artifacts. `acceptance.json` names the correct agent profile. Once the local
model server is available, use that profile with the existing agent runner:

```sh
python tools/agent_evaluation.py run \
  --config runs/real-v1/maps-profile.json \
  --freeze runs/real-v1/agent-freeze.json \
  --database runs/real-v1/oracle.sqlite \
  --output runs/real-v1/agent-trials --endpoint http://127.0.0.1:8080/v1
```

Use `profile.json` if Maps provisioning failed. All attempts and remaining
trials must stay in the denominator; independent semantic review remains
required. No stage promotes normalized-corpus consistency to independent
normalization validity, reporting completeness, a capacity SLA, or overall
research acceptance.
