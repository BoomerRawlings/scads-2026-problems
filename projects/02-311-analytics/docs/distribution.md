# Offline wheel distribution

Version **0.7.0, bundle revision r2**, has actual clean offline installation evidence for both core
and MCP/geometry profiles. Both builds used existing wheelhouses with
`--no-network`; no dependencies were downloaded. Tests ran in fresh virtual
environments outside the checkout, on **CPython3.12.14, Windows x64 Python
(`win-amd64`) on this ARM64 Windows host**. This qualifies that local interpreter
target, not a second device, native ARM64 Python, Linux or macOS.

| Current artifact | Size | Contents |
| --- | ---: | --- |
| [Core bundle](../dist/analytics311-0.7.0-core-r2.zip) | 504,935 bytes | 11 entries; project wheel plus tzdata and fixed handoff files |
| [MCP/geometry bundle](../dist/analytics311-0.7.0-cp312-win-amd64-agent-r2.zip) | 30,047,215 bytes | 43 entries;34 wheels total and fixed handoff files |
| [Core release directory](../dist/release-core-v0.7-r2/release-manifest.json) | 440,995 wheel bytes | 2 wheels; passed clean-install receipt |
| [MCP/geometry release directory](../dist/release-agent-v0.7-r2/release-manifest.json) | 29,958,737 wheel bytes | 34 wheels; passed clean-install/optional-adapter receipt |

Each project wheel is92,999 bytes. Both contain the same23 source modules and five
packaged resources; their ZIP metadata differs. Independent verification checked
all36 wheel CRCs,3,959 RECORD entries, source/resource bytes, both bundle inventories
and every archive-entry hash. Core source stayed unchanged across both builds.
The observed free-disk minimum was32,430,878,720 bytes, above the enforced2GiB reserve.
Old release directories and archives were preserved.
[Build and integrity receipt](../examples/evidence/build-v0.7-r2.json),
[archive hashes and entries](../examples/evidence/handoff-bundles-v0.7-r2.json),
[core clean-install receipt](../examples/evidence/release-core-v0.7-r2.json),
[MCP/geometry clean-install receipt](../examples/evidence/release-agent-v0.7-r2.json).

Revision r2 includes the Maps locator transport and observed-comparison qualification
repairs in `maps.py` and `trend_maps.py`; these are the only packaged source changes
from the earlier0.7 bundles. Source, build-tool and fixed handoff hashes remained
unchanged during the builds. Separately recorded research-tool hashes identify
the matching repository context; those tools are not added to the bundles.
The shared package version remains0.7.0: use the exact r2 archive and a fresh
environment. These installation checks do not qualify live Maps rendering.

Both installations exercised fixture CLI discovery/validation/analysis, a four-row
asynchronous CSV, unchanged installed resources, nine modeled capacity scenarios,
five benchmark cases on100 generated records, and seven owned worker launches with
at most two concurrent processes. An actual abrupt exit86 verified lease release,
partial cleanup and re-export. The MCP profile additionally discovered all seven
stdio tools, completed four valid calls, rejected one invalid call and loaded
Shapely2.1.2 for a synthetic inside/outside polygon check. These packaging smokes
do not run a model, Elasticsearch, Kibana or the acquired real corpus.

Extract either archive into a fresh directory and follow its `INSTALL.txt`.
The MCP/geometry install requirement is `analytics311[geo,mcp]==0.7.0`; core is
`analytics311==0.7.0`. Python, model runtimes/weights, server images and real data
are not included. Generated archives remain outside version control.

## Transfer scope versus current research tooling

The allowlist remains exactly `tools/live_parity.py`, `tools/capacity_scenarios.py`,
`tools/benchmark_fixture.py`, `tools/stress_exports.py` and
`examples/capacity/scenarios.json`. These transferred harnesses were smoke-tested
against the installed0.7 package. The versioned core CLI is packaged; the ZIP is
not a complete copy of the repository's latest acceptance experiment.

The newer `tools/run_real_acceptance.py`, `tools/live_maps.py`,
`tools/measure_live.py`, `tools/agent_evaluation.py`, `tools/local_agent.py`
and `tools/capture_compressed.py` are **not transferred**.
To reproduce the real-corpus/agent study, use the matching repository revision,
its configuration and pinned evaluation/runtime definitions, official-boundary
receipt and required data artifacts; separately provide the compatible server,
browser and model runtimes. Do not infer that the old transferred `live_parity.py`
is the new million-record orchestration/evaluation runner.

## Earlier 0.7 bundles

