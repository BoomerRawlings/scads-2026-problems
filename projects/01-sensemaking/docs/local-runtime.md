# Free local agent runtime

`local_agent.py` runs a local vision-language model against the same six MCP tools as the optional Codex runner. The model chooses tools and writes the substantive analysis. Optional grounded-media mode fixes separately observed pixels and host-derived provenance fields, as disclosed below. No paid account, model API, API key, or Codex installation is required for this path.

Riverwatch14 uses the 9B profile and exact invocation below with the frozen
[v12 synthesis-guidance implementation](../evaluations/local-pilot/implementation-v12/README.md).
Its [original report and separate source review](../examples/local-riverwatch-guidance-accepted/REVIEW.md)
qualify one known synthetic investigation, with disclosed wording/color caveats.
The run took 2,538.563 seconds on a shared CPU host. The preceding
[trial13 review](../examples/local-riverwatch-9b-rejected/REVIEW.md) rejects an
unsupported exclusive explanation and incomplete dependency synthesis; it used
v11. Baseline examples use different settings. Matching a setup does not
guarantee correct or identical output.

The local HTTP endpoint uses llama.cpp's chat-completion format. The Python client uses standard-library HTTP, not the OpenAI SDK. It accepts only HTTP loopback addresses, disables proxy routing, rejects redirects, and sends no authorization header. Once the model files are installed, inference stays on the device.

## Selective public-data retrieval

The opt-in `--retrieval-profile catalog` replaces full-body search with bounded
metadata discovery and selective `read_evidence` calls. Actual complete,
unfiltered cursor chains establish inventory coverage. Catalog cards never earn
citation or edge-proof credit; the model must read the complete supporting source.
The report separately records discovered, fully read and unread source IDs.

For the local runner this profile requires `--grounded-media --compact-synthesis`
and currently admits **text-only** requests. Raw-pixel actions are excluded and
blocked before dispatch; the legacy profile retains the demonstrated PNG/video
workflow. `--evidence-summary` remains optional and host-authored when enabled.

Before each catalog-mode generation, the pinned server formats the full actual
request (including schema/settings) and tokenizes it without inference. The
default admission limits are 131,072 serialized request bytes and 16,384 tokens,
including the actual generation cap plus 128 tokens of headroom. Set
`--catalog-context-bytes` and `--context-token-limit` to match the serving slot.
This is conservative admission, not an exact-fit guarantee; actual prompt usage
and its difference from preflight are recorded and checked afterward. Unknown
counts, media blocks and overflow fail visibly. Source content is never silently
truncated to fit. A deadline timer interrupts trickled responses; requests share
the existing overall/request budgets.

