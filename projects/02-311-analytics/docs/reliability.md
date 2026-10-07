# Export diagnostics and local recovery

Version 0.5 records where an export is working, protects a shared ingestion checkpoint against concurrent writers, and supplies a portable process stress check. These are local software guarantees; real Elasticsearch/Kibana and multi-million-record acceptance remain separate.

## Inspect an export

```text
python -m analytics311 result JOB_ID
python -m analytics311 cancel JOB_ID
python -m analytics311 recover-exports
```

Use the same `--config` profile that created the job. `result` returns status plus the latest persisted stage, timestamps, elapsed worker time and row/byte counters. Stages progress through `queued`, `validating`, `streaming`, `closing_source`, `verifying`, `publishing`, then a terminal status. Failures retain `stopped_stage`; secondary cleanup failures have `cleanup_error`.

Transitions persist immediately. Streaming counters update at most once per second while rows advance. This is a current snapshot, not an event log or heartbeat. Long source reads, startup delays or filesystem stalls may leave it unchanged. `deadline_at` describes the configured cooperative deadline; a blocking call can overrun it. Counters can lag the file. Elapsed time excludes queue time.

Source cleanup finishes before publishing a CSV. Cleanup failures preserve an earlier cancellation/budget/source error, remove incomplete output when possible, and release export admission capacity. Persistent filesystem failures may prevent metadata or cleanup publication; explicit recovery is still needed. Failures during interpreter/configuration startup after process creation can remain queued because the worker never initialized diagnostics.

Recovery uses OS leases, not stale timestamps or PIDs. Stop scheduling exports while recovering; an unstarted queued worker has no active lease yet. Active workers remain untouched. Abandoned jobs become failed and lose their reservation; partial output is removed, while a CSV published just before a crash is preserved as an **unverified orphan**. Export the original analysis again to create a new job. Recovery preserves the last observed stage/counters and records its own timestamp; it cannot reconstruct unrecorded work.

## Windows metadata races

The new two-worker workload reproduced access-denied errors while readers polled JSON status during atomic replacement. An independent held-reader test reproduced the publication failure. The fix closes the reader before JSON parsing and retries only Windows access/sharing denials around metadata reads and replacement: eight attempts, at most 225 ms of scheduled sleeps. Malformed JSON, missing files, disk-full errors and other platforms do not enter that retry loop. Persistent permission failures remain failures; a blocked OS call can exceed the sleep budget. [Recorded diagnosis](../examples/evidence/export-io-v0.5.json).

Windows requires compatible sharing modes for concurrent open/rename operations; the underlying behavior is documented by [Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilea) and in the [CPython issue tracker](https://bugs.python.org/issue46003). The new reproduction establishes this defect, but cannot retroactively prove the cause of the earlier v0.4 timeout.

## Ingestion ownership

Supply `--checkpoint PATH` for a local OS lease covering the CLI's validation, index creation, bulk ingestion, freeze and manifest publication. Competing use of the same checkpoint fails with `ingestion_busy` before source/index access. Process exit releases the lock automatically. Do not delete the persistent adjacent `.lock` file to unlock it.

Checkpoints remain schema v2. Existing v0.4 checkpoints are compatible; v1 checkpoints still require a new index/checkpoint. Linked files, redirected directories and unsafe Windows aliases are refused. This is local same-checkpoint coordination: omitted checkpoints, different checkpoints targeting one index, and distributed/network filesystems require separate single-writer coordination.

## Reproduce bounded worker trials

After installing the package, run the transferred tool from any writable working directory:

```text
python tools/stress_exports.py --output runs/export-stress.json
```

Defaults: three batches of two actual background exports, one additional batch after changing the default profile's working directory, a deliberate worker crash and recovery, then another batch. Each completed CSV must contain exactly the four authored expected IDs, correct row/byte counts and SHA256, with no partial file or capacity marker remaining. The fault worker waits after its first row, then exits abruptly through `os._exit` when the parent signals a private gate. This bypasses Python cleanup and tests OS lease release. Cleanup affects only subprocesses created by the harness; it never targets a PID from saved metadata.

The Windows virtual-environment launcher and executing interpreter were observed to have different PIDs. Killing only the launcher's `Popen` handle did not reliably establish interpreter death; the gate targets the executing worker itself. The corrected trial records its actual exit method and verifies recovery afterwards.

`--batches` accepts 1–20; `--concurrency` 1–2; `--timeout-seconds` bounds each batch; `--total-seconds` bounds overall polling. Reports contain sanitized stage/counter diagnostics and success/failure. Temporary workspaces contain the authored 32-row fixture only; receipt data excludes local paths and raw rows. A blocked OS call can overrun a cooperative budget. This tests finite local process behavior, not sustained production capacity, real NYC analysis, agent quality or Elasticsearch performance.

The earlier v0.4 timeout remains unexplained. Deliberately gated crashes are fault injection, not a reproduction of that incident. See [acceptance evidence](acceptance.md) and [distribution instructions](distribution.md).
