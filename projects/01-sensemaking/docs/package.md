# Inspectable source package

The source ZIP preserves the project as files you can inspect and run locally.
It does not contain Python, installed dependencies, llama.cpp, model weights or
a paid-service configuration. Building never downloads anything or invokes a
model. Python 3.11+ is required.

`dist/scads-sensemaking-source-v1.zip` is an immutable accepted-v12 checkpoint:
423 source files, 5,201,855 ZIP bytes, SHA256
`6d7fe829d4468f901282594f56693a89f2169d94e9a5f2009789578d6130cb27`.
Its review covers the known synthetic Riverwatch case, not public analytic
accuracy. The current working tree adds opt-in catalog integration and local
context admission under validation; those later edits are not in source-v1.
The v2 checkpoint is `scads-sensemaking-source-v2`, including the thirteen-case
viewer: eleven synthetic report/clarification cases and two public execution
failures. Riverwatch14 remains the default. The adjacent checksum and verification
files identify the actual archive and its completed checks. V2 packages the
reviewed development state; public analytic acceptance and scale remain open.

From `projects/01-sensemaking`, after the sources and reviews are frozen:

```powershell
.\.venv\Scripts\python.exe scripts/package_project.py build --name scads-sensemaking-source-custom
```

This form includes showcase source/configuration, so the README build commands
work after extraction, but omits its generated static folder. To include a current
ready-to-serve viewer, build it first. If the generated statement dataset is
absent after extraction, recreate it from bundled capture before building:

```powershell
# Only when datasets/public-research/imported-statements is absent:
.\.venv\Scripts\python.exe scripts/import_public_statements.py --import-data
.\.venv\Scripts\python.exe scripts/build_showcase.py
# Planned reviewed checkpoint; do not overwrite any prior output:
.\.venv\Scripts\python.exe scripts/package_project.py build --name scads-sensemaking-source-v2 --include-showcase
```

If the showcase destination already exists, follow its [safe rebuild
instructions](../showcase/README.md). The source packager checks the saved
showcase against a fresh in-memory build; a stale or edited build is refused.
It never rebuilds or replaces showcase files itself. On macOS/Linux use
`.venv/bin/python` instead.

Four files are written beneath the ignored project `dist/` directory:

- `<name>.zip`: source tree under `scads-sensemaking/`.
- `<name>.manifest.json`: exact copy of the ZIP's `PACKAGE-MANIFEST.json`.
- `<name>.sha256`: SHA256 of the entire ZIP.
- `<name>.verification.json`: member counts/bytes, hash and extraction checks,
  and the extracted core-regression result.

Every output uses exclusive creation. Any existing output for that name causes
refusal; choose a new name. No directories are deleted or old packages replaced.
The same frozen source bytes and options produce the same ZIP bytes, independent
of the output name. ZIP members are sorted, stored without compression, assigned
the fixed timestamp `1980-01-01 00:00:00`, and marked as ordinary mode-0644 files.
Source files are read as bytes. Historical report JSON is never reformatted,
corrected or replaced by a reconstructed report.

The explicit allowlist in `scripts/package_project.py` includes:

- Project Python entry points, `evidence_catalog.py`, `local_context.py`, schema, pinned requirements, README and local
  ignore rule; direct `scripts/*.py` and `tests/test_*.py` files.
- Direct Markdown/JSON documentation; authored graph, records, oracle,
  documents, annotations, transcripts, PNG and MP4 fixtures.
- Named report, review, ledger, trace, metadata, failure and rejected-report
  artifacts within example and preserved `local-pilot/local-*` and
  `public-pilot/public-*` case directories. The same named-file, path and byte
  limits apply; unrelated logs and nested files are excluded.
- Review protocol, recorded probes, runtime profiles, and source snapshots
  whose declared hashes match their original files. Snapshot discovery covers
  `implementation-v*/snapshot.json` under both local and public pilot directories;
  only named runtime/source files and the three public capture/import scripts
  are admitted inside each snapshot.
- The exact frozen `evaluations/public-pilot/PROTOCOL.md` review protocol.
- The verified public capture and byte-identical offline import, including raw
  ROR/Wikidata sources, capture/import manifests and projection decisions.
- Showcase source/configuration, README, QA record and test. With
  `--include-showcase`, exactly the current generated viewer members recorded
  in its build manifest are included as well.

