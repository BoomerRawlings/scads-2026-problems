# Project 4 source-claim adapter

`scripts/import_org_graph.py` imports an explicit snapshot from a Project 4
`orggraph-package` version 1 backup, offline. Default output works with Project 1
as **evidence only**. It does not import the selected organization chart, replay
reviews, infer supervision, or verify present-day employment. No sibling runtime
or model is started; no source reference is fetched.

The Project 1 core supports `contains`, `depends_on`, `supplied_by` and exact
employee-to-manager `reports_to` edges. The adapter still defaults to evidence
only, leaving `graph.json.edges` empty and writing claims to
`pending-relationships.json`. Explicit activation is described below. It never
substitutes `contains` for `reports_to`. Scripted transport conformance is not
agent-chosen sibling analysis or analytic acceptance.

## Run

From `projects/01-sensemaking`, using an existing Python 3.11+ environment:

```powershell
# Verify a source and show exact selection/omission counts. Writes nothing.
.\.venv\Scripts\python.exe scripts/import_org_graph.py `
  ../04-org-knowledge-graphs/runs/backups/meridian-72-before-10000.json `
  --snapshot snapshot_4a360c809d514c5b

# Optional fresh evidence dataset; an existing destination is refused.
.\.venv\Scripts\python.exe scripts/import_org_graph.py `
  ../04-org-knowledge-graphs/runs/backups/meridian-72-before-10000.json `
  --snapshot snapshot_4a360c809d514c5b `
  --entity-id research-00 --output-dir runs/org-graph-source-example

