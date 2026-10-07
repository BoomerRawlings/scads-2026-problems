# Local runtime development record

These are development trials on the known synthetic fixture, not held-out
evaluations or a success-rate estimate. Model/tool implementation changes between
trials are deliberate. Failed and interrupted trials are included; their
[sanitized artifacts](../evaluations/local-pilot/) preserve the actual outcomes.

Runtime: llama.cpp b11457, Qwen3-VL-2B-Instruct Q4_K_M language weights and Q8_0
vision projector from the checksum-verified [manifest](runtime-manifest.json).
CPU inference: four generation/batch threads, one server slot, 16,384 context
tokens, temperature 0, seed 0. Server startup and downloads are excluded from
runner elapsed time. Concurrent local workloads affect latency.

| Trial | Result | Interpretation |
| --- | --- | --- |
| Delta 01 | HTTP 503 during model loading | Startup sequencing error; no model investigation. |
| Delta 02 | Six MCP calls; `insufficient_evidence`; 164.594 s | Rejected by source review: arbitrarily chose an ambiguous identity, confused absent memo media with missing evidence. [Unedited report and review](../examples/local-delta-before-guard/REVIEW.md). |
| Delta 03 | One entity search; two invented-citation report rejections; 215.844 s before controlled stop | Identity policy prevented arbitrary investigation. Report formatting still failed. Motivated constraining clarification findings/citations. |
| Riverwatch 01 | Identity search and traversal; 182.609 s before controlled stop | Interrupted alongside Delta 03 to restart the pilot server. No analytic result or model-quality conclusion. |
| Delta 04 | One identity search, then `needs_clarification`; 50.532 s; zero report rejections | Identity behavior accepted by separate agent review. [Report and review](../examples/local-delta/REVIEW.md). Prose remains repetitive; guarded retest, not independent accuracy evidence. |
| Riverwatch 02 | Ten MCP calls, three invalid media-ID errors; 388.344 s before controlled stop | Model repeatedly supplied a file path where a source ID was required. Repaired with per-turn choices drawn from observed source IDs. No final analytic report. |
| Riverwatch 03 | Six successful MCP calls, including image retrieval; 501.109 s total; next model request reached its 300 s limit | No report accepted. Image encoding plus generation on the busy CPU exceeded the request budget. IDs/tool transport were correct. |
| Riverwatch 04 | 23 successful MCP calls; 1,200.344 s; timed out during action 24 | Retrieved the dependency records and PNG, then repeatedly reread unchanged sources. No video pixels or report accepted. Preserved trace motivated a generic one-read progress policy. |
| Riverwatch 05 | Eight successful MCP calls, including video frames at actual PTS 0/15/29; 746.281 s total; next model request exceeded 600 s | No valid ninth action or report returned. Repeat reads were prevented, but generation latency remained unacceptable for the configured request budget. |
| ClearAir 01 | Nine successful MCP calls; one report rejected for an invalid media locator; 373.328 s before controlled stop during retry | Exposed missing validation feedback in the separate synthesis context and overly broad media citation choices. No accepted report. The rejected draft was not saved by that version; its exact narrative cannot be reviewed. |
| ClearAir 02 | Nine successful MCP calls; runtime `complete`; 335.750 s; zero runtime rejections | Independent source review rejected a false conflict: both sources agree; provenance limitations are not contradictions. Main readiness finding and missing-media disclosure are supported. [Unedited report and review](../examples/local-clearair-rejected/REVIEW.md). |
| Riverwatch 06 | Fourteen successful MCP calls, including PNG and MP4; 993.610 s before controlled stop | Repeated identical searches expanded context and slowed inference; no report produced. Interrupted to apply lossless duplicate-result retention and clearer conflict rules. |
| Riverwatch 07 | Fourteen successful MCP calls; runtime `complete`; 1,044.422 s; one finish-intent rejection | Independent source review rejected incomplete supplier/shipping coverage, repeated conflict prose, and a video interpretation that reverses uncertainty into a factual denial. [Unedited report and review](../examples/local-riverwatch-rejected/REVIEW.md). |
| ClearAir 03 (Qwen3.5-4B) | Five successful MCP calls; runtime `complete`;174.515 s | Correct empty conflict/media lists and concise prose, but source review rejects absolute absence claims and invented coordination functions. [Unedited report and review](../examples/local-clearair-qwen35-rejected/REVIEW.md). |
| ClearAir 04 (Qwen3.5-4B, bounded report thinking) | Five successful MCP calls; runtime `complete`;287.781 s | Complete two-source inventory and improved dependency scope, but source review rejects “unrelated to delay” as stronger than “not evidence of delay,” and synthetic agreement described as verification. [Unedited report and review](../examples/local-clearair-thinking-rejected/REVIEW.md). |
| Riverwatch 08 (Qwen3.5-4B, bounded report thinking) | Twelve successful MCP calls; runtime `complete`;1,028.406 s; one finish-intent rejection | All nine connected records, both dated conflicts and four pixel transcriptions checked. Rejected: falsely claims the successfully inspected video has no raw media; omits actual missing inspection-tag pixels and sampling limits, and overstates a disputed readiness claim. [Unedited report and review](../examples/local-riverwatch-thinking-rejected/REVIEW.md). |
| Riverwatch 09 (Qwen3.5-4B, current-run provenance v8) | Twelve successful MCP calls; runtime `complete`;946.297 s; one finish-intent rejection | All nine connected sources and two dated conflicts retrieved. Corrected video availability, but source review rejects a document date asserted as visible in the15-second frame, omitted missing inspection-tag pixels, misleading modality limits and fictional physical follow-ups. [Unedited report and review](../examples/local-riverwatch-provenance-rejected/REVIEW.md). |
| Riverwatch 10 (Qwen3.5-4B, grounded media v9) | Seventeen successful MCP calls; runtime `complete`;1,372.782 s;23 actions and two finish-intent rejections | Four isolated observations preserved exactly and genuine media gaps disclosed. Source review still rejects summary treating disputed readiness as established and calling actual PNG/MP4 evidence text-only. Caption transcriptions match; minor footer-color description error retained. [Unedited report, observations and review](../examples/local-riverwatch-grounded-rejected/REVIEW.md). |
| Riverwatch 11 (Qwen3.5-4B, compact synthesis v10) | Seventeen successful MCP calls; runtime `complete`;988.485 s;23 actions and two finish-intent rejections | Compact context preserves all nine exact sources; shipping now explicitly distinguishes plans from receipt. Source review still rejects the summary treating unresolved readiness as established. [Unedited report, observations and review](../examples/local-riverwatch-compact-rejected/REVIEW.md). |
| Riverwatch 12 (Qwen3.5-4B, evidence overview v11) | Seventeen successful MCP calls; runtime `complete`;1,049.781 s;23 actions and two finish-intent rejections | Host overview correctly retains both readiness values and shipping plans. Source review rejects finding1's unqualified delayed-readiness conclusion; the supplier path is not explicitly synthesized. Other provenance/media/receipt qualifications hold. [Unedited report, observations and review](../examples/local-riverwatch-overview-rejected/REVIEW.md). |
| Riverwatch 13 (Qwen3.5-9B, unchanged v11) | Fifteen successful MCP calls; runtime `complete`;2,042.890 s;21 actions and two finish-intent rejections | Readiness now stays source-attributed. Rejected: "only a procedural delay" exceeds the evidence; the supplier path and explicit planned-arrival/no-receipt qualification remain incomplete. [Unedited report, observations and review](../examples/local-riverwatch-9b-rejected/REVIEW.md). |
| Riverwatch 14 (Qwen3.5-9B, generic guidance v12) | Fifteen successful MCP calls; runtime `complete`;2,538.563 s;21 actions and two finish-intent rejections | Separate source review accepts the known synthetic case: cited full supplier path, dated unresolved readiness, planned dates distinguished from receipt, and no unsupported exclusive cause. Imprecise shipping/arrival wording and cosmetic image-color shorthand retained and disclosed. [Unedited report, observations and review](../examples/local-riverwatch-guidance-accepted/REVIEW.md). |

