# v7 implementation snapshot

Exact files recorded for ClearAir04 and Riverwatch08. This snapshot preserves
implementation bytes; it does not certify either run's analytic conclusions.
ClearAir04's original output and rejection are preserved in its
[source review](../../../examples/local-clearair-thinking-rejected/REVIEW.md).

Eight saved files:

| Files | Purpose |
| --- | --- |
| `local_agent.py` | Local planner, coverage preflight, report synthesis, and bounded retries |
| `run_agent.py` | Shared report, source-scope, citation, and media-locator guards |
| `mcp_server.py`, `sensemaking.py` | Six MCP tools and dataset retrieval |
| `media_tools.py` | Source images and decoded video PTS |
| `report.schema.json` | Analytic report contract |
| `requirements.txt` | Pinned Python dependencies |
| `runtime-candidate-qwen35.json` | Pinned llama.cpp, model, projector, and asset hashes |

[snapshot.json](snapshot.json) contains the complete SHA256 values for all eight
files; all were verified against their saved bytes. The synthetic dataset's
combined fingerprint is
`7328e186691e7956ac440b1acd28391b6a2e022292b2c28c0104af6d0139cd67`.
Per-source fingerprints are retained in each run's metadata; the dataset itself
remains in the project's `data/` directory.

To reproduce, make a separate copy of the project's source and `data/`, excluding
environments, generated runs, and model caches. Overlay the seven saved
code/schema/requirements files at that copy's project root. Place the saved
candidate manifest at `docs/runtime-manifest.json` in that copy before following
the project's local runtime installation instructions. Do not execute this
snapshot directory as a standalone project: it omits data, models, and environments.

Use the [4B launch profile](../runtime-profile-qwen35-01.json): llama.cpp b11457,
Qwen3.5-4B Q4_K_M with F16 projector, Unsloth revision
`e87f176479d0855a907a41277aca2f8ee7a09523`, 16,384 context tokens, CPU execution,
eight threads, one slot, and context shifting disabled. The manifest installer
targets Windows ARM64. The profile records operator launch settings, not server
attestation; it still identifies this model as an unqualified development candidate.

With that loopback server running, reproduce ClearAir04 from the separate project:

```powershell
.\.venv\Scripts\python.exe local_agent.py clearair --question "What do these sources establish about ClearAir readiness and coordination? Keep the report under 200 words." --base-url http://127.0.0.1:18571/v1 --model Qwen3.5-4B-Q4_K_M --max-steps 24 --timeout 1800 --request-timeout 900 --report-thinking-budget 1024 --output-dir runs/reproduced-clearair
```

Planning used temperature 0 and seed 0. Report synthesis requested thinking with
the recorded 1,024-token budget, temperature 0.6, and seed 0; exact settings and
numeric usage are in the preserved metadata. Private reasoning is not included.
Hardware, concurrent workloads, and numerical execution can change timing/output;
matching inputs do not guarantee an identical report or an accepted analysis.
