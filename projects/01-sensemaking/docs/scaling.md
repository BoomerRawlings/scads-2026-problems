# Scaling: current limits and next implementation stages

The [agreed goal](decisions.md) is to remove a fixed dataset ceiling and measure
practical limits. RAM, disk, context, latency and budgets remain finite. This is
an implementation plan grounded in current code, not a scalability result or a
commitment to a distributed system before one is needed.

## What exists, and what still grows

| Component | Present ceiling or repeated work |
| --- | --- |
| `sensemaking.Workspace.__init__` | Loads the entire graph, all manifest source texts and CSV records; SQLite uses `:memory:`. The evidence dictionary retains full bodies. |
| `Workspace.search`, `entities`, `graph` | Text search scans candidate bodies; identity lookup scans nodes; BFS scans the whole edge list for each expanded node. Hop bounds do not bound a high-degree result. |
| `evidence_catalog.EvidenceCatalog` | Owns another complete Workspace. Every page constructs the whole matching metadata list and reconstructs preceding page boundaries. Only the returned page is byte/item bounded. |
| `EvidenceCatalog._check_snapshot` | Streams hashes of all declared source/media bytes repeatedly. MCP brackets catalog-profile calls with snapshot checks; this protects consistency but adds corpus-wide I/O. |
| `mcp_server.create_server`, both runners | Catalog server retains two Workspaces; each runner also builds a whole-corpus evidence map. Coverage validation constructs another catalog and replays actual page chains. These are separate copies/loads, not a shared disk index. |
| `local_agent.run` | Planner messages, actual result events and source-result messages accumulate. Exact-repeat references avoid duplicate feedback but do not bound unique evidence or the retained audit. |
| `compact_synthesis_messages` | Deduplicates identical complete records and envelopes; keeps distinct versions and their full text. Final synthesis still grows with all retrieved material. |
| `local_context.admit_text_context` | Serializes, templates and tokenizes the full text request before generation. It rejects overflow; it does not shrink context or make storage scalable. |
| Current importers | Read complete source JSON/build output maps in memory. Public capture is a fixed 12-record selection; statement records are capped at 64 KiB and projected output at 16 MiB. The sibling adapter caps input at 8 MiB, full records at 128 KiB and output at 16 MiB. These bounds fail visibly, not truncate. |

These costs also appear in `run_agent.collect_coverage` and
`read_dataset_metadata`: actual-result verification and source hashing are sound
boundaries, but repeatedly rebuilding them is not an incremental index.

There is a measured context failure, not a measured storage capacity result:
[public NCI01](../evaluations/public-pilot/public-nci-01/REVIEW.md) reached 16,823
prompt tokens before decision ten; 512 generation tokens plus 128 headroom exceeded
its 16,384-token slot. The request was refused without truncation or a report.
[v14](../evaluations/public-pilot/implementation-v14/README.md) changes model and
capacity together: 49,152 tokens and 262,144 request bytes.
[NCI02](../evaluations/public-pilot/public-nci-02/REVIEW.md) admitted its report
request within that window, then reached its request deadline without a report.
Its actual reads also omitted the Wikidata/crosswalk portion of the question.
Larger limits alone do not remove the accumulation problem or establish better analysis.

## 1. Disk-backed retrieval with immutable indexed snapshots

First replace the backend behind the existing tool contracts. Use a persistent
SQLite index for entities/aliases, directed adjacency, evidence associations and
searchable text/metadata; keep exact source bodies in an indexed table or local
hash-addressed files. Start with one machine and one database, not new services.
Build into a fresh location, verify all source units, then publish a completed
read-only snapshot. A run pins that snapshot; changes create a new one.

This requires a streaming/batched import boundary, not merely changing SQLite's
connection string. Replace corpus-wide Python dictionaries, scans and repeated
hash passes with indexed lookups and bounded caches. Hash source bytes during
ingest and verify fetched bodies against the pinned manifest. Do not substitute
mtime for content identity or weaken mutation checks on still-mutable files.
Crash/incomplete builds must never become selectable snapshots.

Catalog cursors must remain bound to snapshot, query, normalized scope, ordering
and limits. Use stable indexed continuation positions; retain verifiable actual
first-to-terminal response chains. Introduce explicit traversal pagination or a
declared partial-result boundary for high-degree graphs before claiming bounded
graph retrieval. An unfinished chain never establishes complete inventory.