# Focused checks use small authored packages, not the sibling backup.
.\.venv\Scripts\python.exe -W error::ResourceWarning -m unittest tests.test_org_graph_import -v
```

The example backup is a local Project 4 artifact, not a dependency distributed
with Project 1. Substitute another canonical backup and an explicit snapshot ID.
There is no implicit latest-snapshot selection. Repeat `--entity-id` to select
source `reports_to` assertions incident to any exact original entity ID. Names
and aliases are not resolved by the importer. Omitting this option includes all
source `reports_to` assertions in the chosen snapshot; the Python API additionally
distinguishes `entity_ids=[]` (none) from `None` (all). Selection does not expand
through extra graph hops.

## Fidelity and scope

Every included assertion, endpoint identity, referenced evidence record and
referenced message is independently addressable in the Project 1 manifest. The
record body contains the complete original JSON value, an exact JSON pointer,
the raw package SHA256, corpus identity and snapshot ID/revision. The raw package
is copied byte-for-byte. No source value is truncated, rewritten as an assertion
triple, or interpreted as an instruction. Extra source fields remain intact.

Original opaque entity IDs are preserved; Project 1 node IDs namespace the corpus
and original ID. Similar names and case variants are never merged. The original
identity object accompanies each node. Ambiguous names remain ambiguous during
Workspace resolution; callers can use the distinct imported node IDs.

The canonical backup contains raw assertions. Its metadata may separately count
selected rows, but that count does not identify which raw assertions were
selected. The adapter never manufactures `selected=true`, ranks claims, applies
the Project 4 primary forest, promotes model/analyst assertions to source claims,
or treats the latest snapshot as current truth. An actually supplied `selected`
field remains literal source data only.

Raw `review_status`, primary/matrix reporting type and nullable half-open
`[valid_from, valid_to)` intervals are retained. Applicable review events are
indexed as unreplayed context when their subject belongs to the selected
endpoints. Reject/undo history is not silently reconciled. Manifest dates are
explicitly labeled snapshot creation dates, not assertion validity dates.

`projection-ledger.json` records every chosen-snapshot assertion's inclusion or
omission reasons, excluded identity/evidence/message/review IDs, other unindexed
snapshot IDs, and the original export's declared omissions. Counts describe
**indexed scope**, not deletion from the raw package. The complete backup can
contain unrelated records and history, including labels if its author supplied
them; these remain raw-only and are not returned as indexed source units.
Review that source before distributing an imported dataset.

`import-manifest.json` records the adapter hash and hashes/sizes of every other
output file. The importer rejects unsupported format/schema/projection versions,
duplicate JSON keys and IDs, missing classification/review/availability fields,
unknown referenced endpoints/evidence/messages, invalid intervals and inconsistent
synthetic declarations. Input is bounded to 8 MiB, each complete returned record
to 128 KiB, and all output to 16 MiB; overflow fails without truncation. Record
limits use sorted, indented UTF-8 JSON including the complete text body. These are
safety bounds, not a claim that every permitted record fits a model context.

## Explicit typed-edge activation

Use `--activate-reports-to` with the same source/snapshot/scope and a **new**
destination. The option still refuses a core that does not explicitly support
`reports_to`, including older frozen implementations.
The projection semantics and source-unit IDs stay the same; the dataset ID and
activation disclosure change. No historical dataset is overwritten.

An eligible activated edge points from employee to manager, retains primary or
matrix type, raw review state and dates, and cites the full assertion plus every
referenced source evidence/message unit. It means an attributed source claim,
not an independently verified or selected reporting relationship. Multiple and
competing claims are preserved. Edge activation is blocked for non-distinct or
non-person endpoints; rejected/stale raw claims; applicable subject review
history; unavailable or withdrawn evidence/messages; and assertions outside or
undated within an explicit snapshot `as_of` scope. Null `as_of` preserves
historical exploration and does not infer current applicability. Blocked claims
remain readable evidence with explicit reasons in `pending-relationships.json`.

`tests/test_org_graph_reports_to.py` exercises actual core support and real MCP
stdio traversal using a separately authored two-hop primary/matrix chain. It
checks direction, hop bounds, unchanged source units and legacy graph notes,
terminal catalog inventory, and rejection until every returned edge proof is
fully read. Earlier adapter tests also use in-memory capability changes to verify
the refusal boundary. Neither test set establishes a completed agent workflow.

## Verification

Twelve focused offline tests pass, zero skips (5.696 s). They cover exact values,
raw bytes and hashes; scoped omissions; ambiguous identities; actual Workspace
search/read; future directed primary/matrix edges and full proofs; review/undo,
withdrawal and half-open validity blockers; malformed contracts; bounded reads;
fresh-only publication and source-change refusal. The added real MCP stdio smoke
uses an authored temporary package: identity lookup, empty active graph, a complete
multi-page catalog chain, then exact source reads. Actual response events verify
catalog inventory without source citation credit; credit begins only after full
reads. MCP checks skip explicitly when its dependency is absent. No inference was
performed.

The local canonical backup SHA256 is
`4c0bf2e9d85ba133b5b323e763787b8686794f9818249d1b11ff6cbff931ecde`
(2,293,082 bytes). A read-only plan and fresh temporary import of
`snapshot_4a360c809d514c5b` agreed:

| Indexed / omitted | Count |
| --- | ---: |
| Source reporting assertions / other snapshot assertions | 5 / 69 |
| Endpoint identities / other identities | 6 / 73 |
| Source evidence / other snapshot evidence | 5 / 1 |
| Messages / other messages | 0 / 404 |
| Review records / other reviews | 0 / 2 |
| Indexed source units, including snapshot context | 17 |
| Pending unblocked source claims / active graph edges | 5 / 0 |

All 17 records loaded through the unchanged Workspace. Sorted, indented full
record JSON totaled 38,595 bytes; largest record 3,375 bytes. The temporary output
contained 25 files totaling 2,375,442 bytes, most of which is the exact raw backup.
The original backup remained unchanged. No generated dataset was retained by this
verification. A second real stdio smoke used the byte-identical backup with the
`research-00` subset: 8 actual tool calls, 2 catalog pages and 4 complete source
reads in the employee scope. It verified exact pointer values, raw review status
and both pending-claim proof records. The imported manager identity remains outside
that employee's directed graph inventory because no edge is activated.

These original checks establish adapter fidelity and evidence-only MCP access.
The explicit relation increment was verified separately in an isolated project
copy: four new conformance checks plus existing core, report, coverage, adapter
and MCP checks passed (87 distinct checks; one initially missing copied historical
fixture was supplied and that check rerun). The unchanged public and synthetic
datasets produced 88 identical graph results across depths 0, 1, 3 and 10.

An actual-backup activated smoke used `research-00` in the same earliest snapshot:
6 real MCP calls, 2 catalog pages, 1 employee-to-manager edge and 2 full source-proof
reads. Metadata inventory and a partial proof read could not satisfy completion.
The backup is a one-hop source example; the two-hop chain is a separate authored
test, not an additional claim from that backup. These scripted checks do not
establish agent-chosen analysis. Model synthesis, analytic source review and
broader portability remain pending.