The original0.7 [core archive](../dist/analytics311-0.7.0-core.zip) (504,052 bytes)
and [MCP/geometry archive](../dist/analytics311-0.7.0-cp312-win-amd64-agent.zip)
(30,046,332 bytes) remain unchanged. Their [build receipt](../examples/evidence/build-v0.7.json)
and [archive inventory](../examples/evidence/handoff-bundles-v0.7.json) describe the
preceding source, without r2's two Maps module repairs. R2 rechecked both original
archive hashes and original release manifests; it did not replace them.

## Historical 0.6 and 0.5 releases

Version **0.6.0** is a build-only revision following [static scale reasoning](forecast-v0.6.md), with [119 focused checks](../examples/evidence/test-report-v0.6-focused.json). Core and optional MCP/geometry wheel directories use `release-core-v0.6-build-only` and `release-agent-v0.6-build-only` under `dist/`. They are built from existing dependencies with `--no-network --skip-smoke`; installation, benchmark and stress smokes are deliberately not run for this revision. Their manifests retain `verification.status=not_run`. Do not pass them off as fully qualified transfer releases; the bundler's passed-smoke requirement remains intact.

Built artifacts: [core wheel](../dist/release-core-v0.6-build-only/analytics311-0.6.0-py3-none-any.whl), [agent-profile wheel](../dist/release-agent-v0.6-build-only/analytics311-0.6.0-py3-none-any.whl), [build receipt](../examples/evidence/build-v0.6.json). Each project wheel is 87,668 bytes. Core dependencies plus project total 435,664 bytes; agent-profile wheels total 29,953,406 bytes. All 36 wheel CRCs, metadata/RECORD hashes and manifest checksums were checked; 22 Python files plus five packaged resources match source. The two project wheels have identical uncompressed content; their ZIP metadata differs. Native agent dependencies retain the CPython 3.12 Windows x64 target. No clean installation was performed for 0.6.

To install that historical core, from this project directory into an appropriate Python 3.11+ environment:

```text
python -m pip install --no-index --find-links dist/release-core-v0.6-build-only --find-links dist/release-core-v0.6-build-only/dependencies analytics311==0.6.0
```

The previously verified archives below are **0.5**, preserved unchanged. They do not contain the 0.6 safeguards.

The prepared 0.5 transfer archives are the
[core bundle](../dist/analytics311-0.5.0-core.zip) (498,271 bytes) and
[agent bundle](../dist/analytics311-0.5.0-cp312-win-amd64-agent.zip) (30,040,551 bytes).
Each includes `INSTALL.txt`, verified wheels/receipts, and live-parity,
capacity-replay, bounded reference-benchmark and export stress/recovery tools.
Both releases passed clean offline installation outside the checkout; the agent
release additionally discovered seven MCP tools, checked four valid calls and
one rejected call, and verified native geometry loading. Both also passed the
transferred seven-launch workload and abrupt interpreter-death recovery trial.
Extract before installation. The agent archive targets CPython 3.12 Windows x64.
All archive entries were re-read and checked against exact hashes; archive
integrity is separate from the clean-install evidence for their wheels.
[Archive checksums and contents](../examples/evidence/handoff-bundles-v0.5.json),
[core installation receipt](../examples/evidence/release-core-v0.5.json),
[agent installation receipt](../examples/evidence/release-agent-v0.5.json).
These generated archives remain outside version control.

The current package bundles the default fixture profile, category catalog, index mapping,
fixture manifest and 32 synthetic requests. Python 3.11+ is required. `tzdata` is
a core dependency on every platform, so minimal systems need not supply an OS
timezone database. No model provider, Elasticsearch, Kibana, MCP or geometry
package is needed for fixture CLI queries and CSV export.

