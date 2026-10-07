# Bounded evidence catalog — opt-in integration

`evidence_catalog.py` supplies metadata pages through the existing read-only
`Workspace` interface. The working tree now integrates it with MCP, both runners,
report guards and saved-run provenance through **`--retrieval-profile catalog`**.
The default `legacy` profile retains full-record search. This opt-in implementation
is under validation; no public model investigation has passed source review.
The catalog module itself requires only Python's standard library and performs
no network or model calls. See [package boundaries](package.md) for the distinction
between current sources and the immutable source-v1 checkpoint, which contains
the earlier standalone catalog. The statement builder can reproduce its dataset
from the packaged verified raw capture; generated datasets remain excluded.

Each item contains exactly `id`, `title`, `kind`, `date`, `entity_ids`, `source`,
`text_sha256` and `text_bytes`. Strings and entity associations are copied exactly;
the digest and byte count cover the complete indexed text encoded as UTF-8.
Dates and titles retain their supplied meanings. No text body, assertion object,
media content or additional manifest field is returned. Supplied metadata may
itself contain sensitive or misleading text: this is an allowlist, not redaction.

Every page marks `metadata_only: true` and `evidence_content_returned: false`.
Catalog IDs **do not establish retrieved/citable evidence or graph-edge proof**.
A later actual source-record read must return the full selected record before
existing citation/proof guards can credit it. Media inspection remains separate.
Keyword matching examines indexed title/text internally; finding a match does
not return the matched source content.

## Interface and bounds

```python
from evidence_catalog import EvidenceCatalog, validate_catalog_chain

with EvidenceCatalog(data_dir) as catalog:
    calls, cursor = [], None
    while True:
        response = catalog.page(entity_ids=[entity_id], cursor=cursor)
        # The host records actual returned responses, not an agent's recollection.
        calls.append({"cursor": cursor, "response": response})
        cursor = response["next_cursor"]
        if cursor is None:
            break
    coverage = validate_catalog_chain(catalog, calls, entity_ids=[entity_id])
```

`page(query="", entity_ids=None, *, max_items=20, max_bytes=8192, cursor=None)`
returns at most 20 items and 8,192 bytes by default. Allowed item limits are 1–100;
byte limits are 1,024–65,536. `catalog_json_bytes(response)` is the exact bounded
representation: sorted JSON keys, compact separators, unescaped Unicode, UTF-8,
no newline. The bound includes every catalog envelope field, digest and cursor.
MCP's outer envelope, duplicate text/structured representations, escaping and
transport framing are outside this canonical page measurement. The local runner
separately bounds the actual serialized generation request containing accumulated
messages; a page-byte limit alone does not bound that request.

Items sort by exact evidence ID. Pages never shorten an item or silently omit the
tail. `total_items` names the full matching count; nonterminal pages supply the
next cursor. An item that cannot fit fails with `MetadataItemTooLarge`; raising
the explicitly bounded page limit or changing source metadata is a caller decision.
The whole text may be much larger than a page because only its hash/length are
returned. An empty result returns one terminal empty page, which still must be
recorded for complete-result credit.

Scope is an exact set of known entity IDs, with duplicate IDs/order normalized.
`None` selects all entities; `[]` selects none. There is no automatic graph
expansion or supplier proof insertion. The query string is bound exactly, even
when different strings would match the same records. Matching otherwise preserves
`Workspace.search` semantics: all case-insensitive whitespace-separated tokens
must appear in the combined title/text.

## Snapshots, cursors and actual-response chains

The snapshot hashes `graph.json`, `records.csv`, `manifest.json`, optional
`dataset.json`, all manifest text sources and declared media. Missing optional
files/media have an explicit null entry, so later appearance also invalidates the
snapshot. Required missing sources fail. Paths must resolve inside the dataset;
only relative path/hash mappings enter the fingerprint. Identical datasets in
different directories produce identical pages/cursors. Hash checks bracket
Workspace loading and each returned page. Changed, removed or unreadable inputs
require a fresh catalog. This detects observed changes; it is not an atomic
filesystem snapshot or a defense against changes deliberately made and restored
between checks. Immutable captured data remains the appropriate deployment input.

At construction, the IDs exposed by unfiltered `Workspace.search` must exactly
match CSV and manifest IDs. Otherwise the catalog fails explicitly. This catches
an existing Workspace edge case: a manifest entry with `kind="record"` can be
read by ID but is omitted from public search, which reserves that kind for CSV
records. Such an omission must not silently earn complete-inventory credit.

A cursor binds policy, dataset fingerprint, exact query, normalized entity scope,
both bounds, page index, next item position and the preceding page hash. It is
deterministic and contains no secret. The page hash covers the response body before
the `page_sha256` and `next_cursor` fields, avoiding a circular hash. A resumed
request reconstructs preceding deterministic boundaries and refuses invented
offsets, changed options and altered predecessor hashes. A valid later cursor can
retrieve that page; it does not establish that earlier pages were actually read.

`validate_catalog_chain` separately checks **host-recorded actual** request/response
pairs against their bound snapshot. It requires the first request cursor to be
null, every exact prior continuation, byte-equivalent canonical response content,
and a terminal response. Missing/reordered/replayed pages, shortened chains,
altered items/envelopes, changed scope/query/options and stale inputs fail.
An agent-provided list of IDs or cursors must never replace the host's call audit.
Hashes and deterministic cursors are consistency checks, not authentication or
proof that a network/tool invocation occurred.

