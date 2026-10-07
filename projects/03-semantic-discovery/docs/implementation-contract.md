# Implementation contract

Development contract for parallel implementation. Python package `vopt`, Python 3.11+. Dictionaries at interchange boundaries; root owns validation/release/CLI/UI. Extraction owns `ingest.py`, `extract.py`, extraction tests. Search owns `query.py`, `search.py`, `ontology.py`, search tests. No cloud APIs.

## Private ingestion record

`{schema_version:1, document:{doc_id,title,manufacturer,models:[str],category,language,revision,source_uri,rights:{basis,evidence_url,attribution}}, sha256, processing_version, pages:[], assertions:[]}`.

Page: `{page_number:1,width,height,status:'ok'|'failed',engine,text,lines:[{text,bbox:[x0,y0,x1,y1]}],error:null|str}`. Preserve all page failures and coverage. Optional page image paths remain private. Manifest adds `path` externally to document metadata.

Assertion: `{assertion_id,doc_id,model,variant:null|str,attribute,value:number|str,value_max:null|number,unit:null|str,qualifier:'rated'|'peak'|'no_load'|'unspecified',evidence:{page:1,bbox:[...],text},status:'candidate',confidence:number,method:str}`. Candidate confidence is not a calibrated probability. Human decisions stored separately by assertion ID and record SHA.

Attributes: `input_voltage` (V), `output_voltage` (V), `frequency` (Hz), `input_current` (A), `input_power` (W), `output_power` (W), `horsepower` (hp, no automatic input-watt conversion), `speed` (rpm), `weight` (kg), `blade_diameter` (mm), `displacement` (cm3), `capacity` (L), `pressure` (kPa). Category labels ordinary lowercase names (drill, saw, compressor, sewing machine, appliance). Optional document `model_categories:{model:category}` overrides the document category for a declared model in a mixed-equipment manual.

## Released bundle

`{schema_version:1,catalog_id,sequence:positive int,profile:'coverage'|'values',policy:{version:positive int,revoked_doc_ids:[str],revoked_assertion_ids:[str]},documents:[],assertions:[],integrity:sha256}`. Integrity over canonical JSON excluding integrity. Full snapshots, increasing sequence and nondecreasing policy version.

Released document: `{doc_id,title,manufacturer,models,category,language,revision,request_ref,processing_status:'complete'|'partial'}`. No source path, source URL, evidence text, image, OCR, or unapproved summaries.

Released assertion: `{assertion_id,doc_id,model,variant,attribute,qualifier,status:'reviewed',value?,value_max?,unit?,tolerance?,conditions?}`. Coverage profile forbids all value/condition/tolerance fields; values profile requires finite numeric value, optional upper bound, and canonical unit. Optional tolerance `{minus,plus,unit}` and `conditions:[str]` remain structured. Discrete alternatives are private unresolved candidates until a reviewer supplies a supported value/variant representation; never silently reinterpret them as a continuous range. Page/evidence remains private; explanations cite released assertion IDs. Records are strict allowlists.

Review decisions bind both an extraction fingerprint and the latest assertion review event ID (0 for first decision). Replacement uses a transactional compare-and-swap. Agent/fixture decisions are labeled; default release requires human decisions. A recorded actor label is provenance, not authenticated identity or proof of independent accuracy.

## Search APIs

`query.parse_query(text: str, documents: list[dict] | None = None) -> dict`: `{status:'ready'|'clarify'|'unsupported',text,terms:[],categories:[],models:[],constraints:[{attribute,op,value,value_max?,unit,qualifier?}],attributes:[],message,mode:'discovery'}`. No SQL or source access. Extend explicitly when needed; partial understanding must not silently drop constraints.

`search.Catalog(path)` with `import_bundle(bundle:dict) -> dict`, `search(query:str,limit:int=10,method:str='lexical') -> dict`, `info()->dict`. Root implements import/lifecycle in `catalog.py`; search owns functions `build_index(connection, documents, assertions)` and `search(connection, query, limit=10, method='lexical')`. Tables: documents(doc_id TEXT PRIMARY KEY, data TEXT), assertions(assertion_id TEXT PRIMARY KEY,doc_id TEXT,model TEXT,attribute TEXT,data TEXT), catalog_meta(key TEXT PRIMARY KEY,value TEXT). Other FTS/semantic index tables owned by search. Strict parameterized execution. Return `{status,plan,results:[{doc_id,title,model,revision,request_ref,score,matched_assertions:[],explanation}],message}`.

## Extraction APIs

`ingest.ingest_pdf(path, document, output_dir, force_ocr=False, resume=True, max_pages=None) -> dict`; `extract.extract_assertions(pages, document) -> list[dict]`. All OCR models local; no runtime downloads. Preserve errors per page. Processing cache under output_dir, checkpoint pages and final record. Root wraps lifecycle and manifest validation.
