# v8 implementation snapshot

Exact eight code/schema/dependency/manifest files used by Riverwatch09.
[snapshot.json](snapshot.json) records their SHA256 values, the dataset fingerprint,
and the unchanged [4B launch profile](../runtime-profile-qwen35-01.json).
This snapshot preserves implementation bytes; it does not certify model claims.

The change from v7 adds compact current-run facts to report synthesis, derived
only from successful MCP result envelopes and recorded coverage/pixel audits.
They distinguish declared attachments, inspected availability and returned
image/frame locators. Historical source-authoring labels remain separate from
what the current investigation decoded. Full original evidence and pixels remain
in the model context. No private reasoning text is preserved.

For reproduction, copy the project into a separate directory without environments,
generated runs or model caches. Overlay the seven code/schema/requirements files
at its root, then place this saved candidate manifest at `docs/runtime-candidate-qwen35.json`.
Use the current installer's `--profile candidate-4b` option in the
[runtime setup](../../../docs/local-runtime.md). Keep the
original `data/` directory. This snapshot is not a standalone application.

Use the same launch profile, question and budgets as Riverwatch08:

```powershell
.\.venv\Scripts\python.exe local_agent.py riverwatch --question "What do the sources establish about readiness and dependencies? Keep the report concise: at most four findings, two conflicts, and short explanations." --base-url http://127.0.0.1:18571/v1 --model Qwen3.5-4B-Q4_K_M --max-steps 24 --timeout 1800 --request-timeout 900 --report-thinking-budget 1024 --output-dir runs/reproduced-riverwatch
```

Planning remains non-thinking at temperature0/seed0; report generation requests
1024thinking tokens at temperature0.6/seed0. Matching inputs do not guarantee
identical output or an accepted report. These inspected development cases are
not held-out evaluation. See the [source-review protocol](../REVIEW-PROTOCOL.md)
and [trial record](../../../docs/local-validation.md).
