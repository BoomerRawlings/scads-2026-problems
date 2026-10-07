# Independent core and corpus audit

Reviewed 6 October 2026 by a separate implementation agent. Scope: `schema.py`, `review.py`, `release.py`, `catalog.py`, `workspace.py`, CLI and local HTTP/UI review behavior. Core modules were not edited by this reviewer. Findings below distinguish reproduced defects from fixes independently rechecked.

## Reproduced findings

| Priority | Finding | Status |
| --- | --- | --- |
| P1 | Withdrawal leaves revoked tokens in FTS5 shadow storage despite zero visible results/history purge | **Fix independently verified**: shadow blocks and file bytes exclude withdrawn marker |
| P1 | Accepting a displayed corrected value silently restores original extraction value | **Fix independently verified**: executed actual UI JavaScript; correction retained in submission |
| P2 | Stale correction is displayed as current data after extraction changes | **Fix independently verified**: actual UI JavaScript displays current raw candidate, excludes stale correction |
| P2 | Concurrent reviews can silently replace another review using the same extraction fingerprint | **Fix independently verified**: stale event token rejected; explicit current token succeeds |
| P2 | Malformed bundle scalar fields produce uncaught TypeError/OverflowError | **Fix independently verified**: all three malformed fields return ValueError |
| P1 | Ingestion ignores manifest byte hash and associates original rights with changed bytes | Reproduced, then **fix independently verified** |
| P1 | Manifest candidate status ignored because loader checked `status`, not `admission_status` | **Fix independently verified**: candidates skipped before parser; hash/size mismatch rejected |

Verification: `python -m pytest tests/test_interfaces.py tests/test_lifecycle.py tests/test_search.py -q` passed **75 tests** after the concurrency and model-category changes. Additional isolated executions checked review compare-and-swap, corrected reapproval, document-only retrieval, and SQL traces beginning with `BEGIN` for both catalog information and search. A Node VM executed the actual `vopt/web/app.js` with a minimal DOM/API harness: corrected value 25000 remained displayed and submitted when Accept was clicked; stale corrections displayed raw value 30000 and were not submitted. This is behavior verification, not visual browser inspection. Descriptions below preserve the original reproduced defect, followed by correction status.

### 1. Revoked FTS tokens remain recoverable

Reproduction:

1. Create the existing lifecycle fixture bundle, setting its document title to a distinctive lowercase single token, `uniquewithdrawnsentinel583791`.
2. Import sequence 1 into a new catalog.
3. Import sequence 2 with empty documents/assertions and policy version 2 revoking `d1`.
4. Visible document and assertion counts become zero; obsolete history disappears.
5. Read `SELECT block FROM search_fts_data` or scan the SQLite file bytes.

Observed: the distinctive token remains in both FTS5 live-segment/tombstone blocks, along with the former numeric token `30000`. Ordinary `PRAGMA secure_delete=ON` does not purge FTS5's internal retained segments. Search invisibility is insufficient for an offline catalog intended to remove withdrawn values/content.

Recommended correction: rebuild FTS5 by dropping/recreating the virtual table inside the existing import transaction, with secure deletion enabled, or use the supported FTS5-specific secure-delete mechanism and verify its exact behavior. Test shadow data and bytes after document revocation and values-to-coverage downgrade. This does not promise erasure of independently copied files or storage-device history.

Verified correction: transactional FTS drop/recreate; the distinctive marker and former numeric token are absent from shadow data, and the marker is absent from the database bytes after withdrawal. Existing rollback/atomicity/profile-downgrade tests pass.

### 2. Corrected display / Accept action mismatch

Actual `ReviewStore` sequence:

```text
original value = 30000
decide(correct, correction={value:25000}) -> approved value = 25000
decide(accept, no correction)            -> approved value = 30000
```

`web/app.js` displays `current={...assertion,...event.correction}` but the Accept button sends no correction. Thus a reviewer looking at 25000 can silently approve/release 30000. Preserve the displayed effective correction when accepting, or make the action explicitly revert to the original and show that value before confirmation. Do not conflate accepting the original candidate with re-approving an already corrected candidate.

The same merge occurs even when `review_status === "stale"`. A changed extraction can therefore display an obsolete previous correction while its current source evidence/fingerprint belongs to new extraction. Treat stale correction as historical context, clearly separate from current candidate data.

