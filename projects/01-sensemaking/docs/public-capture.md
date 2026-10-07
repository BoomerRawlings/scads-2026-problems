# Bounded public-source capture

This milestone captures source evidence. It does not import an analysis corpus,
infer relationships, evaluate a model, or establish source truth.

Run with Python 3.11+ from this project directory:

```powershell
python scripts/capture_public_data.py
python scripts/capture_public_data.py --capture
python scripts/capture_public_data.py --verify
```

Default output: `datasets/public-research/`. `--output-dir` selects another
capture directory. Sources are fixed in the script: eight ROR records from the
NCI neighborhood and four Wikidata revisions covering NCI, NIH, CERN, and the
NIH-list identity negative. No source-provided links or media are followed.

`raw/` retains the exact JSON response bytes. `capture-manifest.json` records
the selection plan, source URL, UTC retrieval time, returned revision metadata,
SHA256, byte count, request attempts, acquisition policy and completeness.
ROR records are captured live and then frozen; their modification dates are
not a release identifier or real-world validity date. Wikidata revisions are
requested and checked exactly. This collection is not an atomic database
snapshot. Rights and identity caveats remain in [public-data.md](public-data.md).

**Bounds:** sequential requests, starts at least one second apart; three
attempts/source; 20-second socket timeout; 180-second run budget checked between
I/O operations; 30-second maximum retry wait; 2 MiB/source and 8 MiB received/run.
A blocking I/O operation can extend the run budget by its socket timeout.
`Retry-After` is honored; a wait beyond budget stops acquisition instead of
retrying early. Redirects are rejected. The identifying User-Agent points to
the project owner's public website. No credentials or raw HTTP logs are saved.

**Resume:** successful records are checkpointed individually. Rerunning verifies
their hashes, URLs and revisions before requesting missing records. Existing
raw files are never overwritten. Corrupt files or files without manifest
provenance stop the run; retain them for inspection and use a new output
directory for a fresh capture. A complete rerun performs no network requests.

The official limits were rechecked on 2026-10-06: ROR documents
2,000 requests/5 minutes/IP, with client-ID registration currently paused;
Wikimedia's 2026 general policy lists 200 requests/minute for an identified
unauthenticated client. This capture stays below those rates and respects
service responses. [ROR REST](https://ror.readme.io/docs/rest-api),
[ROR client-ID notice](https://ror.readme.io/docs/client-id),
[Wikimedia limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits).

Offline tests cover partial failure/resume, immutable evidence, corrupted
hashes, pinned-revision rejection, rate-limit waits, retry/byte budgets and
unapproved source/redirect rejection. Actual capture counts and bytes are in
the acquisition manifest; remote database sizes are not processed dataset size.

## Captured milestone

The saved collection contains **12 records: 8 ROR + 4 Wikidata**,
**595,488 raw bytes**. Acquisition ran from `2026-10-07T04:14:03Z` through
`2026-10-07T04:14:14Z`, with 12 request attempts and no retries or blockers.
All hashes and pinned revisions pass offline verification. A completed resume
was also checked with networking disabled and left the manifest unchanged.
Eight focused offline tests passed. The subsequent [offline import](public-import.md)
is verified through Workspace and real MCP calls. Public model evaluation and
the larger acquisition case remain separate, unfinished milestones.
