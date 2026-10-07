# Corpus acquisition and inspection

Checked 6 October 2026. Seven authentic historical scans acquired: 869 PDF pages, 58,182,087 bytes. Four powered-equipment manuals admitted, one hand-tool negative/control admitted, two OEM-style government publications retained as candidates. These are a useful development corpus, **not completion of the representative-corpus or untouched-evaluation gates**.

`corpus-manifest.jsonl` pins original PDF bytes, page counts, source URLs, rights evidence, document identities and evaluation families. Paths are project-relative; `base: ".."` resolves them from `data/`. Admission is explicit. `corpus/evidence-leads.json` contains 20 agent-source-reviewed leads (17 admitted, 3 candidate-only), with PDF page numbers, rendered evidence paths, units and semantic traps. No lead is human gold or an automatic release approval.

## Acquired material

| Manual | PDF pages | Status | Useful content / limitations |
| --- | ---: | --- | --- |
| [TM 9-617, Generating Unit M18](https://www.ibiblio.org/hyperwar/USA/ref/TM/pdfs/TM9-617.pdf) | 158 | Admitted | 30 kW, 60 Hz; dry weight and multiple capacity kinds; 125/250 V output configurations; appended 1944 changes. |
| [TM 9-618, Generating Units M7/M7A1/M15A1](https://www.ibiblio.org/hyperwar/USA/ref/TM/pdfs/TM9-618.pdf) | 178 | Admitted | 28 kW versus 35 kVA; generator variants; five manufacturers; 1945 changes appended to 1943 base manual. |
| [TM 9-1752, Homelite HRH-28](https://www.ibiblio.org/hyperwar/USA/ref/TM/pdfs/TM9-1752.pdf) | 51 | Admitted | 1,500 W, 30 V DC, 3,400–3,600 rpm engine. OCR confuses HR/HRH with HE/HEH. Assembly, engine and generator have separate model identities. |
| [TM 9-834, Vehicular General Purpose Unit Equipment](https://www.ibiblio.org/hyperwar/USA/ref/TM/pdfs/TM9-834.pdf) | 110 | Admitted | Multiple compressor, welder and charger models; fractional hp; engine versus compressor rpm; conflicting nominal/output values; dense data and narrative sections. |
| [TM 9-867, Maintenance and Care of Hand Tools](https://www.ibiblio.org/hyperwar/USA/ref/TM/pdfs/TM9-867.pdf) | 119 | Admitted control | Hand tools with no named product-model list. Empty models intentional. Does not count toward powered-tool coverage; useful retrieval negative. |
| [TM 5-2036, Economy B-180 Pump](https://www.ibiblio.org/hyperwar/USA/ref/TM/pdfs/TM5-2036.pdf) | 127 | Candidate | LeRoi D-133 engine; 1,860 rpm, 133 cubic inches; performance charts. Body resembles reproduced OEM instructions; authorship of those pages remains unverified. |
| [TM 5-1154, Littleford 84-HD-3 Asphalt Kettle](https://www.ibiblio.org/hyperwar/USA/ref/TM/pdfs/TM5-1154.pdf) | 126 | Candidate | Series P/R/S, operating versus crated mass, multiple reservoir capacities, 1963 changes. OEM-style body authorship unresolved; also industrial construction equipment rather than household appliance. |

The four admitted powered manuals total **497 pages**, but M7 and M18 share substantial structure/text and remain **one evaluation family**. With the workshop compendium and Homelite, this is **three independent development groups**, not four independent holdouts. All model sections of TM 9-834 must remain together. The hand-tool control brings admitted pages to 616.

## Rights basis and limits

Admission uses the [archive's government-document rights declaration](https://www.ibiblio.org/hyperwar/), each original manual's War Department title/publication pages, and [17 USC 105](https://www.govinfo.gov/content/pkg/USCODE-2023-title17/html/USCODE-2023-title17-chap1-sec105.htm). Copies of the rights page, archive manual index and statute are under `corpus/evidence/`, with hashes in `snapshots.json`.

Every downloaded PDF's embedded searchable text was checked for copyright and reproduction-permission notices; none was found. Representative covers, publication orders, and specification pages were rendered and inspected. This is a bounded source review: OCR can miss notices, government publication does not prove government authorship of inserted private material, and the government-work public-domain basis is scoped to the United States. The two uncertain OEM-style volumes therefore stay candidates and are not default acquisitions/releases. The ordinary archive webpage's own terms are distinct from the public-domain originals it hosts.

No commercial modern manual was admitted merely because it was free to download. No share-alike source was silently treated as permissive. No contacts, purchases, private documents or classified sources were used.

## Other sources investigated

- [Wertheim High Arm, circa 1891, Victorian Collections](https://victoriancollections.net.au/items/52160b8819403a17c4ba265a): museum record explicitly labels the manual-page scan public domain. Direct catalog/download access encountered Cloudflare protection; actual PDF not acquired. Historical treadle machine unlikely to establish voltage/hp coverage. Retain as candidate, not an admitted document.
- [LulzBot TAZ 2.1 manufacturer-hosted manual](https://download.lulzbot.com/TAZ/2.1/documentation/2013Q4/LulzBot_TAZ_2.1-User_Manual-ebook.pdf): prior research identifies CC BY-SA 3.0; conditional and born-digital. Not admitted.
- [US Forest Service chain-saw course](https://www.govinfo.gov/app/details/GOVPUB-A13-PURL-gpo238931): official government-authored course, but mainly technique/safety, not named-model technical specifications. Lower-priority supplementary domain material, not acquired.
- [Smithsonian sewing-machine history](https://library.si.edu/digital-library/book/sewingmachineit00coop): explicitly public-domain/CC0, but historical survey rather than a product specification manual. Not acquired merely to inflate counts.
- Manufacturer/military sewing-machine manuals can contain incorporated private copyrighted pages; a discovered Singer manual notice is a reason to inspect actual rights, not a reason to infer that every military manual is free of copyright.

## Reproduction

From project root:

```powershell
.venv/Scripts/python.exe scripts/acquire_corpus.py --verify-only
.venv/Scripts/python.exe scripts/acquire_corpus.py
```

The first command is entirely offline. The second is an explicit online setup utility; it is not imported by ingestion/search. It downloads admitted entries only, verifies SHA-256 and byte count, caps each file at 40 MiB, uses HTTPS with bounded timeouts, writes atomically, and refuses to replace an existing mismatched file. `--ids` selects admitted documents. Candidate admission requires a documented rights decision and manifest change; the utility cannot bypass it with a flag.

Some archive URLs intermittently returned HTTP 503 or timed out. The admitted manifest preserves same-resource query variants that successfully returned original PDFs; all variants must match the exact pinned bytes. Wikimedia and Internet Archive mirrors were inspected as leads, but final pinned files came from HyperWar. Do not silently substitute a different edition or scan when hashes differ.

## What this can establish

- Authentic scan/OCR handling, tables and narratives, fractional values, multiple model sections, qualifiers, basic revision complications and source evidence.
- A real offline extraction/search demonstration and source-auditable development checks.
- Current errors without hiding behind generated manuals or synthetic degradation.

What remains unestablished: unseen-manufacturer/document-family generalization, independent human annotations, representative modern handheld-tool/appliance coverage, full multilingual/layout diversity, calibrated extraction confidence and production retrieval usefulness. These sources were inspected during development and must never be relabeled as untouched test material. Future evaluation needs genuinely reserved documents and independent reviewers.

## Source-inspection artifacts

`data/corpus/evidence-leads.json` holds 20 agent-inspected leads (17 admitted, three rights candidates), including essential controlled conditions. `data/corpus/model-category-evidence.json` records only source-confirmed model categories and page numbers. These are private development reference artifacts, not released discovery metadata or human gold.

`data/corpus/m18-candidate-audit-v1.json` preserves an exhaustive audit of all 17 candidates from the original M18 processing version. Every number/unit was transcribed correctly, but only five claims retained sufficient model/component and condition scope; two of those five duplicate another claim. Nine require condition/configuration repair; three attach engine or railroad-example weights to the generator. The full rubric, original fingerprint, observations, rendered pages and hashes remain available even after parser revisions. Selected corrected releases must not be reported as raw extraction accuracy.

`scripts/prepare_development_release.py` applies only an explicitly authored, fingerprint-pinned agent review plan to `runs/real-workspace`. Default invocation checks; `--apply` records agent decisions and builds clearly named development catalogs. It never manufactures a candidate missing from extraction, never records a human actor, and leaves unselected candidates pending. Replaying the same plan is idempotent; changed extraction/source bytes or differing reviews are refused. The regular release API/CLI retains its human-review requirement.

Exact review replay requires the private extraction records, admitted PDFs, inspected PNGs and decision plan together. PDFs/PNGs/runtime records are excluded from Git; source acquisition alone does not recreate the frozen review state. Source-reference JSON integrity is canonicalized to tolerate line-ending changes. Standalone released discovery bundles need none of those private source artifacts.

Completed development replay: `examples/agent-review-decisions.json` records 14 selected source-inspected candidates; both `runs/development-values.json` and `runs/development-coverage.json` contain five admitted documents and 14 approved observations. Seven extraction candidates remain pending; inspected leads 012, 013 and 015 remain unmatched. Every recorded actor is an agent. Repeat replay creates no additional events. The repaired M18 output is audited separately in `data/corpus/m18-candidate-audit-v2.json`: seven supported emitted claims on the same previously inspected source, with no held-out or recall claim. The original 5/17 result remains preserved.
