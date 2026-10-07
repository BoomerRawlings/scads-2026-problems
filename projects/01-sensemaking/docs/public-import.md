# Offline public-data import

The importer turns the [verified capture](public-capture.md) into a dataset
accepted by the existing `Workspace` and MCP interfaces. It makes no network
requests and invokes no model. This verifies an ingestion boundary, not public
analytic accuracy or the larger Wikidata case.

From `projects/01-sensemaking`:

```powershell
# Verify sources and preview counts; no files changed.
.\.venv\Scripts\python.exe scripts/import_public_data.py

# Create the default dataset. Existing destinations are always refused.
.\.venv\Scripts\python.exe scripts/import_public_data.py --import-data

# Inspect through the actual Workspace interface.
.\.venv\Scripts\python.exe sensemaking.py --data datasets/public-research/imported graph ror:01cwqze88 --max-hops 2
.\.venv\Scripts\python.exe sensemaking.py --data datasets/public-research/imported search P749 --entity wikidata:q664846
.\.venv\Scripts\python.exe sensemaking.py --data datasets/public-research/imported read claims-wikidata-Q664846

# The same dataset is accepted by the MCP server and either runner.
.\.venv\Scripts\python.exe mcp_server.py --data-dir datasets/public-research/imported
```

`--capture-dir` selects an existing capture of the same fixed 12-source plan.
`--output-dir` selects a **new** destination. A second import needs another
destination; there is no overwrite flag. Do not interpret its refusal as a
failed source verification. On macOS/Linux use `.venv/bin/python`.

## Recorded projection

| Item | Count |
| --- | ---: |
| Exact source records | 12: 8 ROR + 4 Wikidata |
| Raw source bytes | 595,488 |
| Source-specific entity nodes | 12 |
| Containment graph edges | 5 |
| Source assertions supporting those edges | 10 |
| Indexed evidence records | 24: 12 identity rows + 12 claim extracts |
| ROR relationship / Wikidata statement decisions | 624 |
| Crosswalk candidate pairs | 9 |
| Uncaptured relationship or identifier targets | 86 |
| Wikidata statements preserved but not indexed | 516 |

ROR's captured hierarchy is NIH → NCI → four captured children. Reciprocal
parent/child assertions support the same five directed edges without making
ten edges or claiming ten independent observations. Related organizations
remain source evidence; they are not containment edges.

Both captured Wikidata NIH/NCI hierarchy assertions carry qualifiers. The
prototype graph cannot express their scope faithfully, so neither becomes
an unqualified edge. Their full statements, including GUIDs, ranks, qualifiers,
references and date precision/calendar values, remain in indexed evidence.
No Wikidata graph edge is projected from this particular capture. That is
coverage discipline, not evidence that these organizations lack relationships.

## Identity and projection rules

Node IDs are namespaced: `ror:040gcmg81`, `wikidata:q664846`, etc. Source IDs and
source names remain aliases, but identifiers are never copied across providers
as identity equivalents. `National Cancer Institute` therefore resolves
ambiguously until the user or agent chooses a source-specific ID.

ROR `child` becomes `contains(source, target)`; `parent` reverses that direction.
Both endpoints must be captured and active. `related`, predecessor/successor,
missing endpoints and inactive records are excluded from the graph with reasons.

Only Wikidata `P749` and `P355` may project containment. Both endpoints must be
captured; the statement must have normal/preferred rank, a concrete item value,
and **no qualifiers**. Even an eligible edge represents a source assertion,
not verified current truth. No best-rank collapse or temporal inference occurs.
`P361`, `P527` and replacement predicates retain their own meanings in evidence.
Unknown/no-value statements are retained literally, never converted to empty
values or affirmative graph edges.

Crosswalks are candidate evidence, never merged nodes or equivalence edges.
Extract `entity_ids` include co-mentioned captured crosswalk candidates so the
harness can pivot to inspect a candidate, including a rejected candidate.
That association means relevance only; it does not assert a match or hierarchy.
The NIH ROR link to `Q6973636` is explicitly rejected as an organizational
identity match: the captured item states `P31=Q13406463` (Wikimedia list article),
and supplies no reciprocal ROR ID. NCI and NIH reciprocal identifiers remain
**candidates requiring identity review**. CERN's ROR endpoint was not captured.
Reciprocity does not prove that sources are independent.

These are deterministic documented rules, not model summaries or a general
entity-resolution system. The [source qualification](public-data.md) explains
the predicate meanings and licensing basis.

## Inspectable artifacts

- `sources/raw/`: exact original response bytes, including every unindexed
  property, language label, statement, qualifier and reference.
- `sources/capture-manifest.json`: exact acquisition manifest with source URLs,
  retrieval times, returned metadata, revisions, byte counts and hashes.
- `records.csv`: searchable identity/provenance rows. Its dates mean capture
  dates; its structured assertion means only that a source record was captured.
- `evidence/`: deterministic literal extracts. ROR identity/status/metadata,
  relationships and external IDs; Wikidata `P31/P749/P355/P361/P527/P1365/P1366/P6782`.
  Included statements retain every field. Extracts carry source provenance,
  exact JSON pointers/GUIDs, projection decisions and crosswalk candidates.
- `manifest.json`, `graph.json`, `dataset.json`: the existing dataset contract.
  Extracts deliberately have empty simplified `assertions` arrays: flattening
  multi-valued or qualified source claims would create misleading conflicts.
