# Saved-case showcase

Static, read-only viewer for Project 1. Plain HTML/CSS/JavaScript; no packages,
external assets, live model calls, tracking, backend API or deployment.

From `projects/01-sensemaking`:

The selected public failures require the reproducible statement dataset. If
`datasets/public-research/imported-statements/` is absent, first run
`.\.venv\Scripts\python.exe scripts/import_public_statements.py --import-data`.
This reads the bundled verified capture offline and refuses to overwrite an
existing output. Source-only packages exclude this generated dataset.

```powershell
.\.venv\Scripts\python.exe scripts/build_showcase.py
.\.venv\Scripts\python.exe -m http.server 18573 --bind 127.0.0.1 --directory showcase/dist
```

Open `http://127.0.0.1:18573`. Use HTTP: `file://` cannot load the JSON package.
On macOS/Linux use `.venv/bin/python`. Any Python 3.11+ interpreter also works;
the builder and server use only the standard library plus the project's existing
stdlib `Workspace` module.

`dist/` is the portable website integration artifact. It can be served at a
subdirectory: all packaged assets and artifacts use relative links. The existing
boomerrawlings.com site has not been changed or deployed. Its EAD Implementation
display supplies the process pattern: prompt → problem → decision → validation
→ artifact. This viewer is one project surface, not the finished portfolio.

## Included cases

Thirteen selected saved cases: eleven report/clarification cases and two execution failures.

- Riverwatch14/Qwen3.5-9B Q3_K_M: default, free-local demonstration passed separate
  AI source/pixel review for one known synthetic case. Four supported findings
  retain dated readiness claims, the supplier path and planned/no-receipt limits.
  Shipping-date versus expected-arrival wording and minor image-color shorthand
  remain disclosed in the original review; broader validation is pending.
- CBRI: historical Codex demonstration; separate AI source/pixel review
  passed. Exact historical model/request not recorded. Does not establish a free runtime.
- Delta/Codex: historical clarification; no evidence investigation.
- Delta/local: guarded clarification accepted; prose limitations retained.
- Riverwatch07/local: runtime accepted, separate AI source review rejected.
- ClearAir03/Qwen3.5: runtime accepted, separate AI source review rejected.
- Riverwatch08/Qwen3.5: complete recorded coverage and correct pixel readings;
  still rejected for a false missing-video claim and omitted media limitations.
- Riverwatch10/Qwen3.5: isolated pixel observations and fixed provenance improve
  consistency; rejected because its summary overstates disputed readiness and
  misdescribes inspected image/video evidence as text. Original isolated outputs
  and the detailed source review are included.
- Riverwatch11/Qwen3.5: compact report input preserves source coverage, accurate
  media provenance and shipping qualifications. Rejected because the summary
  still treats unresolved ready/delayed claims as an established delayed state.
- Riverwatch12/Qwen3.5: the host-constructed overview preserves unresolved source
  differences. Rejected because model-authored finding 1 still adopts delayed
  readiness as settled; construction and model authorship are labeled separately.
- Riverwatch13/Qwen3.5-9B Q3_K_M: readiness is accurately source-attributed, but
  "only a procedural delay" adds unsupported exclusivity. The supplier path and
  explicit planned/no-receipt qualification remain incomplete. No delivery is
  invented; original observations and minor image-color shorthand are preserved.
- Public NCI01/Qwen3.5-9B: context admission stopped the run before an analytic
  report. Nine MCP calls include five successful full-record reads and one failed
  catalog continuation. Original failure, reviewed metadata, trace and execution
  review are preserved. No report, final citation ledger or analytic acceptance
  is implied by displaying this failure.
- Public NCI02/Qwen3.5-4B: report generation timed out after context admission
  succeeded. Twelve successful MCP calls included eight full-record reads.
  No report, rejected report candidate or final ledger was saved. This differs
  from NCI01's context overflow and establishes no public analytic acceptance.

