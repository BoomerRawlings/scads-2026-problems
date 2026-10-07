# VOPT operating guide

Run commands from this project directory. `python` below means `.venv/Scripts/python.exe` in the development environment, or the interpreter inside a qualified offline package. The application never downloads assets; acquisition and dependency preparation are separate commands.

Current evidence and unresolved gates: [acceptance status](reports/acceptance-status.md). The shipped development catalog contains agent-reviewed observations; it is not human gold.

## Guided search

The current source interface opens with **Equipment → Specification → Results**. Choose an equipment type and optional model, then add specifications, comparisons and units. Rating and operating conditions apply to every specification. Coverage catalogs offer presence filters only. **Search by text** remains available on the first step.

Back and Edit preserve selections. Matches can be saved in the request list and exported as JSON; the list remains in memory until refresh or close. Missing/conflicting records appear separately under **Needs more detail**. Match evidence and the interpreted query are available in expandable details.

```powershell
.venv/Scripts/python.exe -m vopt serve --catalog runs/development-values.sqlite3 --port 58595
```

The qualified 0.1.0 portable packages below preserve the earlier interface and source snapshot. They have not been rebuilt for this interface revision.

## Run the qualified local build

On this workspace, the bundled discovery runtime can open the existing development release without installing Python:

```powershell
.\dist\vopt-0.1.0-qualified-discovery-windows-x64\vopt.cmd import runs/development-values.json --catalog runs/local-discovery.sqlite3
.\dist\vopt-0.1.0-qualified-discovery-windows-x64\vopt.cmd serve --catalog runs/local-discovery.sqlite3 --port 0
```

Open the printed URL. Try `model HR-28 and output power >= 1.4 kW and output voltage >= 30 V and condition "DC"`. The same catalog was verified in a directory containing only released metadata, with extraction packages absent. [Runtime proof](reports/catalog-only-runtime-proof.json).

Portable ZIPs include Python, licenses and qualification fixtures; real source/review data remain separate in `dist/vopt-research-evidence.zip`. Its `RESTORE.txt` explains restoration and exact agent-review replay. On another device, transfer the chosen runtime ZIP and released JSON explicitly; Git ignores generated runtimes, source PDFs and workspaces. See [offline qualification](docs/offline.md) and [exact artifact hashes](reports/build-verification.json).

## Install and check

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -e '.[extraction,test]'
.venv/Scripts/python.exe -m vopt doctor
.venv/Scripts/python.exe -m pytest -q
```

Discovery needs only Python with SQLite FTS5. Extraction/review rasterization also needs the extraction extra and three bundled ONNX weights. For an offline target, use [the wheelhouse procedure](docs/offline.md); preparation commands above are not an offline installation claim.

## Acquire and ingest

```powershell
python scripts/acquire_corpus.py
python scripts/acquire_corpus.py --verify-only
python -m vopt ingest data/corpus-manifest.jsonl --workspace runs/private
python -m vopt records --workspace runs/private
python -m vopt serve --workspace runs/private --port 8763
```

Open `http://127.0.0.1:8763`. Acquisition requires network access; all subsequent application commands can run disconnected. The manifest documents admission, rights, SHA-256, byte size, model identities and source locations. Candidate-rights records are skipped. Supplied pins must match before parsing. Downloadable PDFs are not automatically rights-qualified.

Ingestion checkpoints pages. Repeating the command reuses compatible pages, retries failed pages within its bound, and recomputes extraction when needed. `--force-ocr` exercises local OCR even if a PDF contains embedded text. `--max-pages N` deliberately creates partial coverage; it is not a complete-document result. `--no-resume` starts a new processing attempt without deleting prior review history.

`--page-timeout-seconds 120` sets the native-worker deadline for ingestion and targeted re-OCR (120 seconds by default). A supervised worker retains OCR models across pages; a timed-out worker is terminated, its page recorded as failed, and processing can continue. Execution settings belong to the processing identity; changing them invalidates reusable processing/review state. This bounds wall time, not total native memory or operating-system access.

```powershell
python -m vopt reextract --workspace runs/private
python -m vopt inspect tm9-617-m18-1944 --workspace runs/private
```

Re-extraction reads saved pages, not original PDFs or OCR models. Parser/metadata changes alter the review fingerprint. Failed/unreadable/unprocessed pages remain explicit; missing attributes are unknown.

When a page has a defective embedded OCR layer, explicitly rasterize selected original pages:

```powershell
python -m vopt reocr --workspace runs/private --doc-id tm9-1752-homelite-1942 --pages 3
```

