# Live Elasticsearch fixture parity

`tools/live_parity.py` checks the real Elasticsearch adapter against 32 authored records and the reference engine. Run it on a suitable machine with an **already running** Elasticsearch. It never installs or starts services. No live run has been performed on the constrained development machine; unit tests are not compatibility evidence.

From this project directory, with the package installed in the active environment:

```powershell
python tools/live_parity.py --elastic-url http://127.0.0.1:9200 --allow-insecure-local --provision-fixture --output-dir runs/live-parity-001
```

For a secured server, use its HTTPS origin and set `ELASTIC_API_KEY` through your normal secret mechanism. Never put credentials in the URL. The API key needs index creation, write, read and management privileges scoped to `analytics311-parity-*`; optional cleanup additionally requires `delete_index`. Keep this namespace isolated from other writers, lifecycle policies and administrators during a run.

`--provision-fixture` is mandatory. The runner creates `analytics311-parity-<random UUID>-v1`; there is no existing-index selector. It normalizes the bundled fixture, verifies the local oracle, creates the explicit mapping with ingest pipelines disabled, bulk-ingests, then write-blocks and counts the index before analysis. If creation is rejected or its result is uncertain, it never ingests into or deletes that name. An uncertain create can still leave an index for manual inspection; Elasticsearch documents this behavior for create timeouts. [Create index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-create).

The output directory must be new. It retains normalized inputs, profiles, manifests, ingestion checkpoint, saved analyses, CSVs and `report.json`. Exit `0` means this bounded parity suite passed; `1` means a recorded execution/check failure; `2` means invalid invocation. Share `report.json` for a compact report without endpoint URLs, credentials, local paths or server node names. Other local artifacts include the configured endpoint and local file paths.

## Checks

Fourteen cases cover:

- All records; noise last month; nested AND/OR/NOT and numeric ranges; closed requests with missing duration.
- A half-open interval during repeated DST time; radius, bounding box and polygon selection.
- Two-dimensional aggregation, null groups, agency closure counts/means, empty aggregate.
- Weekly calendar zero-fill, neighborhood period comparison and zero-baseline trends.

Each case has independently authored **exact source IDs**. Every full-cohort CSV must match those IDs and count, contain no duplicates, and match its recorded checksum. Aggregate rows are compared to reference results, with exact counts/keys/nulls and `1e-9` absolute/relative tolerance only for floating-point values. Additional hand-calculated closure, zero-fill and trend anchors check selected shared service behavior. Closed count includes closed requests lacking duration; mean closure excludes those missing values.

The runner fixes Elasticsearch page size at **2**, bulk size at **7**, preview size at **2**, and bounded export/group budgets. It verifies successful record and composite continuation requests, plus balanced PIT opening/closing. This exercises pagination on a tiny fixture; it does not measure capacity. Composite continuation uses the returned `after_key`, as required by Elastic's [composite aggregation documentation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-composite-aggregation).

## Retention and cleanup

Index and evidence remain by default, including on failure. Add `--cleanup` only for a disposable test environment:

```powershell
python tools/live_parity.py --elastic-url http://127.0.0.1:9200 --allow-insecure-local --provision-fixture --output-dir runs/live-parity-002 --cleanup
```

Cleanup runs only after this invocation confirmed creation and captured the UUID. It rechecks exact generated name, current index UUID and an ownership token in mapping `_meta` before issuing a concrete-index delete. Mismatch refuses cleanup and fails the run; there are no wildcard deletes. Evidence files are always preserved. The [delete API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-delete) has no UUID compare-and-delete parameter, so concurrent administrator replacement between verification and deletion cannot be made atomic. Use retained-index mode on a shared cluster.

## CI and limits

The repository's optional `Project 2` workflow dispatch can run the same command against an ephemeral Elasticsearch service. Keep its report as a CI artifact, recording the actual server version. A workflow definition alone is not a successful live test. Run unit checks locally with:

```powershell
python -m unittest discover -s tests -p test_live_parity.py -v
```

Even a successful live parity report proves only these authored cases on the reported server version. It does **not** prove real NYC ingestion/coverage, two million records, scaling, Kibana rendering or joins, geographic boundary precision, approximate percentile accuracy, offline assets/models, or held-out agent accuracy. The reference path shares orchestration with the Elastic path; exact ID anchors and selected manual metric anchors reduce, but do not eliminate, common-code risk. Use [live acceptance](acceptance.md) and the remaining acceptance gates separately.