Install the wheel with pip, then run from any chosen writable working directory.
The bundled default reads installed resources and writes only to `./runs`.
Explicit `--config` / `ANALYTICS311_CONFIG` profiles keep profile-relative paths.
Custom configurations and their data are not copied into the wheel. Direct
zip-import execution is not a supported deployment; use a normal wheel install.

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install --no-index --find-links RELEASE --find-links RELEASE/dependencies analytics311==0.7.0
.venv/Scripts/python -m analytics311 describe
.venv/Scripts/python -m analytics311 run question.json
```

On Unix use `.venv/bin/python`. `RELEASE` means the directory containing the wheel,
`dependencies/`, `SHA256SUMS` and `release-manifest.json`. The installed
`analytics311` console command is equivalent to `python -m analytics311`.

## Build and reproduce

The builder uses Python's standard library plus installed pip, setuptools>=68 and
wheel. It builds from temporary staging, leaving source files and canonical
assets unchanged. Package assets under `analytics311/assets/` are canonical;
the existing `config/` and `fixtures/` copies remain compatible source-checkout
paths. Deliberate asset updates must update both copies. The builder and tests
reject byte differences before release, and the builder verifies each resource
inside the resulting wheel.

One-time small dependency preparation, requiring network if wheels are uncached:

```powershell
.venv/Scripts/python -m pip download --only-binary=:all: --dest dist/wheelhouse "setuptools>=68" wheel "tzdata>=2025.2"
.venv/Scripts/python -m pip install --no-index --find-links dist/wheelhouse "setuptools>=68" wheel
```

Offline build and verification:

```powershell
.venv/Scripts/python tools/build_release.py --no-network --wheelhouse dist/wheelhouse --output dist/release-core-v0.7-rebuild
.venv/Scripts/python -m unittest discover -s tests -p test_distribution.py -v
```

Output defaults to ignored `dist/release/`. `--output` chooses another directory.
Every output directory must be new, including when rebuilding the same version.
Existing directories are rejected before building. Artifacts, checksums and the
receipt are staged together on the destination filesystem; only the complete
directory is published. Failed verification or copying leaves no partial release
at the requested path. `--wheelhouse` may be
repeated. Without `--no-network`, pip may download missing dependency wheels.
Only the fixed core/MCP/geo requirements are accepted; source builds and model
downloads are excluded. Resolution has a five-minute deadline, a 15-second
per-request timeout, one retry and a monitored 100 MiB staging budget including
incomplete downloads. A subprocess can briefly overshoot between 100 ms checks.
Inherited `PIP_*` settings are cleared, so private indexes, alternate target paths
or constraints cannot silently change this resolution. The explicit arguments
choose dependency sources. The builder does not install missing build tools automatically. `--skip-smoke`
produces an explicitly unverified manifest.

The default smoke creates a fresh temporary venv outside the checkout, installs
the exact wheel using `pip --no-index`, and blocks network socket operations via
a Python audit hook inherited by CLI, MCP and export-worker subprocesses. Only
the standard-library `socket.socketpair()` call is permitted, for asyncio's
internal notification channel. On Windows this function creates a loopback TCP
pair; the exception is scoped to that call, not arbitrary localhost traffic.
Ordinary socket construction and DNS remain blocked and are negatively tested.
This is Python test instrumentation, **not an OS network sandbox**. It confirms:

- import comes from the fresh venv; no source checkout on PYTHONPATH;
- describe and validate succeed using bundled resources;
- installed capacity planning accepts 1,000 fixture rows and labels the result as
  modeled evidence, with production readiness false;
- December Brooklyn noise returns four matches and a two-row preview;
- asynchronous export completes with all four expected request IDs;
- CSV stays under the selected working directory's `runs/`;
- installed resource bytes remain unchanged;
- transferred capacity scenarios replay outside the checkout; the reference
  benchmark executes five cases on 100 generated records; live-parity argument
  parsing works without connecting to a server;
- transferred export stress starts seven owned launch handles, checks exact CSVs
  and changed-working-directory behavior, then verifies abrupt interpreter exit86,
  OS lease release, partial cleanup and successful re-export.

`release-manifest.json` records artifact/resource hashes, selected extras,
install requirement, package version, verification outcome, current Python/OS/
architecture and each wheel's Python/ABI/platform tags. `SHA256SUMS` covers the
project and dependency wheels.
Neither includes machine paths, credentials, raw process logs or source data
beyond the authored bundled fixture. These are local build checks, not signatures
or a claim of bit-for-bit reproducible wheel timestamps. Rebuild after source
changes; the manifest describes the exact wheel it verified.

## MCP and geometry bundles

The default remains a lean **core distribution**. Add `--extras mcp`, `--extras
geo`, or `--extras mcp,geo` to stage all transitive dependencies for those extras.
Preparation on a connected machine with the **same Python version and platform**:

```powershell
.venv/Scripts/python tools/build_release.py --extras mcp,geo --output dist/agent-candidate --wheelhouse dist/wheelhouse
```

Reproduce from those dependency wheels with network access disabled:

```powershell
.venv/Scripts/python tools/build_release.py --extras mcp,geo --no-network --wheelhouse dist/agent-candidate/dependencies --output dist/agent-release
```

Install the complete requested bundle on the matching offline target:

```powershell
python -m pip install --no-index --find-links RELEASE --find-links RELEASE/dependencies "analytics311[mcp,geo]==0.7.0"
python -m analytics311 mcp
```

The MCP smoke starts the installed server over stdio, discovers all seven tools,
calls discovery/validation/analysis/result retrieval and verifies an invalid
operation is rejected. It verifies the four-row fixture result, using the
official SDK client in the same clean environment. This certifies the installed
stdio adapter, not a second independent agent host or agent reasoning quality.
The geo smoke imports the installed native Shapely dependency and checks an
inside/outside synthetic polygon; it does not certify real NTA data enrichment.

MCP/geometry dependencies can contain platform-specific native wheels. The build
manifest distinguishes host architecture from Python's platform: this ARM64
Windows host currently runs x64 Python, so its native dependency wheels target
`win_amd64`, not native ARM64 Python. This is not a universal installer; build
and verify separately on every interpreter/platform target. Pure Python project/core wheels still require a
compatible Python runtime. Python itself, model runtimes/weights, Elasticsearch
and Kibana are not included. Fixture checks do not establish real-data
correctness, server compatibility, capacity or full-project acceptance.

## Reproducible transfer archives

Version 0.4 adds a checked-in bundler; historical 0.3 archives were assembled once.
After a successful release build, create an archive with:

```powershell
.venv/Scripts/python tools/package_bundle.py --release dist/release-core-v0.7 --output dist/analytics311-0.7.0-core-copy.zip
.venv/Scripts/python tools/package_bundle.py --release dist/release-agent-v0.7 --output dist/analytics311-0.7.0-cp312-win-amd64-agent-copy.zip
```

Use the actual fresh release directory selected with `build_release.py --output`.
The bundler requires a passed clean-install receipt, including selected optional
adapter smoke checks and the export stress/recovery smoke. Release manifests pin hashes and sizes for
`tools/live_parity.py`, `tools/capacity_scenarios.py`, `tools/benchmark_fixture.py`, `tools/stress_exports.py` and
`examples/capacity/scenarios.json`. Changes to these files require rebuilding the
release; missing or altered wheels, receipts or handoff files fail closed.
Historical manifests without that inventory must be rebuilt, not silently upgraded.

Only the manifest-listed wheels, those five files, generated `INSTALL.txt`,
release receipt and checksum file enter the archive. Unlisted source files,
configuration, credentials, corpora and runtime output are excluded. An embedded
`BUNDLE-MANIFEST.json` hashes every other entry. The tool hashes and copies files
incrementally, limits inputs to 128 MiB, then re-reads every ZIP entry for CRC and
SHA256 verification before publishing. Existing or racing output files are never
overwritten. Publication requires a destination filesystem supporting hard links
(such as NTFS, APFS or typical Linux filesystems); unsupported filesystems fail
without publishing a partial archive. Use a local supported filesystem and then
copy the completed ZIP to removable/network storage.

Entry order, permissions and timestamps are fixed, so assembling the same exact
release and handoff files twice produces the same ZIP bytes. This does not make
independently rebuilt wheels bit-identical, nor are hashes a digital signature.
The returned JSON includes the archive hash, byte size and entry hashes; save it
as the transfer receipt. Archive verification does not replace the wheel's
clean-install checks or any outstanding real-engine acceptance gates.

The included reference benchmark runs against installed runtime modules and
generates its own bounded corpus; no source checkout or external data is needed:

```powershell
python tools/benchmark_fixture.py --data data/reference-10000.jsonl --output runs/reference-benchmark.json --records 10000 --repeats 3
```

Its timing and Python allocation measurements concern generated input on the
bounded reference backend. They do not estimate Elasticsearch throughput or
million-record capacity. Increase rows explicitly, up to the tool's 100,000-row
limit, on a machine with sufficient resources.

## Historical 0.5 live execution kit

`dist/analytics311-0.5.0-live-kit-r2.zip` adds the real acceptance runner, Compose file, three configuration files and standalone `RUN-LIVE.md` to the exact verified core contents. The final archive is **356,920 bytes / 18 entries**; every CRC, size and SHA256 was independently checked, all eleven original entries are byte-identical and all six additions match current source. [Receipt](../examples/evidence/live-kit-v0.5-r2.json), [runbook](live-runbook.md). The first live kit remains historical; revision 2 corrects the boundary join to use the actual `NTA2020` property against result `nta2020`.

Use `LIVE-KIT-MANIFEST.json` for the full inventory. The unchanged original `BUNDLE-MANIFEST.json` still covers only the original core entries. Extract into a fresh directory, then follow `RUN-LIVE.md`. Python, container images, real data, native geometry dependencies and map/model assets are not included. Packaging verification adds no new target-installation, live-engine or real-million-row evidence.

Resource handling follows Python's
[importlib.resources API](https://docs.python.org/3.11/library/importlib.resources.html)
and setuptools'
[package-data guidance](https://setuptools.pypa.io/en/stable/userguide/datafiles.html).