This is operator-directed remediation, not an automatic extraction improvement. It preserves source identity, records page-engine changes, reruns extraction and invalidates prior reviews. Later ingestion from a different cached page set creates a new record; retain the frozen research artifact to reproduce reviewed results.

## Review and export

The review UI displays the original page, extracted claim, evidence text, conditions and prior decision. Verify model/component, value, unit, qualifier and applicability together. Corrections never overwrite the automatic candidate. Another tab's decision or a changed extraction rejects a stale submission. Reviewer names are provenance labels, not authenticated identity.

For CLI review, obtain the fingerprint and latest event token from `inspect`. First decisions use event `0`; replacing a decision requires its current event ID.

```powershell
python -m vopt review --workspace runs/private --doc-id DOC --assertion-id ASSERTION --decision accept --actor REVIEWER --fingerprint FINGERPRINT --event-id 0
python -m vopt export --workspace runs/private --out runs/released-coverage.json --catalog-id vopt-public --sequence 1 --profile coverage
python -m vopt validate runs/released-coverage.json
```

Default export requires current human review of every candidate, including explicit rejection of errors. `--allow-pending` releases only currently approved assertions and leaves the rest private; it does not claim complete annotation. `--review-kind agent` and `fixture` are explicit development modes, not human validation.

Coverage exports retain identity and observed attribute presence. Values exports additionally retain approved numeric values/ranges, canonical units, tolerances and operating conditions. Unresolved discrete alternatives can establish reviewed presence but cannot become a fabricated numeric range. Titles/model identities are also released metadata; review the manifest accordingly.

## Discover and prepare requests

Copy only the released bundle to a separate discovery environment:

```powershell
python -m vopt import runs/released-coverage.json --catalog runs/discovery.sqlite3
python -m vopt search "manuals with horsepower" --catalog runs/discovery.sqlite3
python -m vopt serve --catalog runs/discovery.sqlite3 --port 0
```

Open the local URL printed by the server (`--port 0` chooses an available port). Results explain the match, identify document revision/model, and supply request references. Add results to a request list and export local JSON; this does not transmit a request or fetch originals. Coverage-only numeric queries return unsupported. Direct specification answers are deliberately excluded.

Supported examples: `model M18 and frequency at least 60 Hz`, `input voltage between 110 and 240 V`, `rated speed below 3000 rpm`, Boolean `and`/`or`/parentheses, exact `variant "EU"` and `condition "less fuel and water"`. Bare voltage, approximations, unsupported technical predicates and insufficient evidence are explicit clarification/unknown outcomes. Inspect the plan and released conditions before refining a query.

## Replace, withdraw and roll back

Each bundle is a complete snapshot. Increase `sequence` for every new import. Increase policy `version` when changing release profile or cumulative revocation lists.

```json
{"version":2,"revoked_doc_ids":["withdrawn-document"],"revoked_assertion_ids":[]}
```

Export the replacement with `--policy policy.json`, then explicitly import it on each offline discovery system. Upstream re-extraction/review changes cannot remotely alter disconnected catalogs. Until replacement import, the previous released snapshot remains active.

```powershell
python -m vopt info --catalog runs/discovery.sqlite3
python -m vopt rollback --catalog runs/discovery.sqlite3 --sequence 1
```

Rollback accepts only retained snapshots allowed by the latest imported policy. It cannot restore revoked documents/assertions or withdrawn value fields, and does not lower the import sequence high-water mark. SHA integrity detects corruption, not publisher authenticity; import trusted bundles. Erasure checks cover the active SQLite file/indexes, not external copies, backups or storage-device history.

## Reproduce development evidence

```powershell
python scripts/evaluate_extraction.py --help
python scripts/evaluate_retrieval.py --help
python scripts/prepare_development_release.py --workspace runs/real-workspace
```

The release helper defaults to validation only. Its `--apply` mode replays explicitly pinned agent source reviews after extraction freeze. It never creates human gold or silently approves unmatched candidates. Development references and synthetic cases are separate from the [final evaluation protocol](eval/protocol.md).

## Supported deployment boundary

The UI binds loopback only; separate launch modes expose separate routes. It is a local research application, without multi-user authentication, distributed processing, or classified-system accreditation. Current evidence is English historical equipment; other languages, arbitrary categories, general paraphrase understanding and broad scan accuracy are not established. PyMuPDF uses AGPL/commercial licensing; consult the [vendor terms](https://pymupdf.io/licensing) before redistributing an extraction package. Corpus rights and dependency rights are separate.
