# Public source units

`scripts/import_public_statements.py` creates a **separate offline projection** of
the existing verified twelve-record ROR/Wikidata capture. It preserves the older
`imported/` dataset, capture files, running harness and saved trials. No network,
model, linked-media download, identity merge or new graph interpretation occurs.

This makes selected source statements individually addressable through the
existing `Workspace` interface. The working tree now implements opt-in
[catalog discovery and selective complete reads](evidence-catalog.md), with
actual-response coverage/citation guards and text-only local context admission.
Default `legacy` search still returns full records. Splitting records alone does
not bound accumulated context or memory. The integration is under validation;
no public model investigation has passed source review.

From `projects/01-sensemaking`:

```powershell
# Verify and preview sizes; no output files written.
.\.venv\Scripts\python.exe scripts/import_public_statements.py

# Create a fresh dataset; refuses any existing destination.
.\.venv\Scripts\python.exe scripts/import_public_statements.py --import-data

# Inspect through the unchanged core interface.
.\.venv\Scripts\python.exe sensemaking.py --data datasets/public-research/imported-statements graph ror:040gcmg81 --max-hops 1
.\.venv\Scripts\python.exe sensemaking.py --data datasets/public-research/imported-statements search P749 --entity wikidata:q664846
```

`--capture-dir` selects the same fixed capture plan at another location;
`--output-dir` selects a new output directory when `--import-data` is supplied.
Defaults are `datasets/public-research` and its new `imported-statements/` child.
On macOS/Linux use `.venv/bin/python`. Only Python's standard library is required.

## Record boundaries

The builder reuses the existing importer's verified capture loading and
conservative projection decisions. It emits:

| Record type | Count | Preserved content |
| --- | ---: | --- |
| Identity | 12 | Every ROR field except separately indexed relationships/external IDs (including names, status, types, locations, links and domains); Wikidata id/type/revision/modified/labels/aliases/descriptions when present. All values in each field remain intact. |
| ROR relationship | 48 | One complete original relationship object and its projection/exclusion decision. |
| External identifier group | 25 | One complete original ROR external-ID group, including every listed identifier. |
| Wikidata statement | 60 | Every statement of each selected property, including GUID, rank, snak type, qualifiers, references and ordering metadata. |
| Identity candidate | 9 | Existing crosswalk outcome and every contributing identifier claim with source lineage. These remain candidates, including rejected/missing-endpoint candidates. |

Selected Wikidata properties remain
`P31/P749/P355/P361/P527/P1365/P1366/P6782`. All 576 captured Wikidata statements
remain accounted for: 60 indexed individually, 516 retained in original raw JSON
and excluded from this index. All 48 ROR relationship decisions remain accounted
for, giving the same 624 relationship/statement decisions. Other source fields
remain in the raw capture; this is not full-property semantic indexing.

Each source unit retains source URL, raw-source SHA256, capture metadata/revision,
and exact JSON pointers paired with the complete selected values. Original raw
files and the capture manifest are copied byte for byte. Individual record text
uses deterministic JSON encoding; it is not a verbatim substring of the raw file.
Unit IDs bind the source ID, raw-source hash and pointer/address, making variants
from different captured bytes distinct. Duplicate unit IDs are refused.

The graph keeps twelve namespaced entities and five conservative ROR containment
edges, supported by the same ten source assertions. Its proof IDs now identify
the exact individual relationship records. Qualified Wikidata hierarchy statements
still do not become unqualified graph edges. Related organizations, frontier
targets and crosswalk candidates are not silently converted into containment or
equivalence. The 86-item frontier is unchanged, not a download queue.

Crosswalk records retain complete contributing source claims and reference their
individual evidence units. Separate `decision_inputs` reference captured endpoint
identity records and every inspected Wikidata P31 statement, including its exact
pointer and admissibility reasons. Candidate IDs and provenance bind these
classification sources as well as identifier-claim sources. A list-type rejection
therefore carries its Wikidata decision proof even when only ROR asserted the
identifier link. Captured candidate co-mentions enable relevance pivots,
including rejected candidates; they do not establish identity equality. Other
source units remain associated with their source-specific entity. Simplified
`assertions` arrays are deliberately empty rather than flattening qualified or
compound claims into misleading conflict triples. Dates mean source capture;
derived crosswalk records use the earliest contributing capture date, never
event time or relationship validity.

## Measured size and bounds

For this pinned capture:

| Measure | Bytes/count |
| --- | ---: |
| Exact raw sources | 595,488 bytes / 12 files |
| Individually indexed records | 154 |
| Indexed record text files | 504,819 bytes |
| Largest complete returned record | 40,213 bytes; multilingual Wikidata identity |
| Largest returned Wikidata statement | 14,278 bytes |
| Largest returned ROR relationship | 2,746 bytes |
| Largest returned crosswalk candidate | 9,374 bytes |
| Entire full-record inventory | 729,421 bytes |
| Output excluding self-describing import manifest | 1,597,415 bytes |
| Output including import manifest | 1,633,803 bytes / 173 files |