Acceptance: parity with existing source bytes, graph direction, search behavior,
identity ambiguity and citation/proof tests; crash/restart and stale-snapshot
tests; bounded process memory across increasing input sizes; measured import,
index size, cold/warm query and terminal-inventory costs. If indexed search changes
matching/ranking, version and test that contract rather than silently changing it.

## 2. Bounded planner memory plus an exact run evidence store

Store every successful full source result/version and actual call receipt in a
private run store. Keep bounded active planner context: current question, chosen
scope, open coverage tasks, recent decisions and source handles. Evicting a body
from the prompt must not erase its exact bytes, provenance or retrieval history.
Expose explicit re-reading of previously retrieved evidence; the current
no-repeat source policy would need a disclosed revision for evicted bodies.

Compact planner notes are navigation aids, never new evidence. Metadata discovery
still gives no citation credit. A summary cannot establish a previously unseen
source, proof or independent corroboration. Before a finding is synthesized or
checked, reload its actual premises within budget. Keep run-store lifecycle and
export rules separate from public artifacts: no private reasoning, raw sessions
or unreviewed source dumps in the showcase.

Acceptance: long multi-pivot replay with bounded prompt and host memory; exact
rehydration and version hashes; unchanged actual inventory/proof accounting;
failure/resume tests; explicit irrecoverable-source errors. Measure re-read I/O,
tokens, eviction frequency, latency and analyst-visible omissions. A run that
cannot finish within budget must abstain rather than silently forget evidence.

## 3. Source-backed chunk synthesis

Only after exact retrieval and rehydration work, add bounded synthesis batches.
Prefer complete semantic units already supplied by the statement adapter. A large
identity/document needs lossless addressable fragments with source hash, JSON
pointer or byte range and declared coverage; preserve qualifiers, references,
negation and neighboring context. No arbitrary first-N excerpt may masquerade as
a complete record. Unit-size refusal remains until this contract exists.

Each intermediate claim must cite exact source units and identify its scope and
unresolved alternatives. Intermediate prose is model output, not corroborating
evidence. Final synthesis must reconcile cross-batch conflicts and relationship
paths against reloaded premises; splitting work cannot grant unread proof credit.
Track covered, unread and deferred source units explicitly. If reconciliation
does not fit, narrow the stated result or return insufficient evidence.

Acceptance: frozen cases with conflicts/qualifiers split across batches, shared
origins, competing versions and multi-hop proofs; original drafts and source
lineage retained; separate semantic review. Compare factual support, coverage,
abstention, tokens and runtime with the unbatched baseline. Chunking is not an
automatic truth check and is not implemented by today's compact synthesis.

## 4. Sharded retrieval only after single-host measurements justify it

If the indexed local backend hits measured disk, memory or throughput limits,
partition immutable source snapshots by declared corpus/namespace behind the
same retrieval interface. Keep globally unambiguous IDs, explicit cross-shard
links and per-shard revision bindings. Do not merge identities by name.

A coordinator must account for each requested shard's actual responses, failed
or missing shards and terminal inventory receipts. Partial availability cannot
be called globally complete; independent shard snapshots do not imply an atomic
world snapshot. Begin with local partitions; remote transport, authentication and
concurrent writers are separate requirements, not current capabilities.

Acceptance: equivalent results to one indexed snapshot, cross-shard proof reads,
missing/stale shard failures, restart behavior and bounded fan-out. Measure end-to-
end costs before adding infrastructure; a service split alone saves no source or
model work.

## Measurement and publication

Use frozen tasks at increasing record/byte counts, graph degree/depth, record
size and source-version multiplicity. Synthetic expansions measure mechanics;
qualified public cases and held-out questions test different analytic limits.
Record hardware/runtime/model, dataset/index hashes, disk bytes, runner/MCP/model
memory separately, cold/warm latency, tokens and admission failures, actual source
reads/proof coverage, resumability and reviewed answer quality. Shared-host peaks
are observations, not minimum RAM requirements. Human time-saving claims require
a measured human baseline. Publish limits and failures with successes; none of
the proposed stages is a completed scaling milestone today.