One free-local analytic demonstration passed separate AI review; broader analytic
validation remains pending. The eleven report/clarification cases use synthetic
data; both public failures use captured ROR/Wikidata source units. No public
analytic case is accepted by this UI change. Riverwatch14 remains the default.
Separate AI review is not human labeling, held-out accuracy or evidence of time
savings. Recorded durations describe individual development runs on a busy host.
The ordered trace contains actual calls, not complete historical response payloads;
the viewer does not re-execute them or reconstruct sampled video frames.

## Inspect and extend

`cases.json` explicitly selects examples, their `dataset_id` and review/engine status.
To add a later case, preserve its original artifacts in `examples/<id>/`, add a
review-backed case definition, and rebuild. Update the project status only when
the accepted evidence supports that change. Never infer success from a report's
`status=complete` alone. Historical prompts are not reconstructed from current
templates; local questions are selected from saved metadata.

An execution failure uses `artifact_kind: failure`, an ID beginning `public-`,
and exactly `evaluations/public-pilot/<id>/` for artifacts/review. Arbitrary
artifact-root configuration is refused. Required files are `failure.json`,
`tool-trace.json`, `run-metadata.json` and `REVIEW.md`; the presence of a final
report or ledger refuses failure-only presentation. Failure cases remain limited,
not accepted or semantically rejected reports. The viewer creates no missing
report or ledger object and keeps the runtime error separate from analytic claims.

The builder admits exactly two dataset bindings: `cedar-basin-synthetic-v1` at
`data/`, and `public-research-statement-pilot` at
`datasets/public-research/imported-statements/`. Only datasets actually selected
by cases are read and copied. Evidence maps are separate per dataset, so reused
source IDs cannot silently resolve to another case's source. New cases must have
saved metadata whose dataset ID, kind, aggregate fingerprint and complete file-hash
map match the packaged dataset. The two older Codex cases (`cbri` and
`ambiguous-delta`) did not save this fingerprint; their explicit synthetic binding
and any ledger hashes are checked, and this limitation is displayed. This exception
is unavailable to new cases or public datasets.

For a selected public case, the builder checks the fixed captured source IDs,
URLs, revisions, lengths and hashes offline, then reproduces all statement-projection
files and requires byte identity. Only this exact file set is copied, including
raw source JSON, capture/import manifests and projection decisions. Arbitrary
extra files and linked media are excluded. Capture dates/registry edits are not
relationship validity; identity candidates remain candidates. These qualifications
are displayed per case. Packaging preserves source claims, not verified current
truth or a public analytic acceptance result. Public data must first be reproduced
using the [statement importer](../docs/public-statements.md) if absent.

The builder copies named report/trace/ledger/review files, the selected dataset
and a small explicit document allowlist. Report JSON/Markdown and traces remain
byte-exact. Their relative dataset links resolve within the packaged artifact tree. Downloads
retain their relative references; preserve the package tree to keep those links.
Report-case run metadata is **not** copied wholesale: a file named `published-run-summary.json`
contains only selected scalar fields and, when present, an explicit sanitized
grounded-media lineage, compact-synthesis metrics or evidence-summary construction
extract. No `runs/`, virtual environment, global
Codex state, private reasoning, raw runtime logs, secrets or model weights enter
the package. Known machine-specific path patterns cause build refusal.

For the explicitly reviewed failure case, the original metadata download is
copied byte for byte only when it matches the case's pinned `metadata_sha256`;
the complete file also passes bounded/path-scanned reading. This is a deliberate
original-artifact exception, not a general raw-log allowance. On-screen failure
context uses a separate bounded allowlist of counts, limits, flags and hashes.
Prompt text, token arrays, source bodies and private reasoning are not extracted
into that display. Recorded retrieved IDs must match successful full-read trace
arguments and the bound dataset. They remain retrieval bookkeeping, never a
substitute for the nonexistent final citation ledger. Source dialogs repeat this
qualification. Recorded overflow arithmetic is checked for consistency; no source
truth or model-capacity claim follows from it.

