# Resumable public-data capture

`analytics311.capture.capture_window` acquires every observed service request in an explicit NYC-local `[start,end)` creation-date window. It uses the official 2020-present NYC dataset, fixed analytical columns, disk-backed uniqueness and bounded keyset pages. It has no 100,000-row sample ceiling. Increasing its budgets permits larger executions; it does not establish supported capacity.

```python
from analytics311.capture import capture_window, capture_status

result = capture_window(
    "2025-01-01", "2025-01-02", "data/2025-01-01.jsonl",
    page_size=200, max_rows=20_000,
    max_bytes=50_000_000, max_storage_bytes=150_000_000,
    max_pages=200, max_seconds=120, min_free_bytes=1_000_000_000,
    retries=3,
)
# After interruption, rerun the same window/output. Inspect without networking:
progress = capture_status("data/2025-01-01.jsonl")
```

The example is a bounded execution request, not evidence that it succeeded. Run it only with adequate free disk. Defaults permit up to 10 million records, 2 GB JSONL, 4.5 GB combined staging/output, 20,000 pages and one hour per invocation; they are configurable guards, not measurements. Page size is at most 5,000; one response at most 16 MiB, one record at most 1 MiB. At most five retries may be configured. No service, runtime, database server or provider account is installed.

Optional `SOCRATA_APP_TOKEN` is sent only as `X-App-Token`; never stored in the checkpoint or manifest. The origin and dataset are allowlisted. This adapter currently accepts only `erm2-nwe9`, for windows beginning in 2020 or later. The historical archive requires a separately verified adapter.

## What the implementation guarantees

- SQLite stages records under a primary key on the original text `unique_key`. Records and the next cursor commit together. A process-level file lock prevents concurrent writers to one job.
- Pagination orders `unique_key ASC` and requests `unique_key > last_key` within the same date predicate. It requires the observed NYC decimal-text identifier format; it rejects unexpected formats rather than assuming another collation.
- The first observation checks official schema, metadata update stamps, `count(*)`, `count(distinct unique_key)` and `max(:updated_at)`. Each data page checks truth/secondary modification observations and rejects a provider stale-response flag. Initial/final observations must agree; counts, distinct keys and maximum captured row update time must reconcile.
- Repeated IDs, descending keys, out-of-window records, count mismatches, changed schemas or changed revision observations quarantine the job. A quarantined checkpoint cannot silently start a new dataset; retain it and choose a new output after investigation.
- Interruptions, budget exhaustion and transient failures preserve committed progress. Resume requires the same source, window, selected columns and ordering. Page size and resource budgets may change without changing selection. A stale response pauses capture until current observations are available.
- JSONL is streamed from SQLite only after reconciliation. Its byte count, record count and SHA-256 are computed during serialization; publication uses an atomic rename. If manifest publication is interrupted, the already reconciled local stage can finish without querying the mutable provider again. An existing conflicting output/manifest is never overwritten.

The staging file is `<output>.capture.sqlite3`; the lock and any in-progress JSONL use the same output prefix. Keep these files in ignored `data/` storage. SQLite remains after completion for inspection and recovery. Do not delete a live job's staging files.

Row, page and JSONL-byte budgets apply to the whole job. Time budget applies to each invocation. Storage guards include SQLite and its journal companions, JSONL/partial files and a reserve for the remaining output copy. Free-disk reserve is rechecked per page and during finalization. Full source records are never collected in application memory. SQLite uses a bounded page cache; available hardware still constrains throughput and practical corpus size.

## What successful reconciliation does **not** establish

A successful manifest has:

```json
{
  "kind": "reconciled_public_capture",
  "source_kind": "real_public_records",
  "observed_complete": true,
  "extraction_complete": true,
  "transactional_source_snapshot": false,
  "coverage": {"complete": false, "observed_complete": true}
}
```

`observed_complete` means the enumerated window reconciled against the source observations retained in that manifest. It does **not** mean the provider offered one isolated transaction across requests. Update timestamps and revision headers are observations, not documented snapshot tokens. Equal counts can conceal substitutions; cached responses or undetected changes remain possible. The adapter therefore leaves analytical coverage uncertified. There is no operator override that converts a sample or this capture into complete citywide coverage.

Normalization and ingestion must carry this uncertainty forward. Use captured records for ingestion, data-quality work and explicitly limited queries. Population comparisons remain blocked until a separate source-coverage procedure establishes an appropriate guarantee, such as a provider-certified frozen extract or another reviewed immutable source. Freezing the resulting Elasticsearch index establishes local immutability; it does not retroactively establish source isolation.

## Verified source behavior and primary references

Research/probes: 2026-10-06 America/Los_Angeles. Only metadata, count aggregates and one record were fetched during adapter development; no bulk capture was run by its author.

NYC identifies `erm2-nwe9` as the 2020-present dataset and states that it is updated daily. Its documented row identifier is Unique Key, a text field; created/closed dates are floating timestamps. [Official dataset](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9/about_data), [NYC dataset changes](https://www.nyc.gov/opendata/news/all-news/311-Service-Requests-Updates).

The actual [metadata endpoint](https://data.cityofnewyork.us/api/views/erm2-nwe9.json) returned `unique_key: text`, `created_date/closed_date: calendar_date`, `latitude/longitude: number`, `location: point`, and text types for the selected categorical fields, including council district and police precinct. It supplied `rowsUpdatedAt` and `viewLastModified`. The adapter verifies those actual field names/types and pins their observations.

Socrata warns that paging has no implicit ordering; a stable order must be explicit. Its current client-center guide recommends keyset pagination for large datasets. The implemented comparison predicate follows that documented pattern, using the verified text identifier. [Paging documentation](https://dev.socrata.com/docs/paging.html), [SODA3 guide: keyset pagination](https://support.socrata.com/hc/en-us/articles/43491231777047-Using-the-SODA3-API).

System fields `:id` and `:updated_at` can be selected explicitly. The latter records row updates; full dataset replacement can update every row. The observed endpoint accepted aliases `source_row_id` and `source_updated_at`, and accepted `count(distinct unique_key)` together with `count(*)` and `max(:updated_at)`. [System fields](https://dev.socrata.com/docs/system-fields.html), [Count function](https://dev.socrata.com/docs/functions/count.html), [Maximum function](https://dev.socrata.com/docs/functions/max.html).

A bounded January 1, 2025 query reported 10,873 rows and 10,873 distinct keys, but its response also carried `X-SODA2-Data-Out-Of-Date: true`. Its truth/secondary modification observations were October 6 UTC; a one-record query carried October 7 UTC observations. Repeating the aggregate with `Cache-Control: no-cache` did not remove the stale flag. These are diagnostic observations, **not certified day totals**. They justify rejecting stale/inconsistent responses rather than treating timestamps as snapshot isolation. General HTTP response handling is described in the [Socrata response documentation](https://dev.socrata.com/docs/response-codes.html); the additional revision/freshness fields were verified directly in actual responses.

## Validation evidence

Mocked tests cover atomic interruption/resume, duplicate and omitted records, initial/final count and metadata changes, stale replicas, page/row/byte/storage/free-disk/time budgets, bounded retries, quarantine, output hash, and interrupted publication recovery. They establish local behavior only. A real multi-million capture, hardware capacity, final source certification and live Elasticsearch parity remain separate gates.
