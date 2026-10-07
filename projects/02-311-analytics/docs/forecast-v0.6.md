# Scale thought experiment and resulting changes

This is a static review of the 0.5 implementation, followed by targeted 0.6 changes. The scenarios below were **not executed**. No throughput, memory peak, million-row success rate or completion time is inferred. Small unit checks verify the changed rules; they are not scale evidence.

The earlier source preflight reported 3,655,041 distinct requests for 2025. That provider observation supplies a prospective workload size only; there is still no qualified local multi-million corpus or live Elastic/Kibana acceptance.

| Prospective condition | Expected behavior from code inspection | Build response |
| --- | --- | --- |
| Normalization expands a large source while other work consumes disk | Before 0.6, normalization has a per-line memory limit but no output-size or free-space guard; it can reach filesystem exhaustion mid-file. | Add an explicit output-byte cap and observed free-space reserve. Stop before the next unaffordable row; publish no completed artifact for a budget failure. |
| A comparison selects 600,000 baseline and 600,000 current records under a 1,000,000-row export cap | Each period fits the backend's per-stream limit. Previously the combined worker could write a million rows before rejecting and discarding the partial CSV. These counts are an arithmetic counterexample, not an executed dataset. | Calculate the exact selected export count from saved results before reserving capacity or launching a worker. Reject the combined 1,200,000-row cohort immediately. Keep streaming limits for later changes or errors. |
| A caller exports only request IDs from documents containing descriptions and geographic fields | Previously each Elastic page transfers and decodes the complete document despite the narrow CSV columns. | Request only the selected source fields. Keep query, sorting, exact counts and PIT pagination unchanged; the fixture path filters before projecting. |
| An annual capture crosses an upstream revision change | Existing capture freshness checks quarantine inconsistent source revisions. More CPU does not establish a consistent upstream snapshot. | Keep this safeguard. Do not fabricate complete temporal coverage or promote incomplete records into trend acceptance. |
| A huge deployment uses the single-node demo mapping | Bounded client pages do not make one shard or one node an appropriate production topology. Long-running source scans, group cardinality, heap/cache demand and map rendering still require measurement. | Keep topology and resource budgets explicit. No automatic shard/replica tuning, silently reduced population or claimed billion-row capacity. |

## New normalization controls

```text
python -m analytics311 normalize data/raw.jsonl --output data/normalized.jsonl --max-output-bytes 8589934592 --min-free-bytes 1000000000
```

Defaults are an **8 GiB normalized JSONL cap** and **1 GB observed free-space reserve**. These are execution limits, not estimates of dataset size. Raise them explicitly on suitable storage if the intended complete output needs more room. Limits accept whole bytes; no rows are sampled away to fit them.

The implementation counts actual serialized UTF-8 bytes, refreshes free-space observations before crossing each 1 MiB of additional output or a larger record, and checks again before publication. It deducts writes since the last observation. Another process can consume space between checks; this is not a disk reservation or quota. Metadata and existing raw/staging/index copies require additional storage.

On a midstream budget failure, `.part` remains for inspection and the completed JSONL/manifest is not published. Normalization does not resume that partial. Resolve storage or limits and choose a new output; existing partials are not silently reused. New output uses LF consistently on all operating systems, so a new Windows normalization may have a different byte hash than 0.5 even for equivalent records. Existing normalized artifacts and ingestion-v2 checkpoints remain valid for their original bytes.

Use one normalization writer per output. Exclusive creation protects the partial, but final data and manifest publication is not one transaction; a competing final-path writer or a later manifest-write failure remains an operational limitation.

## Export admission and projection

Record export admission uses the full saved match count, or the sum of explicitly selected groups. Comparison groups include both disjoint periods. Aggregate CSV admission counts exported aggregate rows. Top-N preview length is never substituted for the full match count. Invalid or non-exact stored counts cannot authorize a record export.

An admitted job reports `planned_rows`; progress remains `rows_written`. Admission is not completion. Existing row, byte, deadline, source-identity, cleanup and final publication guards remain in force. Source-field projection changes transferred fields only; it must not change membership or sorting.

## Verification boundary

Run only the targeted deterministic unit checks for this change and build packages from existing dependency wheels. Do not run the capacity-scenario replay, benchmark generator, process stress harness, live engine runners or bulk capture as evidence for this forecast. Build-only packages explicitly omit the normal installation/workload smoke procedure; prior 0.5 verified release artifacts remain historical and unchanged.

The integrated [focused check receipt](../examples/evidence/test-report-v0.6-focused.json) records **119 passed, zero failures/errors/skips**, with source hashes and exact test selection. Ordinary socket connections/DNS and child processes were denied by a Python audit hook during those checks; this is not OS isolation. Independent code review checked normalization accounting, export count semantics and projection order. Neither review nor these unit checks establishes production capacity.

The next physical execution still needs a suitable target and an independently qualified source. Live engine/map parity, real-million-row acceptance, held-out agent quality and physical scaling remain open.