For grounded-media cases, only successful `media-observation-NN.json` outputs are
copied, byte for byte. Packaging verifies their output SHA256, unique successful
MCP `read_media` call/evidence linkage, recorded source/locator order, strict JSON
shape (including duplicate-key refusal), complete successful-media-call coverage,
and exact ordered reuse in the final report. Metadata includes only the selected
call, source, locator, filename and fingerprint fields; failed outputs, request
bodies, private reasoning and image encodings are excluded. Input SHA256 values
are recorded fingerprints, not independently reconstructed by the builder.

The viewer discloses that isolated pixel observations were fixed into the report
and provenance limitations came from the host; findings remain agent-authored.
It does not rederive host limitations or judge observation truth. Separate source
review remains necessary. Grounded cases include the reviewed Riverwatch14 default
and preserved rejected attempts. A known-fixture pass does not establish general
free-local analytic reliability.

Optional compact-synthesis disclosure exposes only an allowlisted construction
policy, generation/action number, canonical-message byte count/hash and numeric
counts. Input hashes and counts are **recorded**, not reconstructed or independently
verified. The hash covers canonical report messages, excluding the response schema,
generation settings and complete HTTP request. Source bodies, lineage arrays,
raw context, settings, image encodings and private reasoning are not copied into
this metadata summary. Compact report input retains exact retrieved records once,
keeps differing versions/identity/graph/errors, and uses isolated observations
instead of raw pixels; the planner still received any returned pixels. This is a
construction distinction, not evidence of better model accuracy. Riverwatch11
uses compact synthesis and remains rejected by its separate source review.

Evidence-summary mode has a separate attribution: for complete reports, the host
constructs the summary from supplied assertion fields in actual retrieved records
and recorded graph/inventory scope. The viewer labels that summary as host-authored;
findings and conflicts remain model-authored. Packaging checks the final summary's
UTF-8 byte count and SHA256 against its recorded construction and requires the
corresponding constrained field. It publishes only the policy, generation/action,
attribution, hash/byte count and numeric assertion/record counts. These counts
cover records admitted by the host's scope rules; excluded retrieved records
remain available to the analyst model. Source/scope lineage, candidate groups
and raw context are excluded from the metadata extract. Counts are recorded,
not independently reconstructed. Matching bytes do not establish
that supplied assertions are true or that all prose disagreements were detected.
Earlier complete-summary attempts never relabel a final clarification or
insufficient-evidence summary as host-authored.

Source reads check every existing path component before resolution, rejecting
symlinks and Windows junctions even when their targets remain inside the project.
Reads are bounded to 25 MiB plus one detection byte. Dataset CSV, graph, manifest,
descriptor and every manifest-listed text/media file are preflighted before
`Workspace` is constructed; accumulated package content is capped at 32 MiB.

Companion source documents are preserved verbatim, including some links to
repository-only runtime instructions, previous reviews and evaluation artifacts.
Those files are not all included in this small viewer package. The viewer states
this limitation; `document-link-audit.json` identifies every unavailable Markdown
target. Direct report/source/media links are separately checked and resolve.

`package-manifest.json` records every packaged file's SHA256. A fresh build refuses
an existing destination. For an unchanged package owned by this builder:

```powershell
.\.venv\Scripts\python.exe scripts/build_showcase.py --refresh
```