The metadata stores counts, hashes, limits and comparisons, never the rendered
prompt or token IDs. See the [catalog contract](evidence-catalog.md) and
[pinned backend parser](https://github.com/ggml-org/llama.cpp/blob/b11457/tools/server/server-context.cpp#L4927-L4985).
The backend still loads/scans the complete corpus; bounded model inputs do not
establish scalable storage or public analytic quality. The accepted Riverwatch14
run uses the preserved v12 legacy implementation; public-model validation is a
separate development milestone.

## Setup

Start in `projects/01-sensemaking`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/setup_local_runtime.py
```

The final command displays the download plan without installing anything. The pinned installer supports **Windows ARM64**, with the existing CPU profiles and an unqualified opt-in Vulkan candidate. Four curated profiles select fixed local manifests; no arbitrary manifest path, backend directory or URL is accepted:

| Profile | Manifest | Server/model alias | Download bytes |
| --- | --- | --- | ---: |
| `baseline-2b` (default) | [2B baseline](runtime-manifest.json) | `Qwen3-VL-2B-Instruct-Q4_K_M` | 1,564,727,816 |
| `candidate-4b` | [4B development candidate](runtime-candidate-qwen35.json) | `Qwen3.5-4B-Q4_K_M` | 3,425,626,152 |
| `candidate-9b` | [9B development candidate](runtime-candidate-qwen35-9b.json) | `Qwen3.5-9B-Q3_K_M` | 5,604,074,472 |
| `candidate-9b-vulkan` | [9B Vulkan candidate](runtime-candidate-qwen35-9b-vulkan.json) | `Qwen3.5-9B-Q3_K_M` | 5,617,728,413 |

Each manifest identifies the llama.cpp build, model revision, quantizations, licenses, exact asset sizes and SHA256 hashes. Candidate installation is not evidence of analytic acceptance. The 9B assets have been installed and hash-verified; a short source-only request completed with the profile below. Broader resource fit and analytic quality remain unqualified. Other platforms need a matching llama.cpp build; the included ARM64 binary is not a universal installer.

Download/verify the pinned assets and start the server in this terminal:

```powershell
$scadsRuntime = .\.venv\Scripts\python.exe scripts/setup_local_runtime.py --download | ConvertFrom-Json
$scadsServerArgs = @(
  '--model', $scadsRuntime.model, '--mmproj', $scadsRuntime.mmproj,
  '--alias', $scadsRuntime.model_alias, '--host', '127.0.0.1', '--port', '18571',
  '--ctx-size', '12288', '--threads', '4', '--threads-batch', '4', '--parallel', '1',
  '--n-gpu-layers', '0', '--batch-size', '256', '--ubatch-size', '64',
  '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0', '--flash-attn', 'on',
  '--image-min-tokens', '64', '--image-max-tokens', '256', '--jinja',
  '--no-context-shift', '--no-webui', '--no-agent',
  '--cors-origins', 'http://127.0.0.1:18571', '--no-cors-credentials'
)
& $scadsRuntime.server @scadsServerArgs
```

Keep that terminal running. Wait for the model to finish loading before starting an investigation. Downloaded assets remain in the dedicated external cache; do not commit local installation paths or model binaries. MP4 evidence also requires `ffmpeg` and `ffprobe` on `PATH`.

To select the 4B candidate, inspect its dry run, then explicitly request installation:

```powershell
.\.venv\Scripts\python.exe scripts/setup_local_runtime.py --profile candidate-4b
$scadsRuntime = .\.venv\Scripts\python.exe scripts/setup_local_runtime.py --profile candidate-4b --download | ConvertFrom-Json
```

The returned `model`, `mmproj`, `server` and `model_alias` values can be used by the launch command above without copying or replacing either manifest. To reproduce the recorded 4B development profile, change its `--ctx-size` to `16384`, `--threads` to `8`, and `--threads-batch` to `8`; also add `'--chat-template-kwargs', '{"enable_thinking":false}'` to the argument array for its recorded disabled-thinking default. Keep the other launch flags. See the [recorded candidate profile](../evaluations/local-pilot/runtime-profile-qwen35-01.json) and [validation record](local-validation.md). `--profile baseline-2b` explicitly selects the original default again; each model revision uses its own cache directory. No model is downloaded, launched or queried by either dry run.

The larger 9B candidate selects [Qwen's 9B model](https://huggingface.co/Qwen/Qwen3.5-9B), quantized by [Unsloth at a pinned revision](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/tree/3885219b6810b007914f3a7950a8d1b469d598a5). Both identify Apache-2.0. This profile uses Q3_K_M language weights and the F16 vision projector; the pinned repository publishes no Q8 projector. The [manifest](runtime-candidate-qwen35-9b.json) preserves exact asset URLs and LFS SHA256 values.

```powershell
# Read-only selection; no download, cache write or model launch.
.\.venv\Scripts\python.exe scripts/setup_local_runtime.py --profile candidate-9b
# Explicit download/verification only; still does not launch a model.
$scadsRuntime = .\.venv\Scripts\python.exe scripts/setup_local_runtime.py --profile candidate-9b --download | ConvertFrom-Json
```

The 9B model and projector total **5,591,809,824 bytes** (about 5.59 decimal GB). The all-assets total includes the same 12,264,648-byte b11457 archive; a verified cached archive is reused. These are file sizes, **not a memory requirement**. Loading also needs context, image-processing and runtime memory; retained older caches and extraction consume additional disk. Available host memory and disk vary. The controlled probe below justified a bounded development trial, not a general capacity qualification. Selecting this candidate changes no report fields or validation policy.

### Opt-in Vulkan candidate: device discovered, model fit unqualified

The [pinned Vulkan manifest](runtime-candidate-qwen35-9b-vulkan.json) selects the
official [b11457 ARM64 Vulkan archive](https://github.com/ggml-org/llama.cpp/releases/tag/b11457):
25,918,589 bytes, SHA256
`189d661d7a83b9a50fb10a6b701bb7b6d8beeb4c3efd0f108224590e4476029d`.
It retains exactly the CPU 9B profile's two model/projector assets and revision;
verified cached copies are reused. Only the runtime archive differs.

The pinned extracted binary ran `--help` and `--list-devices`, both exit 0,
and listed `Vulkan0: Qualcomm Adreno X1-85`. The driver reported a 12,086 MiB
shared budget; this is not dedicated VRAM, available model memory or a fit/speed
measurement. Extracted files were rehashed unchanged afterward. No model was
loaded and no inference ran during these capability probes.

```powershell
# Read-only plan; prints the distinct runtime destination.
.\.venv\Scripts\python.exe scripts/setup_local_runtime.py --profile candidate-9b-vulkan
# Optional explicit installation; does not launch a server or a model.
$scadsVulkanRuntime = .\.venv\Scripts\python.exe scripts/setup_local_runtime.py --profile candidate-9b-vulkan --download | ConvertFrom-Json
# Device enumeration only; no model argument or inference.
& $scadsVulkanRuntime.server --list-devices
```

Extraction uses the fixed sibling cache `llama.cpp/b11457-vulkan-arm64`.
The CPU directory stays `llama.cpp/b11457`; Vulkan installation never targets it.
The installer rejects mismatched platform/version/archive selections and linked
extraction destinations. Neither profile changes global PATH or graphics drivers.

Before running an investigation, separately qualify model/backend compatibility,
a bounded load, output correctness and context/resource fit on the intended
device. None is established by enumeration, the archive digest or installation. For a later
**text-only** probe, use the returned `server`, `model` and `model_alias`, pass
`--no-mmproj`, and omit the `--mmproj` and image-token options. The projector
remains part of the reusable pinned asset set but is not loaded in that probe.
Keep loopback binding and use a free port; record the actual selected GPU,
offload settings and measured limits before claiming acceleration or capacity.
The recorded CPU commands/results below are unchanged and do not qualify Vulkan.

The first [bounded 9B Vulkan attempt](../evaluations/public-pilot/context-probe-vulkan-9b-8k-01.review.md)
stopped at the shared-host memory guard after **22.734 seconds total**, before
server readiness, context admission or inference. Its [recorded profile](../evaluations/public-pilot/runtime-profile-vulkan-9b-8k-01.json)
requested one GPU layer, 8,192 context tokens, no projector, batch 64/microbatch
16, Q8 caches and no warmup. Host free physical memory fell below 512 MiB on
two consecutive samples; the minimum was 488,865,792 bytes. The child exited
cleanly; its reported peak working set was 2,962,554,880 bytes. These shared-host
startup observations establish the resource stop, not backend incompatibility,
minimum RAM, successful layer offload or acceleration. The [original result](../evaluations/public-pilot/context-probe-vulkan-9b-8k-01.json)
and [prepared neutral request](../evaluations/public-pilot/context-probe-vulkan-9b-8k-01.request.json)
are preserved unchanged; the request was never sent. No retry is recorded.

### Recorded 9B profile and trial14

The [operator-recorded 9B profile](../evaluations/local-pilot/runtime-profile-qwen35-9b-01.json) uses b11457, CPU only, one server slot, 16,384 context tokens, eight generation/batch threads, batch 128/microbatch 32, Q8 key/value caches and flash attention. Weight repacking is disabled and loading uses memory mapping. These are recorded launch arguments, not server attestation. With the verified `candidate-9b` selection from above, reproduce the server launch from the project directory:

```powershell
$scads9BRuntime = .\.venv\Scripts\python.exe scripts/setup_local_runtime.py --profile candidate-9b --download | ConvertFrom-Json
$scads9BArgs = @(
  '--model', $scads9BRuntime.model, '--mmproj', $scads9BRuntime.mmproj,
  '--alias', $scads9BRuntime.model_alias, '--host', '127.0.0.1', '--port', '18571',
  '--ctx-size', '16384', '--threads', '8', '--threads-batch', '8', '--parallel', '1',
  '--n-gpu-layers', '0', '--batch-size', '128', '--ubatch-size', '32',
  '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0', '--flash-attn', 'on',
  '--image-min-tokens', '64', '--image-max-tokens', '256', '--jinja',
  '--no-repack', '--load-mode', 'mmap',
  '--chat-template-kwargs', '{"enable_thinking":false}',
  '--no-context-shift', '--no-webui', '--no-agent',
  '--cors-origins', 'http://127.0.0.1:18571', '--no-cors-credentials'
)
& $scads9BRuntime.server @scads9BArgs
```

The literal JSON argument preserves the recorded disabled-thinking server default. [b11457 accepts this option](https://github.com/ggml-org/llama.cpp/blob/b11457/common/arg.cpp#L3434-L3451), while marking `enable_thinking` there deprecated in favor of `--reasoning off`; the recorded option is retained for reproduction. Runner requests explicitly override this default when report-only thinking is enabled. The shown quoting was checked with PowerShell 7 native argument passing.

The [source-only probe](../evaluations/local-pilot/qwen35-9b-source-probe.json) completed in 65.578 seconds using three known fixture records, with no MCP tools, planner or media. Its phrase “sensor's actual defect” misleadingly suggests an unestablished defect; the [source-review caveat](local-validation.md) prevents treating that completed probe as a quality success. The [capacity sample](../evaluations/local-pilot/qwen35-9b-capacity-probe.json) records one idle point afterward: 5,654,065,152 bytes server working set and 712,128 KiB host free physical memory. Its peak includes startup and the machine had other workloads. Neither establishes a minimum RAM requirement, sustained multimedia capacity or analytic acceptance. The 256-token image cap is also unqualified for small print and natural scenes.

After this server finishes loading, the trial14 command in a second terminal is:

```powershell
.\.venv\Scripts\python.exe local_agent.py riverwatch --question 'What do the sources establish about readiness and dependencies? Keep the report concise: at most four findings, two conflicts, and short explanations.' --base-url http://127.0.0.1:18571/v1 --model Qwen3.5-9B-Q3_K_M --max-steps 24 --timeout 2700 --request-timeout 1200 --report-thinking-budget 1024 --grounded-media --compact-synthesis --evidence-summary --output-dir runs/local-riverwatch-14
```

This allows 24 actions, 2,700 seconds overall and 1,200 seconds per model request. Planning and isolated visual requests disable thinking; only final synthesis requests the 1,024-token thinking budget, with a 4,096-token total generation cap. The exact question, model alias, budgets and three opt-in flags retain trial13's recorded settings; v12 changes only generic report guidance and its metadata label. The host constructs the complete evidence overview and provenance fields; the model still authors findings, conflicts and qualifications. Trial14 passes separate source review for this known synthetic case; it does not establish repeatability or unfamiliar-data accuracy. To reproduce the rejected trial13, overlay the frozen v11 root files and retain this 9B profile/question/settings with a fresh output directory; v11 alone contains the earlier 4B manifest. For another attempt choose a new output directory; existing evidence is never overwritten.

### Public text-only profile

The [public pilot profile](../evaluations/public-pilot/runtime-profile-qwen35-9b-text-01.json)
uses the same pinned runtime/model and 16,384-token slot. Starting from the 9B
argument array above, remove `--mmproj` and its value, remove both image-token
options and their values, and add `--no-mmproj`, `--cache-ram 0` and
`--no-cache-idle-slots`. Retain all other arguments. This is a separate recorded
profile, not a controlled performance comparison with media trials. The
[frozen v13 instructions](../evaluations/public-pilot/implementation-v13/README.md)
give the exact public question and runner flags. Its neutral live context probe
matches 35 preflight and actual prompt tokens; full analytic review is separate.

NCI01 subsequently exceeded that 16,384-token slot without producing a report.
The [expanded-context 4B text experiment](../evaluations/public-pilot/implementation-v14/README.md)
uses verified `candidate-4b` assets, alias `Qwen3.5-4B-Q4_K_M` and
`--ctx-size 49152`; all other 9B text launch flags above remain unchanged.
Runner limits and exact question are bound in its snapshot. Its small neutral
probe passes; whole-window capacity and analytic quality require separate
measurement. The historical 9B profile and failure remain unchanged.

The baseline/4B launch settings above limit memory and image processing for the supplied large-text
caption media. Their 256-token image cap reduces visual detail; it is not qualified
for small print or spatial grounding. Higher-resolution analysis needs a separately
evaluated profile with more compute/memory. The [development record](local-validation.md)
includes the slower settings, failures, and a direct-pixel transcription check.

In a second terminal, again from the project directory:

```powershell
.\.venv\Scripts\python.exe local_agent.py Delta --base-url http://127.0.0.1:18571/v1 --output-dir runs/local-delta
.\.venv\Scripts\python.exe local_agent.py riverwatch --question "What do the sources establish about readiness and dependencies? Limit the report to 4 findings and 2 conflicts." --base-url http://127.0.0.1:18571/v1 --max-steps 24 --timeout 1800 --request-timeout 900 --output-dir runs/local-riverwatch
```

Use a new or empty output directory for each run. Existing run evidence is never silently replaced. `Delta` tests ambiguous identity; it should lead to clarification. `riverwatch` exercises document, relationship, image and video evidence. These are declared synthetic development cases, not independent model evaluations.

`--data-dir <directory>` selects a compatible dataset; `--question` supplies the investigation question. See [integration.md](integration.md) for the input contract. `--model` optionally selects an exact model ID reported by `/v1/models`; omission requires exactly one loaded model.

`--report-thinking-budget N` optionally enables report-only reasoning, with an integer budget from 0 to 4,096; the default 0 preserves disabled reasoning and greedy generation. Use a thinking-capable model and its matching template. The request fields are verified against [llama.cpp b11457's reasoning-budget implementation](https://github.com/ggml-org/llama.cpp/blob/b11457/tools/server/server-common.cpp#L1303-L1366), which depends on the template exposing thinking end tags. This option does not verify the loaded model's capabilities or establish better analytical accuracy.

With a positive budget, only report synthesis sends `enable_thinking=true`, `reasoning_budget_tokens=N`, a total generation cap of `3072+N`, temperature 0.6, top-p 0.95, top-k 20, min-p 0, presence penalty 0, and seed 0. Planning remains disabled-reasoning, temperature 0, seed 0, and 512 tokens. The report schema, finish preflight, action/time/context limits and final guards remain unchanged. The metadata records requested report settings, allowlisted numeric token usage and whether a reasoning field was returned; reasoning text is never saved or fed back into planning. Missing usage fields remain absent. A budget requests backend behavior; the server's numeric response is not independent proof of enforcement.

`--grounded-media` is a separate opt-in mode; omission preserves the baseline workflow. After a finish intent passes preflight, each successful `read_media` call receives one isolated visual-model request from its retained pixels. This deferral avoids repeatedly replacing the planner's context during tool use. Each request contains only those pixels, the exact evidence ID and audited returned image/frame locators, plus generic faithful-transcription instructions. Source text, extraction labels, source dates, target, question, graph and prior conversation are excluded. Labels identify the input; they are not depicted facts. No additional media or corpus queries occur. The model must return one observation per actual image, in order; missing, altered or invented ID/locator pairs fail explicitly.

Each isolated request consumes one action and remaining run time, uses disabled reasoning, temperature 0, seed 0, and a 1,536-token cap. Before starting, the runner reserves actions for all pending visual requests plus final synthesis. Malformed, truncated or failed inference stops the run visibly. Corrected report retries reuse completed isolated observations; a later successful media call adds a new observation request. The planner retains original source results and pixels. Report synthesis retains them unless compact mode is enabled, which substitutes the preserved isolated observations for raw pixel blocks. Observation artifacts retain their original JSON response bytes, with source call/locator lineage, input/output SHA256 and sanitized usage metadata; input images and separate reasoning text are never written to these artifacts. The input hash covers canonical messages, schema and generation settings; the model identifier is recorded separately. An output that copies its input image encoding is rejected without saving that body.

In this mode, the final report schema fixes `media_observations` to the isolated model outputs exactly and `limitations` to host-authored current-run provenance: returned pixel IDs/frames, no audio, sampled-video coverage, observed media declaration/availability gaps, and bounded graph/inventory scope. No unseen records are queried to construct limitations. “No attachment declared,” “availability not inspected,” and “inspection reported unavailable” remain distinct; none establishes whether media exists elsewhere. Synthetic declarations add a shared-origin/independent-verification caution and fix `follow_up` to `[]`; public-dataset follow-ups remain model-authored. Explicit equality validation backs the schema constraints. The runner never rewrites a returned report to make it pass. Findings, conflicts and qualifications remain model-authored. The summary does too unless `--evidence-summary` constructs a complete report overview. Source dates and assertions must not be blended into pixels.

This is **grounded output construction, not automated semantic acceptance**. Pixel-only transcription can still be wrong, and cross-source analysis can still overstate its evidence. Saved artifacts disclose which fields were constrained; historical trials are unchanged. The pinned [llama.cpp grammar converter](https://github.com/ggml-org/llama.cpp/blob/b11457/common/json-schema-to-grammar.cpp#L825-L878) supports constant fields and ordered tuple outputs. Live model/source review remains necessary.

`--compact-synthesis` is another opt-in and requires `--grounded-media`; without both flags the existing report context is unchanged. It changes only final synthesis. The planner still receives original tool results and pixels, and isolated observers still receive the actual pixels. Compact synthesis instead receives exact retrieved evidence records, actual identity/graph results, tool failures, audited current-run facts and the fixed isolated observations/provenance fields. It does not query the dataset again, fetch unseen sources, interpret source claims, or add an answer.

Identical full records are deduplicated by their complete canonical JSON bytes, including every field and all source text. First-occurrence order is preserved; different versions of one source remain separate. Identical structured/text representations of one MCP response are decoded once; differing representations are retained. Identity/graph results retain their actual arguments and payloads, with identical results reused. Failed calls stay failures, never evidence records. Unsupported successful source envelopes and partial/truncated records fail explicitly rather than silently losing source content. Raw MCP image blocks and redundant successful media wrappers are omitted only from this report context: actual media handling remains represented by the audited facts and fixed observations. This omission does not imply that media was unavailable or uninspected.

The compact report prompt preserves source attribution, competing claims, negation, scope, plans versus actual events, and the distinction between source recency and truth. Its 350-word limit (or a tighter question limit) applies only to model-authored narrative; fixed arrays are excluded. The report schema and every final guard remain unchanged. This is a context construction policy, not evidence summarization or a semantic-correctness guarantee; original reports and earlier source snapshots remain unmodified.

For each compact report request, `run-metadata.json` records `compact_synthesis.generations`: policy `exact-record-compact-synthesis-v1`, canonical message SHA256/byte count, counts, and per-record/per-identity-graph-result SHA256 with original 1-based MCP call references. `input_scope: canonical_report_messages_only` explicitly limits `input_sha256`/`input_bytes` to canonical UTF-8 JSON of the messages; these exclude the response schema, model/settings and serialized HTTP envelope, and are not wire-byte measurements. Source record hashes cover the entire canonical record. Occurrence counts exclude identical text/structured envelopes, then count repeated full records before record deduplication. Failed-call indices and the number of omitted raw image blocks are recorded. This metadata contains references/hashes, not source bodies, image encodings, model reasoning, or the synthesis conversation. Existing event/audit lineage is preserved; compact input fingerprints identify construction, not independent source authenticity or analytic validity.

`--evidence-summary` requires both `--grounded-media` and `--compact-synthesis`. For a **complete** report only, it fixes `summary` to a host-constructed evidence overview. The planner, tool choices, inference action count and model-authored findings/conflicts/qualifications remain unchanged. Clarification and insufficient-evidence summaries remain model-authored. Omitting the flag preserves earlier behavior and all previous artifacts.

The overview uses the compact phase's exact actually returned records and audited graph/inventory scope, never a new corpus lookup or extracted narrative claim. Eligible records have explicit entity associations connected to returned target-rooted scope (including recursive co-mentions), or are retrieved proofs of actual returned graph edges. Assertion subjects, aliases and narrative text cannot establish eligibility. Other retrieved records remain intact in synthesis, but their assertions are excluded from the overview with an explicit excluded count; the audit retains their source IDs, record indices and hashes. It reports eligible source counts and declared synthetic provenance, then groups supplied assertions by exact string `subject` and `predicate`. Different nonempty string `value` fields are listed as unresolved candidates with source IDs and record/source dates, not adjudicated contradictions or inferred event times. Different record variants of one source remain attributed separately; a record index is its position among deduplicated returned records, not a historical revision number. Identical values share an attribution list; malformed/missing assertion fields are counted and disclosed, not repaired or inferred from prose. All source strings are quoted data, never instructions. A lack of differing supplied values explicitly does not establish absence of real conflicts.

This is a deterministic evidence overview, **not an analytical truth check**. It neither decides which dated source is correct nor measures incidence, independent corroboration, or complete semantic conflict coverage. Model-authored analysis still faces the same separate source-review criteria. The overview is schema-fixed and checked for exact equality; a model rewrite is rejected and the original parsed draft preserved. The 350-word narrative limit excludes this fixed summary and the other fixed fields. The complete overview must fit 4,096 UTF-8 bytes; otherwise the run fails with `evidence_summary_limit` instead of dropping candidates or abbreviating source values silently.

`evidence_summary` metadata declares policy `exact-assertion-evidence-overview-v1`, scope `complete_reports_only`, the opt-in flag and byte cap. Each constructed generation records its action/status, host attribution, exact summary SHA256/UTF-8 byte count, eligible source/record/assertion/difference counts, full record hashes, and record/assertion indices linking every candidate to supplied data. Its scope metadata records policy `actual-associations-and-returned-proofs-v1`, eligible indices, reached associations, retrieved proof IDs, and excluded record count/IDs/indices/hashes. It contains no assertion-value narratives. Source dates may be capture or record dates and are never upgraded into event dates. Rejected complete generations remain auditable even if a later final report abstains; only a final complete report receives the constrained-summary attribution. The overview and its schema require no extra model action.

## What executes

1. Discover the local model through `/v1/models`, fingerprint the dataset, and initialize a real MCP stdio subprocess.
2. Read tool names, descriptions and argument schemas from MCP. Give the model the question, target and dataset descriptor. Unresolved requested identities permit only identity search and a model-authored clarification; this scope policy blocks arbitrary candidate investigations. Their finish intent fixes the clarification status and original target; subsequent report synthesis requires empty evidence findings/conflicts/media arrays. The model still writes the narrative and candidate explanation from actual entity-search results.
3. Ask the model for one short schema-constrained action: a named tool with arguments, or `finish` with only the intended status and target. Decision generation is capped at 512 tokens. The model plans within identity, provenance and progress constraints. Refresh the schema each turn: `read_evidence` accepts observed source IDs not already successfully read; `inspect_media` accepts observed media records not already inspected; `read_media` accepts only source IDs confirmed available by inspection. Successfully read images leave the eligible set; videos remain eligible for additional seek offsets. Remove an action when no eligible IDs remain. Graph and search discovery remain available for model-selected pivots. A graph edge's proof ID permits reading that source; it does not permit citing unread evidence. Report citations are restricted to actually retrieved IDs. Media paths are never accepted as source IDs.
4. Execute the selected MCP tool. Return its actual result, including errors, to the model. Text is explicitly marked as untrusted source material. Image blocks become base64 image inputs alongside source and sampled-frame timestamps. For a successful exact repeat, return a reference to the first call's retained full result instead of another identical body; the MCP call still executes and remains in the audit.
5. Preflight a finish intent against the target, connected-workflow, coverage and media guards. A complete report needs successful unfiltered inventory for every entity actually returned by its target-rooted/relevant graph traversals, plus full source retrieval for every proof ID on those returned edges. Batched inventories count; filtered searches do not. Missing prerequisites produce compact entity/proof IDs before any report request. The model chooses the next calls or an appropriate abstention. Feedback supplies no source evidence or automatic tool calls.
6. If preflight passes and both action/time budget remain, run pending isolated observations when `--grounded-media` is enabled, then request report-only synthesis, capped at 3,072 tokens plus any optional thinking budget. Synthesis consumes another action. Lock its status and target to the accepted intent; restrict citations to actually retrieved IDs. Media observations accept only audited source-ID/locator pairs: `image` or the actual returned frame timestamp, canonicalized to microseconds with minutes/hours as needed. No inspected pixels means an empty media-observation array, even if an annotation or transcript was retrieved. The opt-in mode also fixes the fields described above. Ask for at most 350 words of narrative. Use a fresh context containing the exact question/target/dataset descriptor, every unique actual result body with references for exact repeats, every error, and safe prior report-validation reasons. Preserve source text and frame locators. Default synthesis retains pixels; compact synthesis uses the preserved isolated observations instead. Omit planning tool catalogs, assistant decisions and rejected drafts. The planner's conversation remains intact.
7. Validate the resulting report again with all final guards. Reject unsupported target substitutions, unobserved or disconnected citations, invented media coverage, and missing workflow steps. Preserve parsed rejected reports separately for review. Malformed or rejected reports return to planning while budget remains; later synthesis receives the safe rejection reasons. Recheck the dataset fingerprint, save a valid report and its audit, or record failure when the run cannot finish within its limits.

These guards establish retrieval and workflow provenance. They do not prove that a claim accurately interprets its cited source. The model can produce weak analysis, miss connections, or fail; independent evaluation remains necessary.

Finish preflight avoids generating a long report when its status already fails structural prerequisites. It does not certify analytical quality or force a complete answer. The 350-word synthesis instruction and demonstration question's finding/conflict limits are writing constraints; final evidence and workflow validation remains separate.

Coverage comes from actual successful MCP result envelopes. Empty-query search results explicitly confirm the unpaginated entity scope, including entities with zero hits. A request alone, a filtered/truncated response, or a future paginated response cannot establish inventory completion. Edge proofs must appear as full source records returned by `search_evidence` or `read_evidence`; media metadata, snippets and pixels alone do not satisfy that obligation. Proofs may belong to entities outside the graph neighborhood. Unrelated traversals and document co-mentions do not expand the mandatory graph scope; later traversals from already reached entities do. Available-media obligations use this same returned scope.

Both local and Codex runners store a compact `workflow_coverage` ledger with scope IDs, traversal depths/counts, inventories, retrieved proof records and missing IDs. Coverage policy is `returned-graph-coverage-v1`; the current local policy is `evidence-overview-opt-in-v11`, with optional modes recorded separately. Older saved trials retain their original policy and outputs; they are not retroactively certified by these guards. Coverage establishes the declared exploration scope, not full-graph completeness or analytical adequacy. A shallow model-selected scope still needs independent review.

The v8 report context includes a compact `CURRENT_RUN_FACTS` preamble derived from successful actual MCP results and their audit: inventoried graph scope, retrieved source IDs, declared media attachments, inspected availability, and successful returned image/frame locators. Failed calls and source-text claims do not supply these facts; the runner does not inspect unseen dataset records to construct them. Frame locators come from returned source PTS intersected with the pixel audit, never requested seek times. A returned record without a media path supports only “no attachment declared”; an actual successful `inspect_media` response is required to state its observed availability.

This preamble separates historical annotation/transcript authoring labels from the current run. Successful pixel retrieval means that source cannot accurately be described as transcript-only or missing raw media in this run. It does not establish independent corroboration, full-video viewing, or audio processing. The default report context retains original source text, extraction labels, returned pixels, errors and exact-repeat references. Compact mode preserves exact records and errors, using the separately recorded observations instead of raw pixels. Dated reports remain attributed source claims, not independently verified current truth. The preamble and prompt improve explicit provenance; they do not add a semantic-review phase or guarantee that the model follows those distinctions.

Coverage does not trigger unlimited expansion. Existing step, byte, context and time limits apply; unresolved coverage permits `insufficient_evidence`, never an automatic complete result. Current inventories return full source text without pagination, so large graphs/corpora may exceed those limits. Scalable inventory would require a separately tested paginated interface and complete cursor-chain/snapshot accounting; this implementation rejects paginated completion claims instead of inferring coverage from a terminal page.

The report prompt retains analytical constraints: preserve dated competing claims; a later date alone does not establish correction or current truth; graph associations do not establish causation or control; repeated shared-origin content is not independent corroboration. Missing raw media belongs under limitations, never pixel observations.

The full conversation retains successful results and image inputs. Successful source-record reads and image reads are not repeated; changing timestamps cannot enable another image read. Observed image/video/audio records may be inspected even when raw bytes are absent; an `available=false` result never enables a raw-media read.

Repeated discovery calls still execute. After each successful MCP call, hash canonical JSON containing its tool name, actual arguments and entire raw result, including image data. An exact prior match gets a short reference to the first call; that original full result and its pixels remain available to planning; synthesis follows the selected context policy described above. No source summary replaces evidence. Different tools, arguments, timestamps, source text, images or other result fields retain their full bodies. Errors always retain their full bodies, even when repeated. Metadata records each reused result's original/repeat call numbers and SHA256; trace, events, retrieval provenance and action accounting still include every actual call. Repeated matching results are not independent corroboration.

Video sampling is adaptive. A later request may contain up to four offsets and must include at least one that has not already succeeded. A mixed request such as `[0, 27]` remains valid after `[0]`; repeating only `[0]` is blocked before MCP execution. Omitted or null timestamps become the actual inspection's suggested offsets before the MCP call, so default and explicit requests cannot bypass this check. Failed calls consume no offsets and may be retried. Requested seeks and returned source presentation timestamps are recorded separately: two different seeks may decode the same frame, and citations must use the returned source timestamp. Step, time and context limits still bound exploration.

The schema bounds each offset array to 1–4 values in 0–3,600 seconds. The backend enforces offset novelty even if the model ignores the schema. This distinction is explicit because [llama.cpp's schema converter](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md) does not support `contains`/`minContains`, which would express “at least one new offset.” Blocked requests enter scope-rejection metadata, never the actual MCP trace.

## Limits and failure handling

| Limit | Default / behavior |
| --- | --- |
| Model actions | 24; `--max-steps` permits 1–100. Each tool decision, finish intent, opt-in isolated visual request and report generation consumes one action. |
| Overall time | 1,200 seconds; set `--timeout`. |
| Individual model request | 600 seconds; set `--request-timeout`. Socket waits are bounded by remaining run time. |
| MCP request | At most 45 seconds, bounded by remaining run time. |
| Video request | 1–4 seek offsets, 0–3,600 seconds; at least one not previously successful. |
| Model generation | 512 tokens per decision; 1,536 per opt-in isolated visual request; 3,072 per report synthesis plus an optional 0–4,096 thinking-token budget. A truncated generation fails explicitly. |
| HTTP response | 2 MiB. |
| One MCP result | 8 MiB. |
| HTTP conversation body | 24 MiB; no silent evidence truncation. The model's token context can impose a smaller limit. |
| Sampling | Default temperature 0, seed 0. Opt-in report reasoning uses the settings above. Hardware/runtime differences can still change outputs. |

A larger timeout permits slower hardware; it does not establish better quality. A timed-out local model request is recorded as `model_timeout`, distinct from connection failure (`model_unavailable`). Context overflow, unsupported model responses, absent media decoders, or exhausted steps are recorded failures. There is no paid fallback, fabricated successful report, or automatic weakening of the validation rules.

## Saved artifacts

| File | Contents |
| --- | --- |
| `report.json` / `report.md` | Validated analytic report or explicit clarification/insufficient-evidence result. |
| `rejected-report-NN.json` | Original parsed report rejected by final validation, bounded to 2 MiB. Unvalidated analytic output retained for source review; never substituted for the accepted report. Malformed JSON produces no candidate file. |
| `media-observation-NN.json` | Opt-in isolated visual-model JSON answer, original bytes. Metadata distinguishes observed/rejected output; malformed JSON and copied image encodings produce no candidate file. Never a semantic-accuracy certificate. |
| `tool-trace.json` | Actual MCP tool names, arguments, and success/failure. No source text, model conversation, or image bytes. |
| `evidence-ledger.json` | Retrieved evidence IDs, source/date, text hashes, and inspected raw-media hashes. |
| `run-metadata.json` | Model identifier from `/v1/models`, endpoint/backend, dataset/code/prompt fingerprints, question/target, requested report settings, sanitized numeric token usage and reasoning-presence flags, elapsed time, limits, step count, decision/media-observation/report phase, synthesis-context policy, compact `synthesis_facts`, observed/retrieved source IDs, `workflow_coverage`, successful requested video offsets, returned source PTS samples, action/intent/report rejections, rejected-report filenames with safe reasons, exact-result reuse call numbers/hashes, grounded-mode constrained fields plus observation call/locator lineage, filenames and input/output hashes, and optional compact-synthesis message/record hashes, counts and actual call references. |
| `failure.json` | Safe failure code and explanation when no report was accepted. Failed runs also preserve their trace and metadata. |

Launch llama-server with `--alias` for a portable model identifier. If it reports an absolute filename instead, metadata stores its basename and identifier hash, not a machine path. The pinned runtime manifest supplies model-file hashes; the server's advertised alias alone does not verify the loaded weights. Raw server logs, authentication state and image base64 are not saved in run artifacts.

Trace and metadata checkpoints are written atomically at startup, before each model request, and after each tool result, blocked action, or rejected report. Metadata remains `running` until an accepted report or handled failure is saved. If the process is interrupted, a remaining `running` checkpoint records unfinished work; it is not a success claim or proof that a process is still alive. Safe report-rejection reasons also appear on stderr. No model narrative, source text or image bytes enter these progress checkpoints.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_local_agent.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_grounded_media.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_compact_synthesis.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_evidence_summary.py -v
```

Tests exercise actual loopback HTTP with scripted responses and actual MCP stdio calls. They cover endpoint restrictions, model selection, size limits, image/timestamp forwarding, identity scope and report-target/citation/media guards, changing datasets, tool errors, failure artifacts and output preservation. Adaptive-media tests cover successive and mixed video seeks, failed-read retry, default/explicit aliases, distinct seeks returning one PTS, image-repeat rejection, and unavailable media. Finish tests cover rejection before report inference, valid complete synthesis, malformed/post-validation recovery, clarification, preserved source context, and exhausted action budgets. Media-schema tests cover unread media exclusion, exact inspected pairs, fractional/hour locators, validation feedback in a subsequent synthesis, and rejected-draft retention without stale reuse after a parse failure. Result-reuse tests verify two actual calls with one retained body, unchanged provenance, preserved pixels, and full bodies for changed arguments/results/timestamps or any errors. Scope-blocked actions are recorded separately; they never become fabricated MCP calls. Scripted responses test the runner; only a separately recorded live-model run can demonstrate local model behavior.

Protocol references: [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md), [official MCP Python SDK v1](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x).