The controlled stops saved `model_unavailable` because the owner stopped the
local server. They were not spontaneous server failures or exhausted deadlines.
Delta 03 and Riverwatch 01 overlapped on a single model slot, so their elapsed times include
queueing and are not isolated performance measurements. Only sanitized run
artifacts are retained; raw model conversation and image payloads are omitted.

Automated shape, identity, citation and media guards establish workflow
provenance. Independent source review is still needed for analytic meaning.
Do not report a technically accepted JSON report as automatically correct.

For Riverwatch 03 onward, server buffers were reduced: batch 512, microbatch 128,
Q8_0 key/value cache with flash attention enabled; context remains 16,384.
Riverwatch 02 ran under host memory pressure, with less than 1 GiB free during a
sample. Its server peak resident set across startup/preceding trials was about
3.80 GiB; this is not an isolated per-investigation memory measurement.

A separate media regression exposed fractional-seek rounding. The implementation
now records decoded source PTS and requested seek separately; seek 14.5 in the
fixture returns source frame 15. Earlier exact samples 0/14/27 remain unchanged.

Subsequent caption-media experiments cap image processing at 256 tokens per
image (minimum 64), reducing visual detail. The board uses large, simple text;
this setting is not qualified for small print, grounding, or natural-scene
analysis. A direct-pixel transcription probe excludes the authored annotation
from model input before retesting the full workflow. Request/run limits increased
to 600/1,200 seconds; this changes the latency budget, not the correctness gates.