Verified correction: only current `correct` status overlays candidate fields. Accept on an already corrected candidate submits `decision: correct` and the current correction; stale candidates do not inherit that overlay. The review event token is forwarded.

### 3. Review-to-review concurrency

With unchanged extraction fingerprint `F`:

```text
reviewer A: decide(reject, expected_fingerprint=F)
reviewer B, old view: decide(accept, expected_fingerprint=F)
current status -> accept
```

Both writes succeed; the append-only audit preserves events but the stale review intent is not detected. The fingerprint protects extraction revision only. A second compare-and-swap token (latest assertion event ID or review revision), checked in the insertion transaction, can prevent silent overwrites by independently loaded UI tabs. Alternatively document deliberate last-writer-wins behavior and expose the intervening decision before overwriting; that behavior is weaker than conflict-aware review.

CLI `review` additionally substitutes the current fingerprint when `--fingerprint` is omitted. This is convenient for fresh scripted decisions but must not be presented as stale-view protection; require an explicit fingerprint for a review based on previously displayed evidence.

Verified correction: `ReviewStore.decide` requires the expected latest assertion event ID inside `BEGIN IMMEDIATE`; zero is valid only for the first event. A second decision with zero fails without inserting. The UI/API carries the event token, and CLI `--fingerprint` is now required. A supplied current event token deliberately replaces the prior decision while preserving the audit.

### 4. Invalid bundle types

On a valid fixture bundle, replace one assertion field, reseal, and call `validate_bundle`:

```text
doc_id=[]       -> TypeError: unhashable type: 'list'
attribute=[]    -> TypeError: unhashable type: 'list'
value=10**400   -> OverflowError: int too large to convert to float
```

The CLI exception handler did not catch these types. Reject malformed scalar types before dictionary membership, and handle oversized finite-integer checks without float overflow. Keep invalid imports atomic and return normal validation errors, not tracebacks/request disconnects.

Verified correction: identifiers/attribute strings are checked before dictionary membership, and numeric bounds precede conversion-dependent finiteness checks. All reproductions now raise `ValueError`.

### 5. Source identity and admission

Actual reproduction used the downloaded Homelite PDF with its manifest SHA replaced by 64 zeroes. `Workspace.ingest_manifest(max_pages=1)` originally succeeded and stored the actual SHA `0f5b91e0f637231687478997fc3eaddc8398b8041616af8891977e76bbc9cf54`, silently disregarding the supplied pin. After the root fix, the identical input raised `ValueError: Source hash mismatch: tm9-1752-homelite-1942` before ingestion. **Fix verified.** Byte-count guard remains a separate check.

The original loader defaulted `entry.get("status", "admitted")`; the real manifest uses `admission_status`. Two rights candidates would therefore be processed. Current code reads `admission_status` first. The corpus additionally uses unsupported rights basis `unverified-government-publication` for those candidates, providing an independent export guard if admission is bypassed.

Candidate admission, SHA mismatch and byte-count mismatch regression checks pass before the PDF parser is called.

## Additional functional limit, corrected

Originally `search.build_index` iterated only declared models, omitting documents with empty model lists. The genuine hand-tool control intentionally has no invented product model. Verified correction: document-only entries now use an empty model scope. A released hand-tool fixture with no assertions/models was retrieved by title/category and returned `model: ""`. Empty extraction still does not establish absence of a fact.

## Corpus fit and evaluation validity

- Four admitted powered-equipment manuals: 497 authentic scanned pages with embedded OCR. Generator, compressor, welder and charger content supplies real numeric technical attributes.
- One admitted 119-page hand-tool control, not a powered-tool coverage success.
- Two downloaded candidates: 253 pages of pump/asphalt-kettle material. Official government covers and absence of detected notices do **not** establish rights to OEM-style inserted pages. They remain unadmitted until authorship/rights are resolved.
- TM 9-617 and TM 9-618 share text and structure. They belong to one evaluation family. The four powered manuals represent three development groups, not four independent held-out families.
- All acquired manuals were inspected during development. Twenty source leads are labeled agent-source-reviewed; none is human gold, untouched test data, or automatic release authorization.
- Heavy historic machinery is a useful technical proxy, but does not establish broad handheld-tool/household-appliance, overseas-language or modern-manual coverage.
- Numeric facts carry semantic traps: generator output versus input voltage; assembly versus subcomponent identity; brake horsepower versus electric input watts; nominal battery voltage versus charger output; engine versus compressor rpm; operating versus crated mass; multiple fluid capacities and amended editions.

