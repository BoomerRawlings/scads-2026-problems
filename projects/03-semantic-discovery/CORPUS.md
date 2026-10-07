# VOPT corpus assessment

**Five admitted original scanned manuals, 616 pages, acquired and processed.** Four powered-equipment manuals contribute 497 pages across three development families. The remaining 119 pages are a hand-tool negative control. This is authentic development material; representative coverage and untouched evaluation remain incomplete.

The [admission manifest](data/corpus-manifest.jsonl) records source URLs, file hashes, page counts, rights evidence, attribution, scan origin, and family assignments. [Acquisition research](data/corpus-research.md) preserves the source assessment. Downloads happened during preparation; extraction and discovery run locally.

## Acquired corpus

| Manual | Pages | Admission and role |
| --- | ---: | --- |
| TM 9-617: M18 generating unit | 158 | Admitted; generating-unit family |
| TM 9-618: M7, M7A1, M15A1 generating units | 178 | Admitted; same family as M18 to prevent split leakage |
| TM 9-1752: Homelite HRH-28 | 51 | Admitted; assembly, HR-28 generator, and HR engine distinguished |
| TM 9-834: Workshop equipment | 110 | Admitted; multi-model compendium, one evaluation family |
| TM 9-867: Hand tools | 119 | Admitted negative control; no named product models or powered-equipment coverage credit |
| TM 5-2036: Economy B-180 pump / LeRoi engine | 127 | Acquired candidate; OEM-body authorship/insert rights unresolved |
| TM 5-1154: Littleford asphalt kettle | 126 | Acquired candidate; OEM-body authorship/insert rights unresolved |

The two candidates' 253 pages are excluded from admitted processing, releases, and the research source package. Government covers and archive declarations alone did not resolve their privately authored content.

Admitted records use a **public-domain, United States scope** rights basis, supported by government authorship, archive declarations, and saved source/legal evidence. This is recorded agent evidence review, not legal clearance. Public-domain and permissively licensed material are distinct categories; a site's general openness does not establish rights for every attachment.

## Evidence and measured limits

[Source-inspected leads](data/corpus/evidence-leads.json) contain 20 agent references: 17 from admitted manuals and three from unadmitted candidates. The actual development release contains five document records and 14 selected agent-reviewed observations, with seven extraction candidates still pending. All review actors are agents. Missing selected facts remain missing; source references are not silently substituted into the released catalog.

The [extraction report](reports/extraction-development.md) separates page execution, selected field matches, and complete version-specific M18 candidate audits. The original M18 audit found 17/17 numeric transcriptions supported but only 5/17 fully scoped candidates, including two duplicates. The repaired version has a separate audit. These inspected development cases establish neither human accuracy nor exhaustive recall.

The [retrieval report](reports/retrieval-development.md) evaluates both rankers on the same frozen authored queries. On the actual values catalog, macro recall@10 is 0.912 across 17 known-positive queries/22 relevant document-model scopes; MRR@10 is 0.941. Coverage recall is 0.929 across seven positive queries/12 scopes. Both rankers meet 33/33 authored plan-status expectations and record zero numeric violations among nine returned values scopes checked. These are partial agent-reference labels, not corpus-wide precision or an untouched test. Synthetic conflict cases and scale benchmarks are reported separately.

All families were inspected during development. Source-inspected [model categories](data/corpus/model-category-evidence.json) repair compendium/category ambiguity; that repair is a development result. The hand-tool control tests missing metadata and document-only discovery, not powered-tool extraction performance.

## Remaining corpus gates

This corpus concentrates on historical English-language US government utility and workshop equipment. It does not establish broad handheld-tool, household-appliance, overseas-language, modern-manual, poor-scan, or unseen-layout coverage.

Expand rights-qualified authentic sources against the [acceptance coverage matrix](ACCEPTANCE.md), including continued tables, footnotes, operating conditions, variants/revisions, damaged scans, and absent attributes. Keep derivatives and shared templates in one family. Reserve untouched families and queries before further tuning; obtain exhaustive independent human annotations before accuracy or labor-savings claims. Preserve original, born-digital, and synthetic scan groups separately.

The problem's existing unclassified use-case mapping remains an external dependency; use it to validate the provisional taxonomy when available. Corpus outcomes and unresolved gates feed the [implementation roadmap](ROADMAP.md).

## Earlier research leads, not admitted corpus

These preliminary leads were not acquired or included in reported metrics:

| Lead | Recorded evidence and remaining work |
| --- | --- |
| [Wertheim sewing-machine manual, circa 1891](https://victoriancollections.net.au/items/52160b8819403a17c4ba265a) | Museum catalog labels the manual-page scan public domain and requests attribution. Inspect actual PDF and technical attributes. Catalog's 19 double-sided printed pages are not a verified PDF count. |
| [LulzBot TAZ 2.1 manual](https://download.lulzbot.com/TAZ/2.1/documentation/2013Q4/LulzBot_TAZ_2.1-User_Manual-ebook.pdf) | Indexed manufacturer copyright text indicates CC BY-SA 3.0; direct inspection remained unresolved. Confirm rights, share-alike scope, and scan origin before admission. Rasterizing an ebook would be synthetic, not an authentic scan. |
