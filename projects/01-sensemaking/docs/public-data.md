# Public-source qualification: ROR + Wikidata

Checked **2026-10-06 (Pacific)**. Qualification and adapter specification. A subsequent [bounded capture](public-capture.md) preserves eight ROR records and four pinned Wikidata records; the [offline importer](public-import.md) now exposes conservative relationships and inspectable claims through the existing tools. Public model evaluation remains unfinished. No linked media was downloaded. These sources support organization identity, relationships, and recorded changes; they do not establish operational readiness, supplier risk, or misconduct.

## Access, rights, and versioning

| Source | Qualified use | Acquisition and provenance |
| --- | --- | --- |
| ROR | IDs and metadata: CC0. Use v2 API / schema 2.1 JSON, the format of record. | Prefer a specific Zenodo release for repeatable bulk work: version DOI, release date, filename, published checksum, local SHA256. Releases are typically at least monthly; API updates follow releases. Current dumps include inactive/withdrawn records; searches default to active. [Dump documentation](https://ror.readme.io/docs/data-dump) |
| Wikidata | Structured entity data: CC0; other namespace prose is generally CC BY-SA. | Save full entity JSON, `lastrevid`, `modified`, request URL, retrieval UTC, and SHA256. Fetch a pinned entity using `Special:EntityData/QID.json?revision=REVISION`. A collection of per-entity revisions is not an atomic whole-database snapshot. [Licensing](https://www.wikidata.org/wiki/Wikidata:Licensing), [revision access](https://www.wikidata.org/wiki/Wikidata:Data_access#Revisions_and_caching) |
| Images/video linked from either source | Not covered by the registry/entity CC0 dedication. | Qualify each actual file separately. For Commons retain file-description revision, original URL, author, license/version, required attribution, file revision and SHA256. A Wikidata `P18` filename grants no extra rights. Linked external documents need their own reuse basis. [Commons reuse requirements](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia) |

ROR record `admin.created` and `admin.last_modified` describe registry editing, not the organization's real-world creation or a relationship's effective date. Preserve them separately from `established`. [Field definitions](https://ror.readme.io/docs/fields)

For later Wikidata bulk processing, pin a **dated full JSON dump**, checksum, selection specification and selected-ID list. Dumps are weekly; `latest` is not a reproducible version. Avoid truthy-only data for conflict analysis: it drops qualifiers/references and excludes non-best-ranked statements. [Dump formats](https://www.wikidata.org/wiki/Wikidata:Database_download), [statement semantics](https://www.mediawiki.org/wiki/Wikibase/Indexing/RDF_Dump_Format#Statement_types)

## Current service limits

| Service | Documented limits / consequence |
| --- | --- |
| ROR REST | General limit: 2,000 requests / 5 minutes / IP; at most 10,000 retrievable search results. Use dumps for the full registry. [REST API](https://ror.readme.io/docs/rest-api#registration-and-rate-limits) |
| ROR client IDs | **Registration is currently paused.** The current notice says no distinction by client-ID presence is enforced during the pause. The 2,000-with-ID / 50-without-ID policy remains described as planned, not currently active. Recheck before implementing registration. [Current notice](https://ror.readme.io/docs/client-id) |
| Wikimedia entity APIs | Current general policy lists 200 requests/minute for unauthenticated clients with a compliant identifying User-Agent; unidentified traffic gets 10/minute. Recommend at most three concurrent requests; obey `Retry-After` on 429/503. These 2026 limits may change. [Rate-limit policy](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits) |
| Wikidata Query Service | 60-second query deadline; 60 seconds processing/client/minute; 30 erroneous queries/minute; at most five concurrent queries/IP. Use narrow discovery queries, then retrieve full entity JSON. [WDQS limits](https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual#Query_limits) |

**Proposed adapter policy:** one request at a time, at most one/second; identifying User-Agent with project URL; cache responses, bounded retries with backoff, honor service headers, and stop cleanly on rate limits. This is our conservative policy, not a promised service allowance. No account, paid endpoint, or credentials needed for these small public reads. Recheck limits at acquisition time.

## Mappings to preserve

Keep the raw source predicate beside every normalized edge. `A` means the record/item being processed; `B` is its referenced target.

| Source assertion | Proposed normalized interpretation |
| --- | --- |
| ROR `relationships.type=child` | `contains(A,B)` |
| ROR `parent` | `contains(B,A)` |
| ROR `related` | Separately typed `related_to(A,B)`; never containment/dependency. |
| ROR `successor` / `predecessor` | `succeeds(B,A)` / `succeeds(A,B)`; retain direction and record status. |
| Wikidata [P749](https://www.wikidata.org/wiki/Property:P749), parent organization/unit | `contains(B,A)`, retaining qualifiers and statement scope. |
| Wikidata [P355](https://www.wikidata.org/wiki/Property:P355), child organization/unit | `contains(A,B)`, retaining original meaning and entity type. |
| Wikidata [P361](https://www.wikidata.org/wiki/Property:P361) / [P527](https://www.wikidata.org/wiki/Property:P527) | Preserve `part_of(A,B)` / `has_part(A,B)` separately; organizational containment requires an explicit, reviewed projection. |
| Wikidata [P1365](https://www.wikidata.org/wiki/Property:P1365) / [P1366](https://www.wikidata.org/wiki/Property:P1366) | `succeeds(A,B)` / `succeeds(B,A)`; replacement is not identity equivalence. |
| ROR `external_ids[type=wikidata]`; Wikidata [P6782](https://www.wikidata.org/wiki/Property:P6782) | Candidate crosswalk. Validate entity type and reciprocal identifiers; preserve ambiguous/many-to-many links. |

ROR supports multiple parents and temporal/lateral relationships. Deduplicate reciprocal edges while retaining both source assertions. Neither source mapping creates `depends_on` or `supplied_by`. New relation types require an explicit graph-contract extension; never squeeze them into the prototype's three existing relation labels. [ROR relationships](https://ror.readme.io/docs/relationships)

Keep Wikidata statement GUID, rank, snak type, value, all qualifiers and references. Preserve date precision/calendar; unknown/no-value is not an empty string. Separate `P580/P582/P585` validity from retrieval/edit time. Compare claims only after checking compatible entity, predicate, scope, and time; differing values are review candidates, not automatically contradictions. [JSON model](https://www.mediawiki.org/wiki/Wikibase/DataModel/JSON), [date representation](https://www.wikidata.org/wiki/Help:Dates)

## Verified seeds and bounded cases

| Organization | Inspected identifier links | Inspected Wikidata revision |
| --- | --- | --- |
| National Cancer Institute | [ROR 040gcmg81](https://api.ror.org/v2/organizations/040gcmg81) ↔ [Q664846](https://www.wikidata.org/wiki/Special:EntityData/Q664846.json?revision=2550610368) | 2550610368 |
| National Institutes of Health | [ROR 01cwqze88](https://api.ror.org/v2/organizations/01cwqze88) ↔ [Q390551](https://www.wikidata.org/wiki/Special:EntityData/Q390551.json?revision=2543960225) | 2543960225 |
| CERN | [ROR 01ggx4157](https://api.ror.org/v2/organizations/01ggx4157) ↔ [Q42944](https://www.wikidata.org/wiki/Special:EntityData/Q42944.json?revision=2541849285) | 2541849285 |

These identifier links were inspected during source qualification. Reciprocal IDs
remain candidates requiring identity review; they do not authorize merging records.
CERN's ROR record is outside the subsequent eight-record frozen ROR capture.

**Real identity trap:** NIH's ROR record also lists `Q6973636`, with no preferred Wikidata ID. That item is a [Wikimedia list article](https://www.wikidata.org/wiki/Special:EntityData/Q6973636.json?revision=2216204992), not NIH, and has no reciprocal `P6782`. Preserve it as a rejected/unresolved candidate; do not merge it into the organization.

1. **Small ROR case: eight named records.** NCI plus its seven listed neighbors: children `05bjen692`, `03v6m3209`, `05n6zrm60`, `00vkwep27`; parent `01cwqze88`; related `00w52vt71`, `02qyzaf42`. Question: which connections are hierarchical versus merely related, and which identities require review? Freeze the exact eight response bodies and hashes. [Observed NCI record](https://api.ror.org/v2/organizations/040gcmg81)
2. **Larger Wikidata case: at most 250 entities.** Seed the three verified QIDs; traverse `P749/P355` to two hops, sort candidate QIDs deterministically, cap before fetching, and freeze the resulting ID/revision list. Include the rejected NIH-list crosswalk as a negative identity case. Question: how do recorded organization relationships differ across scope/time/source? NCI already has multiple parent claims with qualifiers; NIH has multiple inception claims. Retain these for review without declaring them errors. [NCI revision](https://www.wikidata.org/wiki/Special:EntityData/Q664846.json?revision=2550610368), [NIH revision](https://www.wikidata.org/wiki/Special:EntityData/Q390551.json?revision=2543960225)

These are acquisition ceilings, not observed corpus counts or benchmark results. For both cases record truncation/frontier IDs, included/excluded relation types, acquisition window, failures and bytes. Produce an inspectable source ledger and a separate reviewed answer set before scoring. Public source-media coverage remains unqualified; registry text does not substitute for natural images/video.

## Independence and scale boundaries

Two databases can repeat one upstream assertion. Track Wikidata reference URLs/`P248` source IDs and ROR provenance where available; reciprocal identifiers alone do not establish independent corroboration. Label a shared or unknown origin explicitly. Neither a database's reputation nor a repeated claim supplies ground truth.

ROR documents over 120,000 registry records; Wikidata's access guide describes over 120 million items. Those remote sizes do **not** describe this project's indexed or tested corpus. Report measured local entities, statements, source bytes, memory, latency and coverage separately. Grow bounded collections only after those measurements; a full Wikidata mirror is outside this first acquisition plan. [ROR access scope](https://ror.readme.io/docs/rest-api), [Wikidata access scope](https://www.wikidata.org/wiki/Wikidata:Data_access)