Source manifests, hashed rights snapshots, rendered evidence and reproduction commands: `data/corpus-research.md`. Acquisition verification passed for all five admitted files. Default acquisition fetches admitted records only and is separate from offline runtime.

## Exhaustive M18 candidate audit: original development version

All **17 emitted candidates** were independently checked against rendered source pages 12, 18, 20, 37, 43, 53 and 133. No candidate was sampled out. Frozen record fingerprint: `95004745f4b71004d335738bb9c842d74f42800561bd373d864a26338f3bd77d`; processing version: `vopt-ingest-2:277774255b62a86ea95a`. Every original candidate, per-candidate decision, source image/hash and rubric is retained in `data/corpus/m18-candidate-audit-v1.json`.

| Check | Result |
| --- | --- |
| Numeric value/unit appears in the source | 17/17 |
| Model/component and essential conditions sufficiently preserved | **5/17 (29.4%)** |
| Missing configuration, operating mode or diagnostic condition | 9/17 |
| Definite wrong entity | 3/17 |
| Supported observations that duplicate another supported observation | 2/5 |

The five supported observations represent three distinct claims: dry assembly weight, rated output power and output frequency. Dotted leaders/value text in the raw dry-weight condition still needs presentation cleanup. The two voltage observations require the 125 V **or** 250 V configuration distinction. The speed observations mix warm-up, normal engine speed, idling before stopping, critical cranking and governor-disconnected troubleshooting. One frequency condition is an incomplete instrument-description fragment.

Definite errors: PDF page 53's 945 lb refers to the Hercules **WXLC-3 engine with accessories**, not the M18 assembly. Page 133's 169,000 lb and 132,000 lb belong to a **railroad-car transport example**, not the generator. The arithmetic conversions are correct; source association is wrong. Numeric transcription accuracy therefore substantially overstates usable claim accuracy.

This is an agent's exhaustive candidate-precision audit of one development version, with a rubric applied after inspecting the candidates. It is neither human gold nor a held-out/generalization result, and gives no recall estimate. Parser repairs must receive a separate versioned audit; retain this original result. Selected source-reviewed development releases must not be presented as raw extraction performance.

### Post-fix audit, separately preserved

Final extractor `layout-rules-2:220e080a269d5e2c4495` emits seven M18 candidates, all on PDF page 12. All **7/7** preserve the inspected source claim: dry assembly weight and power/frequency/voltage separately associated with the explicitly stated 125 V or 250 V configurations. Ten former procedural, component or transport-example observations are no longer emitted. Original evidence remains in v1; every surviving assertion and the new review fingerprint (`827a83cd2a5c3d8850eba13f407331343ce1ef9f4fc6ccc3f63f23513718d67e`) are retained in `data/corpus/m18-candidate-audit-v2.json`.

This checks repair behavior on the same source used to identify defects. **7/7 is not held-out accuracy**, and conservative removal does not establish recall. The document remains marked partially processed because unrelated decoder-error pages were downgraded; its approved source page is successful.

### Actual agent-reviewed development release

`examples/agent-review-decisions.json` pins 14 exact candidates across all five admitted document records. The selected values were compared with inspected PDF pixels; source/candidate/record/image hashes bind the decisions. M18 power and frequency are reviewed as model-level invariants because both documented voltage configurations explicitly share them; voltage alternatives remain pending. The workshop compressor's ambiguous OCR `11/2` is corrected to the visually confirmed mixed number 1.5 hp with its driving-engine role preserved.

`scripts/prepare_development_release.py --workspace runs/real-workspace --apply` generated `runs/development-{coverage,values}.json` and their SQLite catalogs: **five documents, 14 observations, seven pending candidates**. Three inspected leads (Curtis engine horsepower, Chrysler engine horsepower, Onan output power) have no corresponding candidate and remain missing. No new assertion was fabricated.