Refresh first checks ownership, the exact file inventory and old hashes. It
walks destination ancestors and inventory entries before writing, rejecting
symlinks and Windows junctions. It refuses foreign files, edited outputs and removal of prior artifacts;
use `--output-dir showcase/dist-next` for a fresh destination in those cases.
No files or directories are deleted. A write interruption can leave a partial
output; use a fresh directory rather than overriding integrity failures.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s showcase -p test_showcase.py -v
node --check showcase/app.js
```

Thirty-two checks cover unchanged original artifacts, review-status separation, source
hashes, portable Markdown/media links, attributed prompt excerpts, the publishing
allowlist, deterministic refresh, path escape and foreign/edited file protection.
The suite contains 34 checks. The preceding twelve-case version passed all 32
then-existing checks, zero skips, in 454.818s. Six relevant checks, including two
new admitted-context timeout cases, passed in 23.428s after NCI02 was added;
the full expanded suite was not repeated. Browser verification is recorded
separately in `QA.md`; test duration is not a model-runtime or scaling benchmark.
They include physical oversized CSV/manifest/text inputs refused before Workspace
construction, cumulative size refusal, and three real Windows junction regressions:
source ancestors/root, destination ancestors/root, and a link inside an owned
output. Junction tests skip off Windows or if junction creation is unavailable;
all three executed successfully on the recorded Windows run. Tests remove only
their own junctions after verifying their resolved targets remain in the fresh
test directory. The builder itself deletes nothing.
Three focused scripted checks cover grounded output lineage/hashes, exact report
reuse, malformed/reordered artifact refusal and metadata filtering; they do not
represent an actual model run or analytic acceptance.
Two additional scripted checks cover compact metadata filtering, explicit hash
scope/metric validation and refusal without verified grounded artifacts.
Three further checks cover host-overview attribution, exact final-summary hash/byte validation, published metadata allowlists and prior-complete versus final-abstention handling.
Six additional checks cover explicit historical bindings, same-ID separation across
synthetic/public datasets, saved fingerprint/identity refusal, path escapes,
exact public reproduction/tampering and the narrow historical-fingerprint exception.
Mixed-dataset reports in these tests are scripted packaging fixtures, not actual
model outputs or accepted public analyses. The public source files are reproduced
from the captured raw inputs in fresh temporary directories; tests do not depend
on a pre-generated statement dataset.
Two follow-up checks bind each dataset's protocol link to its explicitly copied
source document and restrict the saved retrieval-profile extract to `legacy` or
`catalog`. The Implementation tab distinguishes the six server tools from the
local catalog profile's five enabled tool types; raw pixel reads are disabled there.
Successful catalog/full-record read call counts come from the original trace,
not metadata source bodies or a reconstruction of cursor-chain completeness.
General context-admission histories and coverage/source bodies remain outside the
display allowlist; the failure view exposes only its bounded final-preflight
measurements. The public protocol link appears only for the selected public
dataset; synthetic cases retain their local-pilot protocol.
Five failure checks cover absent report/ledger preservation, refusal to hide an
existing report/ledger, required pinned metadata, artifact path boundaries,
dataset identity and consistent recorded counts/overflow. These source tests do
not establish public analytic acceptance or browser rendering quality.
Two further checks cover the preserved NCI02 report timeout and a generic scripted
timeout after admitted context, retaining source bookkeeping and display bounds
without creating an analytic result.
These are packaging/content checks, not browser rendering or accessibility audits.
Manual/browser QA should cover all four tabs, case switching, source dialog
open/close, image/video links, narrow screens, keyboard focus and artifact downloads.
The earlier eleven-case browser pass verified the Riverwatch14 default, visible
authorship/review qualifications, initially collapsed construction details and
host overview, exact overview text when expanded, authentic prompt excerpts,
dataset/protocol disclosure and Delta's visible model-authored summary. At
390×844, the expanded view remained within the viewport with no console
warnings/errors. The twelve-case browser pass additionally verified failure-only
tabs and context counts, original call arguments, qualified public source links,
public protocol/fingerprint, scaling-plan link, narrow-screen layout and normal
labels restored on case switching. No public analytic acceptance is implied.
See [the QA record](QA.md) for scope and historical checks.
Both this README and QA record are copied unchanged into the static bundle's
explicit documentation allowlist. Documentation-only refreshes do not imply a
new browser check.
No PDF was generated.
