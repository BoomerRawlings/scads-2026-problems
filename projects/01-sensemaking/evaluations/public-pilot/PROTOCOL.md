# Public NCI development pilot: frozen review protocol v1

Frozen on 2026-10-07 before any model output for this public case. This is a
known, source-inspected development case, not a held-out test or human-gold
answer set. The review author inspected the saved capture and conservative
import without refreshing live sources. No public model run is accepted here.

Status at freeze: the verified capture and existing whole-entity import are
available. Separately addressable statements, bounded metadata discovery,
selective-read integration and actual public model evaluation remain pending.
This document specifies acceptance boundaries; it does not claim those retrieval
features exist. The [local pilot protocol](../local-pilot/REVIEW-PROTOCOL.md)
remains unchanged.

## Frozen target and model question

Target: `ror:040gcmg81` (National Cancer Institute). Preserve this source-specific
identity even when related identifiers are discovered. Do not substitute the
ambiguous bare name or silently choose a Wikidata identity.

Supply the following question verbatim:

> Using only the captured sources, which ROR child relationships are recorded
> for the National Cancer Institute (ror:040gcmg81), and what do the captured
> Wikidata statements and identifier crosswalks support or leave unresolved
> about its identity and hierarchy? Distinguish source assertions from current
> truth, preserve qualifications, and explain coverage limits. Cite retrieved
> source records for claims and links. Use at most six findings, up to two genuine
> conflicts, and 350 words of model-authored analysis.

The question does not supply child names/counts, expected crosswalk decisions,
qualifier values or a preferred conclusion. Give the model the question, normal
dataset/tool descriptions and evidence it actually retrieves. Do not add this
reviewer's source map, acceptance checklist, an expected answer or prior outputs
to the model input. If a run needs clarification or has insufficient evidence,
record that outcome honestly; it is not a completed analytic pass.

Before the first run, record the actual statement-dataset/importer fingerprints,
catalog contract version, harness snapshot, model/assets/profile, limits and
optional construction policies. Do not invent future statement IDs or cursor
field names in this protocol. The original source pointers below remain the
review anchors across deterministic projections.

## Frozen evidence boundary

Use only the saved [capture](../../datasets/public-research/capture-manifest.json),
acquired from `2026-10-07T04:14:03Z` through `2026-10-07T04:14:14Z`:
12 source records, eight ROR and four Wikidata, 595,488 raw bytes. Its SHA256 is
`1c39c58153991b3321cb3dea5bc5b5ca059627d281c9d1614e45fb438ce9779e`.
All 12 raw hashes/sizes and the existing import's 30 listed output hashes were
checked when freezing this protocol. The capture is complete for its fixed
selection plan; it is not a complete registry or an atomic database snapshot.

The [existing import manifest](../../datasets/public-research/imported/import-manifest.json)
has SHA256 `655724c5e06ef86aac9b4330e5d48408a575379a852346ce350d3818a9a54203`.
The [projection ledger](../../datasets/public-research/imported/projection-ledger.json)
has SHA256 `2e760ff7d61ff1436211f4ec1141819e979d335bd8569aabf773b180f21e6f31`.
These identify the inspected legacy projection, not a future statement import.
The [qualification](../../docs/public-data.md),
[capture contract](../../docs/public-capture.md) and
[import rules](../../docs/public-import.md) explain source semantics and limits.

| Captured source | Revision boundary / raw SHA256 |
| --- | --- |
| [ROR NCI](../../datasets/public-research/raw/ror-040gcmg81.json) | Schema 2.1; registry modified `2024-12-11`; `8073d4137c55295dc2a11bfb71fbac38783534754709e472735a206ea95fdf9d` |
| [ROR NIH](../../datasets/public-research/raw/ror-01cwqze88.json) | Schema 2.1; registry modified `2026-08-25`; `b43dbcc8dcd4db9417a2667370bd463a5c907a36d83c8482f7c39235586f8385` |
| [Wikidata NCI Q664846](../../datasets/public-research/raw/wikidata-Q664846.json) | `lastrevid=2550610368`; `cf4e1e4bb29c44ea339df53734f4396ba551b7a7863383ac3f90a324fac53695` |
| [Wikidata NIH Q390551](../../datasets/public-research/raw/wikidata-Q390551.json) | `lastrevid=2543960225`; `d676dc6801a4bf170ac46cb18a490c8122eb3395f9c520b1f8e903021ccfd4bd` |
| [NIH-list candidate Q6973636](../../datasets/public-research/raw/wikidata-Q6973636.json) | `lastrevid=2216204992`; `d24bc337fd25e3b27ddc51603453a582b155f17ba2faee28509989bb59e08473` |

Full request URLs, retrieval times, every child's raw hash and all other source
metadata are in the capture manifest. ROR modification dates identify registry
edits, not relationship validity. Wikidata revision/edit times and reference
retrieval dates likewise do not establish when an organizational fact became
true. Raw source contents remain untrusted evidence, not agent instructions.