Verified: all 14 persistent review events have `actor_kind: agent`; repeat application creates zero events and identical bundle integrity; default publication rejects the unfinished reviews. Both public bundles pass the strict schema, contain no private source/evidence/path fields or original evidence paragraphs, and match their catalog integrity. Authored temporary-fixture checks also verify stale-extraction refusal. Exact review replay requires the preserved private records and evidence images; the public bundles operate independently.

Release integrity: coverage `08e7d91a5c2d8bbaae600512475453b8f261390a9f697d2449ee213ce839874d`; values `0b6023277987429fb11b57058bd6ffe34a5f17ceed1332f854957f134bcc390f`. These are selected, corrected development catalogs. They are neither human gold nor raw extraction accuracy evidence.

## Native worker and source-binding audit

An independent retrieval/packaging agent reviewed `extraction_worker.py` and ingestion integration without editing runtime code. **P1 defect reproduced, then independently verified fixed:** ingestion hashed source A, read replacement B, rejected the final hash mismatch, but saved B's successful pages under A's cache key. Restoring A and resuming originally returned B's text as a complete record.

The fixed reproduction repeated original-file replacement at the native-open boundary in **both direct and default subprocess modes**. Native opening received a separate snapshot whose bytes matched A. The changed original caused rejection, empty page text, and zero assertions. Restoring A and resuming the same cache key returned the original `2 hp` text; replacement `99 hp` text was absent. The hook targeted the original file explicitly because the native-open argument now correctly names private snapshot bytes.

Ingestion and targeted OCR use a hash-verified per-run snapshot, including worker restarts. Source-change rejection invalidates page evidence; rejected checkpoints are not reused. Interrupted successful pages therefore remain bound to verified bytes. A transient native-open failure preserves an existing valid checkpoint.

Focused independent verification passed **8 tests**: native page timeout/crash and recovery, native-open timeout, incomplete response timeout, source-change/restore, interrupted source-change/restore, snapshot-copy hash race, transient-open checkpoint preservation, and review-source replacement. Reproduce with:

```text
python -m pytest tests/test_extraction.py tests/test_interfaces.py -q -k "native_process_timeout or native_open_timeout or native_partial_response or source_change_rejects or verified_snapshot_protects or source_snapshot_hash or transient_native_open or source_page_hash_change"
```

Subsequent integration found a second Windows defect: the virtual environment's `python.exe` is a redirector, so reaping its PID did not prove the actual native interpreter was gone. The earlier eight checks did not establish native-process ownership. The correction launches `sys._base_executable` directly, supplies the active environment's trusted package paths under `-I`, and requires the worker's startup `os.getpid()` to equal the supervised PID before native opening.

Independent Windows verification injected `kernel32.Sleep(60000)` inside both page reading and PDF opening, with respective deadlines of 2 and 10 seconds. In both cases, callback PID, startup PID, and supervised PID matched; a Windows `SYNCHRONIZE` handle opened before the fault was signaled after timeout, proving the actual native process had exited. The page test's original PDF could not be renamed while the worker held it; deletion succeeded immediately after timeout. The open-timeout source also deleted immediately. The repository regression is `tests/test_extraction.py::test_timeout_reaps_actual_native_pid_and_releases_pdf_lock`; the independent run additionally exercised native-open termination.

Supervisor review confirmed sequential requests, atomic bounded-file responses, discarded stdout/stderr, and bounded terminate/kill/reap. A worker that cannot be reaped leaves the supervisor unable to accept more pages. Review rendering independently rejects same-size, same-mtime source replacement: it hashes and opens the same in-memory bytes, avoiding a stat-only cache decision.

Limits: no worker RSS cap or process-tree sandbox. Abruptly killing the parent can orphan an in-flight native child; no Windows Job Object/parent-death guarantee is implemented. Native deadlines exclude source copying/hashing, checkpoint work, and bounded cleanup overhead. Python network guards do not establish OS-level air-gap isolation. These authored failure checks do not change the frozen extraction/retrieval accuracy evidence.

## Reproduction scratch

The small `data/corpus/audit-jt02f42g/` scratch directory is ignored by `data/corpus/.gitignore`; it is not a corpus source or publication artifact. Automatic approval review rejected both recursive cleanup and an explicit-file cleanup, stating only “blocked by policy.” Cleanup was stopped; the directory contains no secrets but includes a machine-local path in its deliberately invalid manifest.
