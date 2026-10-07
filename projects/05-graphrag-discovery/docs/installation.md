# Install, build, and verify

Python **3.12 or newer**. The application has no third-party runtime dependencies.
The optional package-building tools below are development dependencies. A model server, corpus, or credentials are not needed for the authored demonstration.

## Install a wheel

From a directory containing the release wheel, create an environment:

```text
python -m venv .venv
```

Activate it in the current terminal:

| Shell | Command |
| --- | --- |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows cmd | `.venv\Scripts\activate.bat` |
| macOS/Linux | `source .venv/bin/activate` |

If PowerShell activation is unavailable, substitute `.venv\Scripts\python.exe` for `python` below; no policy change is required.

```text
python -m pip install --no-index --no-deps scads_graphrag_discovery-0.3.2-py3-none-any.whl
python -m graphrag_discovery --help
python -m graphrag_discovery --db example.sqlite3 demo --output example-report
```

The demonstration requires a **new database path** and a new or empty output directory. Inspect `example-report/report.md` and its evidence bundles.
The `graphrag-discovery` console command is equivalent to `python -m graphrag_discovery` in the active environment.
Use absolute database/output paths when launching from another directory; the chosen working directory controls relative output paths.
Bundled fixtures, schemas, and browser assets resolve from the installed package, independently of the working directory. They are read-only.

## Run from the checkout

Change into `projects/05-graphrag-discovery`, then:

```text
python -m unittest discover -s tests -v
python -m graphrag_discovery --db runs/local-demo.sqlite3 demo --output runs/local-demo
```

Frontend state regressions additionally use Node.js 24's built-in test runner:

```text
node --test tests/frontend.test.cjs
```

Node is a development test tool; the installed application needs only Python and a browser.

## Build both distributions

In a dedicated build environment, install the build tools once. This setup can download packages; application installation from the resulting wheel can remain offline.

```text
python -m pip install build "setuptools>=68"
python scripts/build_distribution.py --no-isolation
python scripts/smoke_install.py
```

Run these commands from the project directory. For an isolated build that resolves its own declared build dependencies, omit `--no-isolation`.
The build command uses the standard `build` frontend: create an sdist, then build the wheel **from that sdist**. No custom build backend or asset relocation is required.

Outputs in ignored `dist/`:

| File | Meaning |
| --- | --- |
| `scads_graphrag_discovery-0.3.2-py3-none-any.whl` | Installable Python package with runtime assets |
| `scads_graphrag_discovery-0.3.2.tar.gz` | Source package, build metadata, scripts, docs, tests, and assets |
| `artifacts.json` | Package file sizes/SHA-256 hashes and audited resource hashes |
| `installed-smoke.json` | Local installed-package verification result, interpreter/platform, and demonstration checks |

`smoke_install.py` verifies the wheel hash, creates a fresh temporary venv outside the checkout, removes `PYTHONPATH`/`PYTHONHOME`, and installs with `--no-index --no-deps`.
It checks package imports, bundled resources, the installed console command, and the module command. Its temporary database/environment are removed afterward; the JSON result remains.
For another output directory, use `build_distribution.py --outdir PATH`, then `smoke_install.py --manifest PATH/artifacts.json --report PATH/installed-smoke.json`.

## CI and limits

The repository's project-specific workflow configures Windows, macOS, and Linux with Python 3.12/3.14; project-path filtering avoids unrelated sibling changes.
It runs Python tests and Node 24 frontend state tests, builds both archives, runs the installed smoke check, and retains the artifacts. **A configured matrix is not evidence those jobs have run.** Check actual CI results separately.
Local verification records its own OS and Python version. It establishes package completeness and authored-fixture behavior, not model quality, real-data usefulness, or scale performance.
Builds need their declared tooling available; runtime wheels need no dependency resolution. Hash manifests detect byte changes but are not signed release attestations.