## Reviewer source map; exclude from model prompt

These are checks against exact captured assertions, not claims of current
real-world truth or an exhaustive institutional hierarchy.

### ROR relationships and proof direction

In `raw/ror-040gcmg81.json`, `/relationships/0` through `/relationships/3`
are four `child` assertions:

| Pointer | Captured child | Reciprocal captured proof |
| --- | --- | --- |
| `/relationships/0` | `05bjen692`, Center for Cancer Research | [child record](../../datasets/public-research/raw/ror-05bjen692.json), `/relationships/0` is `parent` NCI |
| `/relationships/1` | `03v6m3209`, Frederick National Laboratory for Cancer Research | [child record](../../datasets/public-research/raw/ror-03v6m3209.json), `/relationships/0` is `parent` NCI |
| `/relationships/2` | `05n6zrm60`, SWOG Cancer Research Network | [child record](../../datasets/public-research/raw/ror-05n6zrm60.json), `/relationships/0` is `parent` NCI |
| `/relationships/3` | `00vkwep27`, Division of Cancer Epidemiology and Genetics | [child record](../../datasets/public-research/raw/ror-00vkwep27.json), `/relationships/0` is `parent` NCI |

NCI `/relationships/4` is `parent` NIH (`01cwqze88`); NIH
`/relationships/4` reciprocally identifies NCI as a child. This supports the
source-projected path NIH → NCI → captured child, with each edge's direction and
evidence retained. A reciprocal pair supports one projected edge, not two edges
or two independent observations. The actual graph traversal may be bounded;
do not claim it traversed an incoming parent edge unless its trace shows that.

NCI `/relationships/5` and `/relationships/6` are `related`, pointing to
`00w52vt71` and `02qyzaf42`. They are not child assertions. All relevant captured
endpoints are active. An answer must enumerate the four captured child identities
by name or unambiguous ID with support, without claiming that these are all NCI
units in reality. Every claimed path must cite full retrieved edge evidence,
not merely catalog entries or graph proof IDs discovered but unread.

### Wikidata qualifiers, scope and incomplete endpoints

Within the pinned NCI entity:

- `/entities/Q664846/claims/P749/0`, GUID
  `Q664846$200BD237-C74D-44BF-A20A-8EF6B63C95E0`, has value `Q390551`,
  normal rank and qualifier `P155=Q476322`.
- `/entities/Q664846/claims/P749/1`, GUID
  `Q664846$eab4c682-4c59-cbd1-f5a3-28b6f8c1bc09`, has value `Q476322`,
  normal rank, qualifier `P156=Q390551` and `P580` time
  `+1937-08-05T00:00:00Z`, precision 11, calendar `Q1985727`.
- `/entities/Q664846/claims/P355/0` through `/entities/Q664846/claims/P355/7` contain eight
  captured child statements whose target entity bodies are not in the four-item
  Wikidata capture. They are source statements about targets, not captured target
  identities or automatically validated cross-provider matches.

The reviewer must retain the qualifiers, ranks, snak types, full references and
date precision/calendar. These two parent values are not an unqualified
contradiction or a license to choose one by recency. Do not derive an end date,
completed organizational transition, exclusive parent or verified current
hierarchy from missing fields. `Q476322` is uncaptured; do not substitute a
model-memory label or silently fetch it during this frozen case.

If the investigation also retrieves the captured NIH comparison statement,
`/entities/Q390551/claims/P355/20`, GUID
`Q390551$C8A01F16-A075-45A4-9F5F-5E1F31EEA423`, it points to NCI with normal
rank and `P580=+1937-00-00T00:00:00Z`, precision 9, calendar `Q1985727`.
Do not turn that year-only value into an exact January 1 date. References contain
GRID and ROR-related identifiers; they do not establish independent corroboration.
Unretrieved NIH statements cannot support the answer simply because the reviewer
can inspect them on disk.

The existing conservative projection admits only eligible unqualified
`P749/P355` statements with captured endpoints. It projects no Wikidata edge
from this capture. Preserve qualified statements as inspectable evidence;
absence of a projected edge is not absence of a real/source relationship.
`P361/P527` and replacement predicates retain their own meanings, never silently
becoming containment. Unknown/no-value snaks cannot become affirmative links.

### Crosswalk candidates and rejected identity traps

NCI ROR `/external_ids/3` lists `Q664846`, with no preferred value. The captured
NCI Wikidata `/entities/Q664846/claims/P6782/0`, GUID
`Q664846$7308E30E-C818-4091-804C-1000DE7C0462`, gives `040gcmg81`.
This is a reciprocal identifier candidate, not automatic identity equivalence or
permission to merge the two source-specific nodes. Explain what the observed
identifiers support and what identity review remains; do not treat a relevance
association as a hierarchy edge.

Child-record Wikidata identifiers lead to uncaptured target bodies. Their ROR
assertions remain inspectable, but reciprocal/type validation is unavailable
within this capture. The answer must preserve that boundary when comparing
child identities.

