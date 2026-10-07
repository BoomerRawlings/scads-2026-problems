# v10 implementation snapshot

Exact eight implementation/schema/dependency/manifest files used by Riverwatch11.
[snapshot.json](snapshot.json) records SHA256 and dataset fingerprints; the
[4B launch profile](../runtime-profile-qwen35-01.json) is unchanged from10.

Opt-in grounded-media defers isolated pixel-only observations until finish
preflight passes. The final report preserves those model outputs exactly and
uses host-authored current-run provenance limitations. Declared-synthetic
follow-ups are empty. Summary, findings, conflicts and qualifications remain
model-authored. The additional compact mode retains exact actually returned full records once,
keeps differing versions and graph/identity results/errors, and replaces repeated
media payloads in report input with audited facts and isolated observations. The
planner and observers still receive original pixels. No new corpus queries occur.
Canonical report-message hashes/bytes/counts and source-call lineage are recorded;
they exclude the HTTP envelope, response schema and generation settings.
This is constrained construction, not automated semantic acceptance.

For reproduction, copy the project into a separate directory without environments,
runs or model caches. Overlay these seven root code/schema/requirements files and
put the saved candidate manifest at `docs/runtime-candidate-qwen35.json`.
Use `--profile candidate-4b` in [runtime setup](../../../docs/local-runtime.md).
Keep the unchanged `data/` directory. This snapshot is not a standalone app.

```powershell
.\.venv\Scripts\python.exe local_agent.py riverwatch --question "What do the sources establish about readiness and dependencies? Keep the report concise: at most four findings, two conflicts, and short explanations." --base-url http://127.0.0.1:18571/v1 --model Qwen3.5-4B-Q4_K_M --max-steps 24 --timeout 1800 --request-timeout 900 --report-thinking-budget 1024 --grounded-media --compact-synthesis --output-dir runs/reproduced-riverwatch
```

Planning and isolated observations use non-thinking temperature0/seed0; report
synthesis requests1024thinking tokens at temperature0.6/seed0. Original isolated
JSON files, hashes and call/locator lineage are retained; private reasoning and
encoded input images are not saved. Matching inputs do not ensure identical or
correct output. These inspected cases are development, not held-out evaluation.

Before this run:162 implementation tests passed, no skips,52.829seconds;
eight affected checks passed after review refinements;
independent code review found no blocking issue. See the unchanged
[review protocol](../REVIEW-PROTOCOL.md) and [trial record](../../../docs/local-validation.md).
