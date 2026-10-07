# Source-package reproduction check

The source allowlist at the twelve-case checkpoint reconstructed that
mixed-dataset viewer. This was an offline extraction check using the existing
project Python environment, not a clean-device installation or model run.

A fresh temporary source-only ZIP contained 374 source files, 5,091,481 content
bytes and 5,242,111 archive bytes. All member hashes and extracted bytes verified.
The archive intentionally excluded `showcase/dist/` and
`datasets/public-research/imported-statements/`. It preceded this documentation
note and is an ignored smoke artifact, not a new published release.

- Archive SHA256: `5ca5580cce18ec5eb695cf1763b05ba367c76324818c0e2b6cac3ab6758d411c`.
- From the extracted sources, the [statement importer](../scripts/import_public_statements.py)
  regenerated all 173 public dataset files, 1,633,803 bytes, exactly from bundled
  verified raw capture. Full dataset metadata matched; fingerprint:
  `6f73d422781738700473016818d3e3de011f1082b5ba4b4df1b54481e4f72aa5`.
- The extracted [viewer builder](../scripts/build_showcase.py) reproduced all
  283 checkpoint viewer files byte for byte: twelve cases, 3,458,389 content bytes,
  Riverwatch14 default. App, content, source artifacts and package manifest all
  matched, including the failure-only public case without an invented report.
- Viewer manifest SHA256:
  `701d897d145de7de79c79a1221059abca6cac1fb1b3bb13a0734f16bb8a0ab06`.

Nine selected tests ran from the extracted copy and passed, zero skips, 45.188s:
four importer checks (determinism, exact statements, candidate-decision lineage,
actual Workspace reads), three catalog checks (complete metadata chains,
replay/shortening refusal, separate full-source reads), and two failure-view
checks (original preservation/display bounds, required pinned metadata).
The full 32-check viewer suite was not repeated for this extraction check.

Python socket and child-process audit guards were active during packaging,
reconstruction and selected tests; no guarded operation was attempted. Modules
were checked to load from the extracted copy. No downloads, model requests or
dependency installation occurred. The original dataset and viewer were unchanged.

Immutable source-v1 remained unchanged, SHA256
`6d7fe829d4468f901282594f56693a89f2169d94e9a5f2009789578d6130cb27`.
This verifies packaging/reproduction sufficiency, not public analytic acceptance,
model capacity, cross-OS support or a new release.

## Frozen thirteen-case checkpoint before source-v2

A fresh source-only smoke ZIP verified and extracted 387 source files:
5,250,618 content bytes, 5,406,517 archive bytes, SHA256
`25d6c42d035ebaa5291c48fd3ecb3adc23b5ef98a72282ca8ea049cad6b9166d`.
This temporary archive preceded this appended note; it is not the final v2
release. Generated statement data and `showcase/dist/` were absent.

Using only extracted sources and bundled raw capture:

- Regenerated all 173 statement-dataset files, 1,633,803 bytes, exactly. Complete
  dataset metadata matched, including fingerprint
  `6f73d422781738700473016818d3e3de011f1082b5ba4b4df1b54481e4f72aa5`.
- Rebuilt all 288 viewer files byte-identically: thirteen cases, 3,587,122 content
  bytes, Riverwatch14 default. Both public failures retained their originals;
  neither gained an invented report or ledger. App, content, source artifacts
  and manifest matched the frozen generated viewer.
- Viewer manifest SHA256:
  `db15e777b07d36dc32734cd3cd7c96befca06dadbd5d1c6803dcdddc33892682`.
- Verified inclusion of the three public Vulkan JSON records and the
  [separate probe review](../evaluations/public-pilot/context-probe-vulkan-9b-8k-01.review.md),
  whose SHA256 is
  `9565bce67ce9bf66bf777e9a0437d2c364de21a099253fa5f57b68c84a1fe5f8`.
  The ignored probe supervisor and private logs remain excluded, as explicitly
  qualified in [package documentation](package.md).

Twelve selected tests passed from the extracted copy, zero skips, 53.328s:
four importer checks, three catalog checks, four original/pinned/admitted-timeout
failure-view checks, and Vulkan manifest/model-reuse/cache-separation checks.
No full suite was repeated. Python socket and child-process audit guards remained
active; zero guarded operations were attempted. Imports came from the extracted
copy using the existing Python environment. No downloads, model calls or
dependency installation occurred.

The original dataset/viewer and immutable source-v1 were unchanged. The current
allowlist is sufficient for this dataset/viewer reconstruction. This does not
reproduce the excluded GPU supervisor, establish public analytic acceptance or
qualify clean-device installation, GPU capacity, speed or another operating system.