The [direct-pixel probe](../evaluations/local-pilot/vision-probe-256.json) finished
in 11.609 seconds and reproduced every line of the board's text, checked against
the actual PNG. Only pixels and a generic transcription request reached the model;
the authored annotation was excluded. This is one simple caption-board check,
not an OCR benchmark. [Reproduction script](../evaluations/local-pilot/probe_vision.py).

Riverwatch 05 retained all prior results while excluding successful duplicate
source reads, media inspections and pixel reads from subsequent action choices.
Raw-media reads require an actual `available=true` inspection result. This is a
constrained planner, not an unconstrained model. Riverwatch 05 additionally used
an explicit concise-report question and a 1,800-second overall budget; its result
is evaluated separately from the earlier settings. During that run a sample
showed about 631 MiB host memory available; server working set was 2.02 GiB and
peak working set since server startup was 3.47 GiB. These are observations amid
other workloads, not an isolated peak-memory benchmark.

Independent guard review also found and repaired scope and timestamp defects:
a complete report must actually traverse its requested identity and cite sources
within the connected investigation scope; numeric video locators compare at the
decoder's microsecond precision. Adaptive video sampling permits new seek offsets
while still rejecting redundant reads. Such guards do not establish semantic truth.

The next runtime profile uses 12,288 context tokens, batch 256, microbatch 64,
the same Q8 key/value cache and 64/256 image-token limits. Context shifting is
disabled. Planning and report generation are separate so required-workflow
checks run before expensive report writing. Report synthesis retains actual tool
results, pixels and errors while omitting planner scaffolding. A subsequent fix
constrains media observations to audited source/locator pairs, passes safe rejection
feedback into synthesis, and preserves rejected parsed drafts separately from
accepted reports. Prior trial artifacts remain unchanged.

Riverwatch 07 adds exact-response deduplication: identical successful calls still
execute and remain in the trace, but the planner receives a reference to the
original retained result. Synthesis receives each unique response body once.
Different arguments, timestamps, results and errors remain distinct. A scoped
inventory-first workflow is explicitly requested; the trace records whether the
model follows it. Conflict instructions distinguish incompatible claims from
missing corroboration or media. These changes are development on known cases,
not an isolated experiment or a held-out evaluation.