Unlisted files are excluded: `.venv`, `runs`, raw logs, machine caches, model
files, credentials/global state, and `.codex/STATE.md`. Selected symlinks or
Windows junctions cause refusal. Public-source verification checks fixed IDs,
URLs, revisions, sizes and hashes offline, then compares every imported byte
with a fresh in-memory import. Snapshot hashes and a final source reread detect
changed inputs. Each file is bounded to 16 MiB and total source content to 64 MiB.

The current allowlist includes the [metadata catalog](evidence-catalog.md),
statement-level public importer, text-only local context admission and their
focused tests. Opt-in MCP/runner integration is implemented in the working tree,
under validation: metadata discovery does not earn source/citation credit,
inventory requires actual terminal cursor chains, and selected complete reads
retain exact source content. Local generation enforces explicit token/output,
serialized-byte and deadline bounds; `Workspace` still loads the whole corpus.
These later changes do not modify the source-v1 checkpoint.

The public protocol is a reviewer artifact, not model prompt content. Temporary
`runs/` outputs and generated statement datasets remain excluded from the
allowlist. After extraction, `scripts/import_public_statements.py`
verifies and reproduces the projection offline from the included raw capture;
its default invocation verifies a plan without writing. Use `--import-data` only
when creating a fresh output. Packaging these files establishes availability,
not a completed public analytic workflow or model acceptance.

The current source selection preserves both public attempts:
[NCI01](../evaluations/public-pilot/public-nci-01/REVIEW.md) failed context
admission; [NCI02](../evaluations/public-pilot/public-nci-02/REVIEW.md) passed its
configured context preflight but timed out during the report request. Each has
original failure JSON, run metadata and tool trace, plus a separate AI execution
review. Neither produced an analytic report or final citation ledger. Both now
appear as explicitly labeled failure records in the viewer, not accepted
analyses or semantic rejections of an answer. Their originals, later public
snapshots/profiles/probes and current UI are not retroactively present in v1.

Public Vulkan probe JSON records remain operator-recorded diagnostics. The
profile's source hashes include the ignored `runs/probe_vulkan_text.py`
supervisor, which is **not packaged**. A hash identifies that operator's helper;
it does not supply its source or make the exact probe runnable from this package.
Private startup logs, process records and machine paths are also excluded.
The curated installer/profile is included; device discovery and the recorded
resource-boundary failure establish no model-fit, inference or speed result.

Recheck a saved ZIP:

```powershell
.\.venv\Scripts\python.exe scripts/package_project.py verify dist/scads-sensemaking-source-v1.zip
.\.venv\Scripts\python.exe scripts/package_project.py verify dist/scads-sensemaking-source-v1.zip --evaluate
```

Verification checks the manifest inventory, member lengths/SHA256, canonical
ZIP metadata, contained paths and a fresh temporary extraction. `--evaluate`
also executes the included `sensemaking.py evaluate` using the current Python
environment; inspect unfamiliar source packages before choosing that option.
Build performs this regression automatically before writing the deliverables.
To verify the external archive checksum independently, use `Get-FileHash
<archive> -Algorithm SHA256` or `sha256sum <archive>` and compare the `.sha256`
file. A hash proves consistency, not the identity of a publisher.

The automatic extracted check covers the seven authored retrieval/conflict cases. It
does not verify a clean-device dependency installation, model download/startup,
cross-platform media decoding, live agent quality, public-data analysis, or
website deployment. Those remain separate validations; the saved reviews and
[acceptance record](acceptance.md) retain their original limits.

Grounded-media runs additionally retain original `media-observation-NN.json`
outputs. Their run metadata records source-call lineage, actual locators and
input/output fingerprints. These isolated outputs are included unchanged alongside
reports, traces and ledgers; image encodings and private reasoning remain excluded.

The source-only flavor was also extracted into a fresh temporary directory and
its included `scripts/build_showcase.py` successfully rebuilt the saved-case
viewer. See [reproduction evidence](package-reproduction.md) for the exact
checkpoint, byte comparisons and selected checks. This used the existing Python
environment, not a clean-device install; later edits require their own check.

A pre-integration source-only smoke archive included the standalone catalog, corrected
statement importer and frozen public protocol. Fresh extraction imported every
test module successfully (202 discovered cases), then executed only the 19 catalog
and 10 statement-import tests: all 29 passed, zero skips. Those tests reproduced
statement data from the packaged raw capture in fresh temporary directories;
neither `runs/` nor a pre-generated statement dataset was present. Network calls
were prohibited. The other discovered tests were not executed in this check;
the automatic seven-case core regression passed separately. This is an existing-
environment packaging check, not a model run or clean-device qualification.