Successful validation reports `result_set_complete`, counts and the request
binding. `scope_inventory_complete` is true only for an unfiltered query
(empty/whitespace); a completed keyword search does not inventory its entire
entity scope. Neither flag grants evidence retrieval/citation/proof credit.
Even a complete unfiltered catalog describes only this supplied bounded scope,
not an investigation's semantic completeness or all real-world information.

## Implemented runner boundaries

Start the MCP server with `--retrieval-profile catalog` to expose
`catalog_evidence` in place of `search_evidence`. Both `run_agent.py` and
`local_agent.py` accept the same opt-in profile and pass it to their MCP server.
The local profile additionally requires `--grounded-media --compact-synthesis`;
it is currently text-only and refuses pixel reads. These flags retain actual-run
provenance construction and compact final synthesis; they do not establish that
media was inspected. See [local runtime](local-runtime.md) for model setup.

Successful catalog cards and returned graph-proof IDs make source IDs discoverable.
Only actual successful complete `read_evidence` envelopes grant source retrieval
credit. Nested identifiers, catalog metadata and media availability do not.
Graph-edge proofs must be read in full. Connected evidence scope can expand through
actual traversals or associations in returned full records; an unread catalog
co-mention cannot expand it or establish identity equivalence.

Before accepting a complete report, guards require a traversal rooted at the
resolved target, complete unfiltered terminal catalog chains for the reached
graph scope, and all returned edge proofs as complete records. The host validates
actual page responses, not model-supplied claims of coverage. Saved coverage
receipts retain request bindings, page/call lineage and incomplete-chain gaps.
Citation checks bind exact returned record versions and connected scope. These
requirements establish a minimum retrieval workflow, not sufficient investigation
or the truth of a report's conclusions. Clarification remains distinct from a
completed analytic report.

The local catalog planner now receives recovery guidance based on the actual
missing work: unfinished inventory requests a terminal cursor chain; missing
edge proofs request full `read_evidence` records. A proof-only deficit does not
instruct the planner to repeat completed inventories. Its catalog-only planning
reminder also distinguishes each question part's source support from structural
coverage, preserving unread-source and ambiguous-association limits. Metadata
records `catalog_planning_guidance_policy=question-parts-and-actual-deficits-v1`.
These are guidance changes, not a new semantic validator or demonstrated model
improvement; schemas, citation/proof guards and the legacy profile are unchanged.
Historical NCI runs predate this change and remain preserved as failures.

The local planner sees each actual metadata page and chosen complete record.
Compact final synthesis retains exact retrieved record variants, graph/identity
results and errors; catalog content is represented by audited discovery/coverage
facts, not promoted into evidence bodies. Discovered-but-unread counts remain
explicit. Saved ledgers include retrieved evidence, not the entire catalog.

For local catalog runs, `local_context.py` sends the complete generation payload
to the same loopback server's `/apply-template`, then calls `/tokenize` with
`parse_special=true`, `add_special=false`. It admits only text requests satisfying
`prompt_tokens + max_tokens + 128 <= --context-token-limit` (default 16,384).
`--catalog-context-bytes` separately bounds cumulative serialized request bytes
(default 131,072). Template/token requests and responses, shared deadlines and
numeric results are checked; no evidence is silently dropped or truncated to fit.
Non-text content, missing counts, malformed responses and overflows fail visibly.
The original generation request remains unchanged. Actual reported prompt usage
is checked after generation and compared with preflight counts. This is a
conservative admission check, not proof of exact model fit or resource capacity.
Metadata stores hashes, counts, limits and outcomes, never rendered prompts or
token arrays. These local-server checks do not apply to the optional Codex runner.

## Remaining limits

The catalog bounds individual metadata pages; local admission rejects oversized
cumulative model requests. Neither bounds **storage, total work or total transfer**.
Existing `Workspace` still loads
the entire corpus and builds an in-memory SQLite database. Searches scan loaded
text, snapshot checks hash complete input files, and cursor verification replays
prior metadata page construction. These costs are unsuitable as an infinite-scale
claim. A future indexed store and immutable snapshot service need their own design
and measured limits. Complete source reads can still be large, and retained
planner pages accumulate until admission refuses the request. There is no durable
out-of-context planner memory or automatic continuation after overflow.

The [NCI01 context diagnosis](../evaluations/public-pilot/context-cost-probe-nci01.json)
reconstructs all ten original request hashes without model calls. The blocked
prompt reached 16,823 tokens; successive-request increases following five full
reads and the first catalog page totaled 12,701 tokens (75.5%). These deltas
include actions, feedback and schema changes, not isolated source-token costs.
Outer JSON compaction saved only 812 request bytes in an offline measurement;
lossless catalog tables and removing repeated tool schemas offer further bounded
byte savings, not measured token savings. Unique evidence still accumulates.
Sustained growth requires bounded planner memory backed by exact stored source
versions; larger final analyses would also need source-backed chunk synthesis
and cross-chunk qualification review. No such changes or public acceptance are
established by this known development-case diagnosis.

Offline component checks and scripted local HTTP/MCP tests exercise implementation
boundaries. The two source-reviewed public runs both failed before producing a
report: NCI01 exceeded context; NCI02 reached its report deadline and had not read
the Wikidata/crosswalk evidence. Their recorded failures are inspectable in the
showcase. Public analytic acceptance, repeatability and measured scale remain open
under the [frozen public protocol](../evaluations/public-pilot/PROTOCOL.md).
Historical synthetic runs and the source-v1 checkpoint predate this integration.

Focused implementation checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_evidence_catalog.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_local_context.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_local_catalog.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_catalog_planning_guidance.py -v
```

These tests verify bounded serialization and consistency safeguards, not analytic
accuracy, source truth, external-data scale or model behavior.