Riverwatch 07 confirms that valid citations and actual media access do not make
the narrative correct. Its exact code/requirements/runtime manifest remain in
[the v6 snapshot](../evaluations/local-pilot/implementation-v6/README.md).
The actual-result inventory/edge-proof completion guard is implemented and tested;
it catches missing source coverage, not unsupported meaning.

A stronger free candidate is being evaluated after the 2B model's analytic
failures: [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B), quantized by
[Unsloth](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF), with pinned Q4_K_M
weights and F16 projector. Both repositories identify Apache-2.0. The
[candidate manifest](runtime-candidate-qwen35.json) records exact revisions,
published hashes and sizes. Successful download verification or upstream
benchmark scores are not project acceptance. Its separate launch profile uses
16,384 context tokens, eight CPU threads, and disabled thinking; this is a
changed model/runtime experiment, not an isolated guard comparison.

The initial thinking-enabled synthesis probe exhausted 6,144 output tokens in
668.641 seconds with no final answer. Its artifact records usage and a reasoning
presence flag, not reasoning text. The runner now offers an explicit report-only
thinking budget, with total output/time limits still enforced. Mechanical tests
verify request settings, recovery and privacy; only a completed source-reviewed
trial can establish analytic improvement.

ClearAir 04 uses a 1,024-token report-thinking budget, with unchanged non-thinking
planning. Its report response contained final JSON plus a reasoning-presence flag;
2,439 prompt and 1,422 completion tokens were recorded. Private reasoning text is
not saved. The independent AI source review still rejected the analysis. Numeric
usage demonstrates the bounded request completed, not that thinking improved
quality. Exact source files and fingerprints are retained in the
[v7 snapshot](../evaluations/local-pilot/implementation-v7/README.md).

Riverwatch 08 exposes a provenance distinction: an annotation's historical label
that no image/video was processed describes its authoring, while actual MCP
pixel calls establish what the current investigation inspected. Those two facts
must remain separate. Complete retrieval and correct transcription did not prevent
the report from contradicting its own media access. The original draft remains
unchanged; a subsequent generic synthesis-context repair will expose current-run
media facts explicitly. This remains development on inspected cases, not a held-out
comparison or a general reliability claim.

Riverwatch 09 shows that a factual provenance preamble alone does not prevent
cross-source contamination during synthesis. The opt-in grounded-media repair
separates pixel reading from document analysis: deferred isolated requests receive
only actual returned pixels and audited source/locator labels. Their exact outputs
become fixed report observations; actual-run limitations are constructed from
tool provenance, and declared-synthetic cases have no physical follow-up requests.
The model still chooses tools and authors findings/conflicts. This constrained
construction requires source review and is not evidence of general model accuracy.

Riverwatch10 confirms that separating pixel observation and provenance repairs
those fields without ensuring correct source synthesis. Its final request contained
10,129 prompt tokens and returned2,378 completion tokens, per backend usage;
reasoning presence is recorded, not its text. [A shared-host memory sample](../evaluations/local-pilot/resource-probe-riverwatch10.json)
records process working set and startup-inclusive peak; neither is a minimum RAM
specification or isolated performance benchmark.

The opt-in compact synthesis experiment retains one exact copy of each
actually returned full source record, differing versions, graph/identity results,
errors and audited media facts. Original pixels remain in planning and isolated
observation; the report phase receives their preserved observations. No unseen
sources or fixture answers are added. This changes context construction and
prompting; any improvement is not an isolated causal estimate.

Riverwatch11 reduced the report input from10,129 to4,640 backend-reported prompt
tokens;25 actual full-record occurrences became nine distinct exact records.
The source reviewer reconstructed the canonical report messages and matched their
16,929 bytes and saved hash against the frozen sources and actual trace. This
checks construction, not a persisted raw HTTP conversation. Original media
observations and current-run limitations still match. The shipping qualification
now explicitly says that no physical delivery is confirmed, but the model-authored
summary again treats the unresolved delayed claim as established. The result remains
rejected, with all original artifacts preserved. [Resource observation](../evaluations/local-pilot/resource-probe-riverwatch11.json).