- `projection-ledger.json`: a decision for every ROR relationship and every
  Wikidata statement, exclusion reasons, crosswalk evidence and frontier IDs.
  Non-relationship properties are not projected; their raw source paths remain.
- `import-manifest.json`: importer/capture fingerprints, policy, counts and
  hashes for every other output file. It does not hash itself.

Raw source JSON is locally inspectable but not automatically returned through
search. Unindexed properties require opening their preserved source files or
a future explicit adapter expansion. This avoids automatically adding all
595 KB to model context. Indexed extracts still have variable size; default legacy
search has no paging. The opt-in catalog profile pages metadata and permits
selected complete reads, but cannot shorten these older large claim extracts.
Use the separate [statement projection](public-statements.md) for individually
addressable source units. Nothing is silently truncated.

Measured UTF-8 JSON sizes (`json.dumps(..., ensure_ascii=False)`, default
separators; structured payload only, excluding the MCP envelope): largest
returned record **205,849 bytes** (`claims-wikidata-Q390551`); all-record
search **342,504 bytes**; ROR NIH scoped inventory **239,580 bytes** after
candidate associations. The whole imported dataset is **1,208,227 bytes**
across **31 files**. The NIH extract is too large for the small contexts used by the local pilots
(12,288-token baseline and 16,384-token candidates). The implemented opt-in
catalog and statement projection address discovery and read granularity; their
public analytic qualification remains pending. No model was run on this import.

NCI plus its four reached ROR children returns **11 evidence records / 70,470
bytes**, including the associated Wikidata NCI extract. Individually, NCI's ROR
extract is **8,201 file bytes / 10,345 returned-record bytes**; Wikidata NCI is
**26,787 / 30,736 bytes**. This smaller candidate is still not an accepted local
agent case: tools, prompt, selected evidence and generated report all compete
for context. Public agent acceptance remains pending.

## Verification and limits

Eleven focused offline tests pass: byte-exact source preservation and deterministic
reimports; real Workspace identity/search/traversal; complete statement accounting;
false crosswalk/relationship prevention; qualifiers/ranks/unknown values; corrupted
hash and pinned-revision refusal; concurrent manifest-change rejection;
foreign/existing output protection; artifact
hashes and indexing boundaries. They use the saved capture, not live responses.
The final test starts a real MCP stdio server on the imported data, checks
ambiguous identity, graph traversal, scoped claim search, rejected-crosswalk
reading and explicit missing media. With MCP absent that test skips; a skip
does not establish transport compatibility.
It also exercises the existing connected-scope report guard: a separately
read Wiki identity is initially rejected as outside scope, then becomes
eligible after an actual ROR claim record supplies its candidate association.
The graph still contains no cross-provider equivalence or containment edge.

Before any output, the importer checks the fixed capture plan, exact URLs/IDs,
source hashes and sizes, pinned Wikidata revisions and manifest totals. Inputs
remain unchanged. Capture bounds remain 2 MiB/source and 8 MiB total; generated
output is capped at 16 MiB. It stages only fresh files and refuses any existing
destination, including empty directories. There is no incremental merge.

The 86-item frontier is a recorded boundary, not a download queue or omitted
ground truth. It covers direct relationship and crosswalk targets only, not
every entity mentioned in qualifiers/references. Those remain in raw claims.
The per-entity revisions do not form an atomic database snapshot; registry edit
times are not relationship validity dates. Linked images/video were neither
downloaded nor licensed by this import. No natural-media benchmark, public
model evaluation, larger-scale benchmark, or analyst time-saving claim follows
from these importer checks.

Use `entities`, `graph`, `search` and `read` for this corpus. The existing
deterministic `Workspace.investigate()` convenience packet still contains
hardcoded synthetic-fixture limitations; its prose is not valid public-corpus
documentation. That helper is absent from the MCP agent tool catalog. The
importer does not modify it.

## Opt-in retrieval boundary

The separate [statement projection](public-statements.md) and
[bounded metadata catalog](evidence-catalog.md) passed focused component checks
and independent review. Current working-tree MCP and runner integration is
implemented behind `--retrieval-profile catalog`, under validation. Default legacy
behavior and historical artifacts remain unchanged.

Catalog IDs permit selective source reads without earning citation or graph-proof
credit. Actual complete source responses grant that credit; completed unfiltered
scope inventories require host-recorded snapshot-bound terminal cursor chains.
Unread catalog associations cannot establish a connected evidence pivot.
Statement units retain full qualifiers/references, revision, JSON pointer and
raw-source hash; crosswalk candidates remain distinct from confirmed identity.

The local catalog profile admits text-only generation requests through actual
template/tokenization endpoints with explicit token/output and serialized-byte
bounds. Overflow fails rather than silently discarding evidence. This limits
model requests, not storage: `Workspace` still loads/scans the whole corpus,
and accumulated planner pages can still exhaust the context budget.

The [source-specific NCI question and review protocol](../evaluations/public-pilot/PROTOCOL.md)
are frozen. Scripted local HTTP/MCP integration checks exercise transport,
coverage and citation boundaries without a model. The first public analytic
qualification still needs an actual model investigation and source review of
ROR containment and qualified Wikidata comparisons. Component/transport checks
alone do not establish that result. The accepted source-v1 archive remains the
earlier v12 synthetic checkpoint, not this later working tree.
