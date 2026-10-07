# v11 implementation snapshot

Exact eight implementation/schema/dependency/manifest files frozen for Riverwatch12.
[snapshot.json](snapshot.json) records SHA256 and the unchanged dataset fingerprint.
The [4B launch profile](../runtime-profile-qwen35-01.json) is unchanged from11.

This version adds opt-in `--evidence-summary`, requiring grounded media and compact
synthesis. A complete report's overview is host-constructed from exact actually
returned, target-eligible records and supplied assertion triples. Different values
remain unresolved candidates. Source dates are not inferred event dates; recency
never determines truth. Actual associations, co-mentions and returned edge proofs
define eligibility. Other retrieved records remain in the model input and audit;
the overview explicitly counts exclusions. Missing assertions do not prove agreement.
The complete overview is bounded to4096UTF-8bytes; overflow fails visibly.

The model still chooses tools and authors findings, qualifications and conflicts.
Pixel observations remain separate model outputs, reused exactly. Current-run
limitations and declared-synthetic empty follow-ups are host-constructed. None of
these constraints establishes semantic acceptance. Original rejected reports stay
unchanged. Separate source review uses the [same protocol](../REVIEW-PROTOCOL.md).

For reproduction, copy the project into a separate directory without environments,
runs or caches. Overlay the seven saved root code/schema/requirements files and
put the candidate manifest at `docs/runtime-candidate-qwen35.json`. Keep `data/`
unchanged and use `--profile candidate-4b` in [runtime setup](../../../docs/local-runtime.md).
This snapshot is not a standalone app.

```powershell
.\.venv\Scripts\python.exe local_agent.py riverwatch --question "What do the sources establish about readiness and dependencies? Keep the report concise: at most four findings, two conflicts, and short explanations." --base-url http://127.0.0.1:18571/v1 --model Qwen3.5-4B-Q4_K_M --max-steps 24 --timeout 1800 --request-timeout 900 --report-thinking-budget 1024 --grounded-media --compact-synthesis --evidence-summary --output-dir runs/reproduced-riverwatch
```

Planning and isolated observations use non-thinking temperature0/seed0. Report
synthesis requests1024thinking tokens at temperature0.6/seed0. Compact context
hashes cover canonical report messages only, excluding schema/settings/HTTP envelope.
Overview hashes cover the exact UTF-8summary. Metadata preserves record hashes,
assertion references and exclusions without narrative/source bodies. Private
reasoning and input image encodings are not saved. Matching inputs do not guarantee
identical or correct output; this is development on a known synthetic fixture.

Before the run:172 implementation tests passed, no skips,61.104seconds, including
ten evidence-overview checks. Independent source/code review found no remaining
blocker. See the [trial record](../../../docs/local-validation.md) for outcomes.
