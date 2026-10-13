# Capture with limited local disk

`tools/capture_compressed.py` is an optional capture transport for a machine that
can fetch pages but cannot store a SQLite payload copy plus raw JSONL. It writes
one gzip member per source page and a metadata-only SQLite checkpoint, then joins
those members into one standard concatenated gzip. It never starts Elasticsearch,
Kibana, normalization or model inference. No million-record run of this fallback
is implied by its tests.

```sh
python tools/capture_compressed.py --start 2025-04-01 --end 2025-11-01 \
  --output data/nyc311-apr-oct-2025.jsonl.gz --page-size 1000 \
  --max-rows 3000000 --max-bytes 3000000000 --max-pages 10000 \
  --max-seconds 14400 --request-timeout-seconds 120

python tools/capture_compressed.py --status --output data/nyc311-apr-oct-2025.jsonl.gz
```

Run the same capture command to resume an initialized checkpoint. An interruption
before initial checkpoint creation may leave an empty directory/database; retain
it and select a fresh output path. The checkpoint binds source ID, selected
fields, date window and sort order. Each committed chunk records compressed and
raw hashes, bytes, row count and cursor chain. Resume rereads every committed
chunk with one-record decompression buffers, checks all totals and rechecks source
metadata/count/revisions before fetching more pages. The entire response is
limited to 16 MiB and 1,000 records; one source page is held in memory. Invocation
time, request timeout/retries, rows, raw bytes and page operations are bounded.
Shell continuations above use POSIX `\`; in PowerShell, put each command on one
line or use PowerShell's backtick continuation.

Capture reserves **at least 1,000,000,000 bytes free**, plus the space still needed
for the final gzip. Compressed chunks, final gzip and checkpoint are capped at
**500,000,000 bytes**; `--max-storage-bytes` may reduce that ceiling. The guard runs
before and after page conversion and throughout publication. Resource exhaustion
pauses capture; it does not discard records or qualify an incomplete capture.
Compression ratio is data-dependent, so these limits do not promise that every
window will fit. Other applications can reduce free space between guard checks.

Strict decimal-text `unique_key ASC` ordering establishes uniqueness across pages.
Every page must match the initial provider revision. Final count, distinct count,
maximum row update, metadata and replica/truth revision must match the initial
observations. Source drift or chunk corruption quarantines capture. The final
artifact is published only after the full raw hash/count/cursor chain is rechecked.
This is still an observed enumeration, not a transactional snapshot or complete
city reporting. `coverage.complete` remains false; the existing separate observed
comparison qualification and official-boundary requirements remain in force.

Crash recovery preserves full uncommitted chunks only after verifying their
checkpointed intent. Truncated owned page files are retained, charged against the
storage ceiling and replaced by a new filename. A partial final gzip resumes only
after its exact prefix matches the committed chunks. Unknown files, links,
conflicting artifacts and foreign publication prefixes are never overwritten.
Chunks/checkpoint remain after completion for audit/resume; no automatic deletion.
Publication requires hard-link support on the selected filesystem (NTFS/ext4 are
appropriate). No cross-filesystem move is required.

## Transfer and normalization

Transfer the completed `.jsonl.gz` and adjacent `.manifest.json` to the capable
host. In the manifest, top-level **`sha256` and `bytes` describe decompressed
canonical JSONL**. `transport.sha256`, `transport.bytes` and `transport.file`
describe the gzip artifact. Verify both identities; do not pass gzip directly to
the current JSONL normalizer. Decompress into a fresh `.jsonl` file, preserve the
same adjacent manifest, then use `tools/run_real_acceptance.py --raw ...` normally.

This bounded streaming example refuses existing output and checks both hashes and
byte counts. Run on the capable host with disk space for the raw corpus:

```python
import gzip, hashlib, json, shutil
from pathlib import Path

compressed = Path("data/nyc311-apr-oct-2025.jsonl.gz")
raw = compressed.with_suffix("")
manifest = json.loads(raw.with_suffix(".manifest.json").read_text())
def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
def require(condition, message):
    if not condition:
        raise ValueError(message)
require(compressed.stat().st_size == manifest["transport"]["bytes"], "gzip size mismatch")
require(digest(compressed) == manifest["transport"]["sha256"], "gzip hash mismatch")
require(shutil.disk_usage(raw.parent).free >= manifest["bytes"] + 2_000_000_000,
        "insufficient space for raw JSONL and 2 GB reserve")
sha, total = hashlib.sha256(), 0
with gzip.open(compressed, "rb") as source, raw.open("xb") as target:
    for block in iter(lambda: source.read(1024 * 1024), b""):
        total += len(block)
        if total > manifest["bytes"]:
            raise ValueError("decompressed size exceeds manifest")
        sha.update(block)
        target.write(block)
require(total == manifest["bytes"] and sha.hexdigest() == manifest["sha256"],
        "raw JSONL size or hash mismatch")
```

If decompression fails, retain the partial raw file for diagnosis and select a
fresh destination. Do not normalize an unverified partial artifact.
Successful decompression establishes artifact identity only. Lossless normalization,
official NTA enrichment, immutable index/count reconciliation and independent live
checks remain required; capture does not qualify population coverage or performance.