The subsequent repair is a disclosed deterministic **evidence overview**:
summarize actual scope and exact supplied assertion disagreements with dates and
source IDs, leaving competing claims unresolved. This changes which report fields
the host constructs; it does not validate model-authored findings, resolve truth,
or relax separate source review. No case-specific answers or unseen records are
permitted in that construction.

Riverwatch12 confirms that this construction fixes the overview without validating
the model's findings. Its first finding again adopts delayed readiness without
acknowledging the unresolved ready claim in that conclusion. The report retrieves
the supplier chain but does not explicitly synthesize its second link. The
unchanged review protocol rejects the result; seven original artifacts are
preserved byte for byte. Independent reconstruction matches the1,333-byte overview
and18,579-byte compact messages, all nine eligible records and two supplied value
differences. [Shared-host resource observation](../evaluations/local-pilot/resource-probe-riverwatch12.json).

The pinned [9B candidate](runtime-candidate-qwen35-9b.json) is now installed
with both asset hashes and sizes verified. Eight focused installer checks pass;
the subsequent full suite passes 202 checks, zero skips, in 73.737 seconds.
Its [launch profile](../evaluations/local-pilot/runtime-profile-qwen35-9b-01.json)
disables repacking, uses memory mapping, and reduces batch/microbatch to 128/32.
This changes model, quantization, memory settings and time budget together;
results are not an isolated causal comparison.

A [source-only probe](../evaluations/local-pilot/qwen35-9b-source-probe.json)
completed in 65.578 seconds with 938 prompt and 87 completion tokens. The answer
retains both readiness claims and the external supplier, but its phrase
"sensor's actual defect" misleadingly suggests a defect the sources do not
establish. Separate review verified the three input records and request hash.
This narrow capacity signal does not qualify the analytic workflow.

The [capacity observation](../evaluations/local-pilot/qwen35-9b-capacity-probe.json)
records 5,654,065,152 resident bytes and 5,687,668,736 startup-inclusive peak bytes,
with 712,128 KiB host memory available after the probe. These are shared-host
observations, not minimum RAM requirements or evidence that a full media run fits.
Riverwatch13 completed on frozen v11 in 2,042.890 seconds, with a 2,700-second
overall budget and 1,200-second request limit. Final synthesis used 4,971 prompt
and 2,619 completion tokens. Separate review rejects an unsupported exclusive
explanation ("only a procedural delay") and incomplete supplier-path synthesis.
Readiness attribution and substantive pixel descriptions improved, but this is
not an accepted full analytic case. The [finished-run memory observation](../evaluations/local-pilot/resource-probe-riverwatch13-finished.json)
records an 8,305,934,336-byte startup-inclusive resident peak; the peak also
includes the earlier source-only probe. It is not a minimum RAM specification. Further
constraining analytical fields is not a substitute for demonstrating supported
model-authored findings and connections.

The v12 development change gives both synthesis contexts the same generic
instructions to answer all question parts, consolidate competing dated claims,
explain supported multi-hop paths with typed links and source evidence, avoid
unsupported exclusive alternatives, and distinguish forecasts from actual events.
It supplies no fixture names or answers and changes no schema or acceptance rule.
Riverwatch14 completed the full workflow with this change and passed separate
source review. All original reports remain unchanged. This is a tuned,
source-inspected development case, not a held-out result or a causal comparison.

Trial14 used 15 actual MCP calls, two isolated pixel requests and one final
synthesis, with two rejected premature finish intents. Reconstruction verifies
the 18,621-byte compact report messages and 1,333-byte host overview. The
[finished-run resource observation](../evaluations/local-pilot/resource-probe-riverwatch14-finished.json)
records an 8,305,934,336-byte process peak since server startup, including the
earlier probe and trial13. This shared-host observation is not a per-run memory
benchmark or minimum RAM requirement. The task-owned inference server was stopped
after the run; the static showcase needs no model process.