Returned sizes use UTF-8 `json.dumps(..., ensure_ascii=False)` with default
separators, excluding MCP envelopes. They are not token counts. The full inventory
is larger than the old projection because provenance is repeated across units
and complete multilingual identity fields are individually available. Smaller
selective reads are the benefit; feeding every unit to the model is not.

Actual source-specific NCI inventories through unchanged `Workspace.search`,
including explicitly associated crosswalk co-mentions:

| Scope | Records | Full inventory bytes | Largest complete record | Largest complete Wikidata statement |
| --- | ---: | ---: | ---: | ---: |
| `ror:040gcmg81` only | 14 | 44,569 | 8,294 (crosswalk) | 3,427 |
| `wikidata:q664846` only | 16 | 80,339 | 14,330 (identity) | 6,422 |
| ROR NCI graph, three hops | 39 | 117,971 | 8,294 (crosswalk) | 3,427 |

The three-hop graph contains `ror:040gcmg81`, `ror:00vkwep27`,
`ror:03v6m3209`, `ror:05bjen692` and `ror:05n6zrm60`. Its inventory has five
identity records, thirteen relationships, sixteen external-ID groups, four
crosswalks and one Wikidata statement explicitly associated through an identifier
claim. It does not automatically include every Wikidata counterpart record.
The ROR NCI identity alone is 4,518 bytes; the Wikidata NCI identity alone is
14,330 bytes. Neither is the corpus-wide 40,213-byte maximum. These inventories
and their proofs still consume significant context; fitting individual records
under 64 KiB does not establish a complete investigation fits a 16k-token model.

Before integration, the standalone `EvidenceCatalog` module was exercised against a
fresh projection, with its defaults of twenty items and 8,192 bytes per page.
Every actual returned cursor chain passed validation and its IDs exactly matched
the corresponding `Workspace` inventory:

| Scope | Catalog pages | Largest metadata item | Largest complete page | Total page bytes |
| --- | ---: | ---: | ---: | ---: |
| All 154 records | 8 | 396 | 8,023 | 59,730 |
| ROR NCI only | 1 | 371 | 5,332 | 5,332 |
| Wikidata NCI only | 1 | 371 | 6,090 | 6,090 |
| ROR NCI graph, three hops | 2 | 376 | 7,682 | 14,892 |

Catalog measurements use its canonical UTF-8 JSON without whitespace, including
the page envelope, unlike the full-record size convention above. They exclude
MCP envelopes and are not token counts. Catalog metadata contains no source
body and grants no retrieval, citation or edge-proof credit. This compatibility
check does not demonstrate model use. The later opt-in integration is described
separately in [the catalog contract](evidence-catalog.md).

Each complete returned record is capped at **64 KiB**, and total output at
**16 MiB**. A source unit exceeding its bound fails the whole projection before
publication; it is never clipped, split across an arbitrary qualifier boundary,
or silently omitted. Existing capture validation enforces its fixed plan,
source sizes/hashes, pinned revisions and capture byte limits. All source bytes
are checked again before publication. Outputs stage only fresh files and refuse
existing destinations. No overwrite mode exists.

`import-manifest.json` records builder and legacy-importer fingerprints, source
capture fingerprint, policy, counts, size measurements and every other output
file's size/SHA256. Its byte total explicitly excludes itself to avoid a recursive
measurement. The CLI's preview reports that same total; the table above separately
includes the manifest. `projection-ledger.json` retains every original decision
and exclusion while replacing indexed proof references with source-unit IDs.

## Verification and remaining work

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_public_statements.py -v
```

Ten focused offline checks cover deterministic output, byte-exact raw copies,
every selected statement/relationship/external-ID pointer and complete value,
identity fields, unchanged conservative graph/exclusions, exact edge proofs,
crosswalk identifier/decision provenance and classification-source identity changes,
actual `Workspace` resolution/search/read, size bounds,
existing-output protection, changing inputs and artifact hashes. Network calls
are forbidden in the Workspace integration check. This does not exercise model
selection of these units or prove a bounded complete agent investigation.

The opt-in catalog profile now distinguishes metadata discovery from actual full
record reads. Terminal host-recorded cursor chains establish scope inventory;
only complete returned records can satisfy citation and edge-proof requirements.
Unread metadata co-mentions cannot expand evidence scope. Local generation checks
the complete rendered text request against explicit token/output and wire-byte
bounds, failing visibly instead of clipping source units. Actual planner pages
still accumulate, and `Workspace` still loads the whole corpus into memory.

The [frozen public protocol](../evaluations/public-pilot/PROTOCOL.md) governs the
next model investigation. Public source review, actual context measurements,
repeatability, broader-scale evaluation and analyst-time claims remain pending.
The immutable source-v1 archive contains the earlier standalone components;
current opt-in integration is later working-tree development, not a change to
that checkpoint. Generated `imported-statements/` remains reproducible from raw
capture and excluded from the source-package allowlist. See [packaging](package.md).