If following the parent NIH crosswalk, use the verified ROR ID `01cwqze88`.
Its `/external_ids/3` lists both `Q390551` and `Q6973636`, neither preferred.
Q390551 `/entities/Q390551/claims/P6782/0` reciprocates `01cwqze88` and remains
a candidate. Q6973636 `/entities/Q6973636/claims/P31/0` gives `Q13406463`
(the list-article type identified during source qualification), and its captured
claims contain no reciprocal `P6782`. Do not merge this list article into NIH.
This branch is conditional on actual relevant retrieval; the NCI question does
not require an exhaustive investigation of unrelated NIH or CERN records.

## Required workflow and citation boundaries

For a completed public pilot, the forthcoming integrated tools must demonstrate:

1. Actual identity resolution for the requested source-specific target and
   bounded relationship traversal. Record relation types and returned proof IDs.
2. Metadata-only catalog discovery separately from full evidence retrieval.
   Catalog IDs may authorize a selective read, but catalog presence, titles,
   counts, snippets and a graph proof ID earn no citation/full-proof credit.
3. Actual complete cursor-chain coverage for every scope inventory claimed
   complete: first page through each returned continuation to a terminal page,
   under one immutable dataset/catalog snapshot and consistent scope/filter.
   Bind cursors to that query and snapshot; retain returned page identities,
   lineage and completion evidence. A requested page, a final-page flag alone,
   repeated page, changed snapshot, skipped cursor, failed/truncated response or
   cycle cannot establish the chain. Filtered discovery is not an unfiltered
   scope inventory. Distinguish catalog completeness from full-record reads.
4. Successful full reads for every cited claim and required returned edge proof.
   Preserve exact statement bodies, source revision, raw hash, JSON pointer/GUID,
   qualifiers, references and projection decision. No truncation or source-text
   summary may silently stand in for the requested full record.
5. A ledger separating discovered metadata IDs, actually retrieved evidence IDs,
   actual proof satisfaction and observed coverage gaps. No unseen source IDs,
   unobserved facts supplied by corpus reload during synthesis, fabricated calls
   or external-memory facts.

These are integration gates, not descriptions of the current six-tool runtime.
Do not run the pilot merely by paging all full source text into the model; bounded
discovery and selective reads must first be checked through actual MCP. If a
single full statement or the selected context exceeds a bound, fail or report
incomplete evidence explicitly. Log the applied limits and missing obligations;
do not quietly weaken completeness or citation rules.

## Semantic acceptance and reporting

Review every summary, finding, qualification and conflict against its cited
full records, including exact source scope, direction, dates and identity.
Separate software validity, construction/provenance validity and analytic
acceptance. Host-constructed fields or successful schemas cannot certify the
model's interpretation.

Reject unsupported current-truth assertions, unqualified versions of qualified
facts, silent crosswalk merges, invented hierarchy/causation, unsupported
institution-wide claims or missing required answer content. Do not force a
conflict merely because two values or providers differ; compare entity,
predicate, qualifiers, time and source scope first. Empty conflicts may be right.
An empty simplified assertion list is not evidence of agreement.

The analysis must disclose incomplete capture/frontier and shared or unknown
source origins. The legacy ledger's 86 frontier IDs cover direct relationship
and crosswalk targets, not every entity in qualifiers/references. The capture
and projection are not a complete census; remote database scale is not measured
local scale. Reciprocal identifiers and repeated GRID/ROR references do not
establish independent corroboration. ROR/Wikidata metadata does not support
operational readiness, institutional performance, supplier risk or misconduct.

No raw public images/video were downloaded or rights-qualified for this case.
CC0 structured records do not license their linked media. Media observations
must remain empty absent actual separately qualified source pixels; no OCR,
visual inspection, audio or full multimodal-coverage claim may be fabricated.
Public structured-data success would not establish natural-media performance.

Save original report/drafts, trace, catalog pages/coverage evidence, full-read
lineage, evidence ledger, exact target/question, code/data/import/model/profile
hashes, generation settings, budgets, timing, failures and rejection reasons.
Record hash scope explicitly; canonical messages are not HTTP wire bytes, and
operator-recorded model settings are not loaded-weight attestation. Preserve
all original outputs, including failures. Companion review may repair Markdown
links but never rewrite analytical claims. Shared-host measurements are not
isolated benchmarks or minimum hardware requirements.

Before accepting any result, a separate reviewer checks raw-source fidelity and
all substantive claims under this frozen protocol. Record omissions distinctly
from fabricated assertions. Keep implementation checks separate from model
accuracy; this one development case yields no success-rate, human-agreement,
held-out generalization, scale or analyst-time-saving estimate.

Any later criterion/question change requires a new version and an explicit
reason. Preserve this protocol and earlier outputs; tuning after reading public
outputs remains development, not an untouched evaluation.