## Public text workflow: v13

The catalog integration is frozen before the first NCI trial in
[implementation-v13](../evaluations/public-pilot/implementation-v13/README.md).
Its 13 saved files, dataset, import manifest, fixed question, protocol and text
runtime profile are hash-bound. The full suite passes 245 tests, zero skips,
in 77.415 seconds; independent review verifies the frozen bindings and unchanged
legacy trial14 context. The public dataset and reviewer map remain separate from
model instructions; only the fixed question, ordinary tool descriptions and
actually retrieved evidence enter the run.

The [9B text profile](../evaluations/public-pilot/runtime-profile-qwen35-9b-text-01.json)
omits the projector and optional saved-prompt caches. A
[neutral context probe](../evaluations/public-pilot/context-probe-9b-01.json)
passes in 3.454 seconds: 35 preflight prompt tokens, 35 actual prompt tokens and
10 output tokens. It returns the expected boolean under a strict small schema.
Only counts, hashes, flags and safe metadata are retained. This verifies one
small endpoint/token-count path, not general fit, analytic quality or capacity.
The exact neutral request is preserved as a separately labeled reconstruction;
its canonical hash matches the original admission.

NCI01 failed before its tenth model decision after 2,049.031 seconds. Its
16,823-token prompt plus 512 output tokens and a 128-token safety margin exceeded
the 16,384-token slot. The harness refused the request without truncation; no
final report exists. Nine actual MCP calls include one rejected continuation
whose omitted scope/options did not match the first catalog page. Five complete
sources were read, including three of eight graph proof records. Inventory and
proof coverage remained incomplete. All nine completed preflight counts match
reported generation usage. The [failure review](../evaluations/public-pilot/public-nci-01/REVIEW.md)
preserves the originals and reconstructs all ten request hashes.

The [finished resource sample](../evaluations/public-pilot/resource-probe-nci01-finished.json)
records 5,026,734,080 resident bytes and a 5,087,371,264-byte peak including server
startup, the neutral probe and NCI01. It is a shared-host observation, not a
minimum RAM requirement or isolated benchmark. That server was stopped.

[Experiment v14](../evaluations/public-pilot/implementation-v14/README.md) retains
the same v13 code, evidence, question and acceptance criteria. It switches to
the pinned 4B Q4_K_M model, a 49,152-token slot and explicit larger run/request-byte
budgets. Multiple variables change; neither causal performance comparisons nor
analytic acceptance follow. Its [neutral probe](../evaluations/public-pilot/context-probe-4b48k-01.json)
passes in 1.656 seconds with 35 preflight and actual prompt tokens. This checks
only a small request; it does not qualify the expanded window or public analysis.

NCI02 reached report synthesis after 12 successful MCP calls and eight complete
ROR proof reads. Two terminal catalog chains establish only the inventories of
their requested scopes. No full Wikidata statement or crosswalk was read, so those
parts of the question remained unsupported. The report admission counted 15,363
prompt tokens plus 4,096 output tokens and a 128-token margin, within the 49,152
slot. Its 1,200-second request deadline expired; total run time was 4,859.516
seconds. There is no final response, report or ledger.

The [independent NCI02 review](../evaluations/public-pilot/public-nci-02/REVIEW.md)
reconstructs all 15 request hashes, confirms all 14 completed prompt counts match
their preflights, and verifies eight literal source fragments against the raw ROR
capture. The three original artifacts remain byte-exact. This is an execution
failure, with no public analytic acceptance. The
[resource observation](../evaluations/public-pilot/resource-probe-nci02-finished.json)
records a 4,383,703,040-byte process peak including startup and the neutral probe
on the shared host; it does not establish minimum RAM or a causal comparison.
The task-owned CPU inference server was stopped after the run.
