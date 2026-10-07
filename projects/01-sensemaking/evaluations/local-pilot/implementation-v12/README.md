# v12 report-synthesis guidance snapshot

Eight exact code/schema/dependency/manifest files are preserved here.
[snapshot.json](snapshot.json) records their SHA256 values and the unchanged
dataset fingerprint. This experiment keeps Riverwatch13's exact question,
Qwen3.5-9B-Q3_K_M model, [9B launch profile](../runtime-profile-qwen35-9b-01.json),
24-action limit, time budgets and report-thinking budget.

Only the two report-synthesis prompts and their explicit metadata label changed.
Both contexts now include this generic guidance:

> Answer every part of the question. Consolidate competing dated claims instead
> of repeating them as separate findings. Synthesize supported, question-relevant
> multi-hop paths, preserving relation types and citing source evidence for their
> links. Lack of evidence for X neither excludes X nor establishes 'only Y'.
> Distinguish forecasts and schedules from evidence that an event actually
> occurred or work was completed.

Metadata records `synthesis_guidance_policy: question-path-and-qualification-v12`.
The existing `schema_policy: evidence-overview-opt-in-v11` remains unchanged:
no schema, guard, planner, tool-selection or constrained-field change occurred.
The model still authors findings, conflicts and qualifications. Existing optional
host overview/provenance and isolated pixel observations retain their disclosed
construction and exact-reuse rules. Guidance does not guarantee supported claims.
The [source-review protocol](../REVIEW-PROTOCOL.md) is unchanged; original trial13
and earlier artifacts are not rewritten or relabeled.

For reproduction, copy the project into a separate directory without environments,
runs or caches. Overlay the seven saved root code/schema/requirements files and
put the saved 9B manifest at `docs/runtime-candidate-qwen35-9b.json`. Keep `data/`
unchanged. Use `--profile candidate-9b` and the recorded 9B server arguments in
[runtime setup](../../../docs/local-runtime.md), including disabled repacking,
`--load-mode mmap`, batch 128/microbatch 32 and disabled-thinking server default.
This snapshot is not a standalone application or a bundled runtime/model.

```powershell
.\.venv\Scripts\python.exe local_agent.py riverwatch --question 'What do the sources establish about readiness and dependencies? Keep the report concise: at most four findings, two conflicts, and short explanations.' --base-url http://127.0.0.1:18571/v1 --model Qwen3.5-9B-Q3_K_M --max-steps 24 --timeout 2700 --request-timeout 1200 --report-thinking-budget 1024 --grounded-media --compact-synthesis --evidence-summary --output-dir runs/reproduced-riverwatch-v12
```

Choose a fresh output directory. Planning and isolated observations use disabled
thinking, temperature 0 and seed 0. Report synthesis requests 1,024 thinking tokens
within a 4,096-token output cap, temperature 0.6 and seed 0. Private reasoning is
not saved. Repeating settings does not guarantee identical or correct outputs.
This remains iteration on a known synthetic fixture, not held-out evaluation.

Before freezing, **101 existing focused checks passed, zero skips, in 60.023
seconds** across local protocol/agent execution, compact synthesis, evidence
overview, report validation and grounded media. No new prompt-mirroring tests
were added. All other root source/schema/dependency bytes and the dataset
fingerprint match v11. These are implementation checks; no v12 live inference
or analytic acceptance is claimed by this snapshot.
