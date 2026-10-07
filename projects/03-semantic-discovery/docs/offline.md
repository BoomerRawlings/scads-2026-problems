# Offline installation and qualification

Discovery uses Python's standard library and SQLite FTS5. Extraction adds local PyMuPDF, RapidOCR, ONNX Runtime, and bundled OCR weights. Neither profile requires credentials or remote inference. Keep extraction/review workspaces separate from the metadata-only discovery catalog.

## Current artifact status

Exact qualification results are preserved in [build verification](../reports/build-verification.json): regression totals, source/wheel hashes, cold installs, and portable-runtime proofs. Each proof applies only to its accompanying artifact hash. Earlier intermediate packages remain local historical artifacts; use the named final outputs below.

The final output names are:

| Artifact | Purpose |
| --- | --- |
| `wheelhouse/vopt-0.1.0-qualified/` | Exact wheels, hash locks, license inventory, fresh-install proofs |
| `dist/vopt-0.1.0-qualified-discovery-windows-x64/` and `.zip` | Discovery runtime, bundled CPython, launcher, relocation proof |
| `dist/vopt-0.1.0-qualified-extraction-windows-x64/` and `.zip` | Extraction/review runtime, bundled CPython and OCR assets, relocation proof |

Qualification targets **Windows x64 / CPython 3.12**. The tested interpreter is CPython 3.12.13 with SQLite 3.53.1 and FTS5; the host reports ARM64 while the interpreter uses `win_amd64` wheels. This does not qualify native ARM64, Linux, macOS, or another Python ABI. Read each generated manifest and proof for exact versions, hashes, and status.

## Build from acquired local assets

Run from the project environment. Output directories must be new or empty; existing artifacts are not deleted. The local build backend must already be available to `uv`.

```powershell
.venv/Scripts/python.exe scripts/package_offline.py --profile all --output wheelhouse/vopt-0.1.0-qualified --from-wheelhouse wheelhouse/release-qualified/wheels --verify
.venv/Scripts/python.exe scripts/package_portable.py --wheelhouse wheelhouse/vopt-0.1.0-qualified --output dist/vopt-0.1.0-qualified-discovery-windows-x64 --profile discovery --zip
.venv/Scripts/python.exe scripts/package_portable.py --wheelhouse wheelhouse/vopt-0.1.0-qualified --output dist/vopt-0.1.0-qualified-extraction-windows-x64 --profile extraction --zip
```

Initial preparation may use `package_offline.py --allow-download` into a separate new directory. Downloading belongs to preparation; installation, qualification, and normal runtime use local assets. Rebuild and requalify after source changes.

The wheelhouse pins the environment's installed dependency closure, honoring platform markers. It contains `wheels/`, profile-specific `requirements-*.lock` files with SHA-256 hashes, `licenses/`, `manifest.json`, and `proof-*.json`. OCR weights live inside the RapidOCR wheel. The initial combined wheelhouse had 16 wheels, approximately 116 MB, and three ONNX models; consult the final manifest for the rebuilt inventory.

The portable assembler copies the complete local CPython base, including its license, then installs the selected lock with bundled pip using `--no-index --no-cache-dir --require-hashes`. The resulting runtime needs no separately installed Python or package installer. `portable-manifest.json` inventories file hashes; `proof-portable.json` records the relocated-runtime test.

## Run a portable profile

Extract the selected ZIP into its own directory, then run:

```powershell
.\vopt.cmd doctor
.\vopt.cmd import released.json --catalog catalog.sqlite3
.\vopt.cmd search "manuals with horsepower" --catalog catalog.sqlite3
.\vopt.cmd serve --catalog catalog.sqlite3 --port 0
```

On the extraction profile, use `vopt.cmd ingest manifest.jsonl --workspace private` and `vopt.cmd serve --workspace private --port 8763`. `doctor` inventories local packages and model hashes. Missing assets produce local diagnostics; there is no download fallback. Lexical ranking is the default; `--method semantic` selects the local ontology/TF-IDF comparator, not a pretrained model.

For wheelhouse-only installation, provision a compatible interpreter and `uv` separately:

```powershell
uv venv --python 3.12 --offline --no-python-downloads .offline-discovery
uv pip install --python .offline-discovery/Scripts/python.exe --no-index --offline --no-cache --find-links wheelhouse/vopt-0.1.0-qualified/wheels --require-hashes -r wheelhouse/vopt-0.1.0-qualified/requirements-discovery.lock
.offline-discovery/Scripts/python.exe -I -m vopt doctor
```

Use the extraction lock in a separate environment for extraction/review. The wheelhouse alone does not bundle Python or `uv`; the portable ZIP does bundle CPython.

## What the proof establishes

Fresh environments install solely from the wheelhouse, with index/cache access disabled and hashes required. Python runs with `-I`; the proof checks imports come from the installed wheel. Portable verification repeats the smoke test using the copied interpreter with Python-path overrides removed.

The runtime exercise checks preflight, catalog import, both rankers, rejection of a cross-model numeric conjunction, source-sentinel exclusion, and values-to-coverage downgrade. Discovery must have no extraction packages or models. Extraction additionally OCRs an authored image-only specification PDF, checks numeric assertions, and verifies the supervisor controls the actual native interpreter PID. These authored fixtures remain in the verification subdirectory; they test packaging functionality, not real-manual accuracy.

Python socket connections, address resolution, and datagram sends are blocked during the smoke test; successful proofs record zero attempted Python network calls. This is a **guarded cold install and relocation test on an existing host**, not OS-level air-gap or clean-machine certification. Native-library networking is not independently intercepted. Qualification on an actual target still requires OS network isolation, representative inputs, and recorded results.

## Runtime versus research material

Each runtime's `project-source.zip` uses a source allowlist and excludes **`data/`, `runs/`, and `examples/`**. Real-corpus PDFs, OCR caches, review ledgers, reference labels, and development catalogs are not runtime payloads. Discovery receives only an explicitly imported release bundle.

The separately assembled research archive includes admitted originals, evidence, frozen extraction records, review decisions, and reports for reproduction. It belongs on the extraction/research side and must not be imported into discovery. Unadmitted source candidates are excluded. Research artifacts remain agent-inspected development evidence, not human gold or an accredited release.

Project redistribution licensing remains undeclared in `pyproject.toml`. Bundled notices and the dependency inventory record third-party terms; project licensing and applicable dependency redistribution/corresponding-source requirements remain publication gates.
