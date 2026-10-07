# Acceptance and limits

Project 1 must demonstrate a traceable analytic workflow: resolve a target, traverse its organizational context, retrieve relevant evidence, reconcile assertions, and produce a cited analytic product. Tool availability alone does not establish an end-to-end demonstration.

## Acceptance matrix

Status below describes the local prototype, not production readiness.

| Requirement | Acceptance evidence | Status |
| --- | --- | --- |
| Target resolution | Canonical names and aliases resolve; an ambiguous alias exposes candidates rather than silently choosing one. | Verified for exact, case-insensitive fixture aliases; ambiguity requires an explicit ID |
| Organizational traversal | Directed relationship paths retain edge types and provenance; depth limits hold and cycles terminate. | Verified for outgoing `contains`, `depends_on`, `supplied_by`, and explicit `reports_to` source assertions |
| Relevant retrieval | A target finds linked evidence without leaking unrelated records through substring alias matches. | Verified entity scope and unrelated-name decoy exclusion |
| Cross-structure evidence | One case retrieves organizational graph, structured records, and text through callable tools. | Verified in a live Codex/MCP investigation across graph, SQLite records, documents, and media |
| Media evidence | Image/video records identify the original media and the exact annotation, extraction, or observation used. Curated annotations are not raw-media understanding. | Live model observations of actual PNG pixels and MP4 frames at 0, 14, and 27 seconds independently checked against those pixels |
| Reconciliation | Conflicting dated claims remain visible with their respective source IDs and dates. A later claim is not automatically assumed true. | Verified for supplied assertion triples; automatic assertion extraction not implemented |
| Non-obvious connection | A seeded connection requires multiple relationship or evidence pivots; the product cites the supporting path and records. | Agent expanded traversal from depth 3 to 6, found the Riverwatch/component/supplier chain, and cited its implications; real-world novelty remains unmeasured |
| Analytic product | Conclusions are bounded by retrieved evidence; citations resolve to real source records. Missing evidence is stated explicitly. | Five findings, two dated conflicts, and four media observations independently reviewed against the fixture; missing media and scope limits stated |
| Agentic harness | A live model session invokes tools and produces the analytic product. A deterministic investigation function is a workflow baseline, not proof of agentic execution. | Historical Codex demonstration and one free local Riverwatch investigation pass separate AI source review; broader reliability unmeasured |
| Free reproduction | No paid account/API required to run the delivered agent workflow. Pinned model/runtime assets and install instructions supplied. | Free local ambiguity and one full synthetic analytic case pass separate review. Exact runtime/code/data/settings preserved; clean-device repetition and other platforms unqualified. Installer currently Windows ARM64 only |
| Dataset/question portability | Run a compatible external corpus and an explicit analytic question without changing code. Record corpus fingerprints. | Implemented in both runners; external-corpus routing and report/media provenance tested |
| Reduced manual pivots | Record the same-case manual baseline and agent tool trace, then compare analyst actions and elapsed time under a stated protocol. | Not yet measured |
| Reusable interfaces | Document tool contracts, stable entity/source IDs, relation direction, evidence locations, and adapter expectations for sibling projects. | P4 source-export adapter passes 12 checks plus 4 typed `reports_to` conformance checks through actual MCP; sibling model-analysis acceptance pending |

## Evaluation rules

- Synthetic case assertions test discovery against a known fixture. They do not estimate performance on real-world data.
- Retrieval coverage is the fraction of expected fixture evidence retrieved. It is not factual accuracy, confidence, or analytic completeness.
- Multiple records from the same underlying source do not establish independent corroboration. Counts are reported only as counts unless independence is established.
- A graph edge or shared supplier supports a connection, not an unobserved causal conclusion. Organizational reachability does not prove incident impact.
- Distinguish source observations, resolved identities, contradictions, and analyst inferences. Cite inferences to their premises and label uncertainty.
- Keep original media locations and timestamp/page/region locators when available. Do not describe hand-authored annotations as automatic image or video analysis.

## Current scope

Core resolution uses exact canonical IDs, names, and aliases. MCP entity search additionally offers substring candidates; traversal still requires an unambiguous target. Neither performs learned entity resolution. Text search uses case-insensitive lexical tokens and entity links supplied by the fixture. Graph traversal follows outgoing edges only; it does not ascend to parents or automatically pivot to siblings.

Conflict detection groups supplied `(subject, predicate, value)` assertions. Differing values are review candidates: they may reflect temporal change, scope differences, or a true contradiction. The host agent must read source dates and content before interpreting them.

The dataset includes authored image annotations and video transcripts. A separate media tool returns actual synthetic image pixels or requested decoded video frames. Frame sampling does not establish full-video coverage, and audio is not processed. Direct model inspection must be demonstrated separately from successful file decoding.

## Verification record

The free-runtime development record is maintained separately in
[local-validation.md](local-validation.md), including rejected and intentionally
interrupted trials. A citation-valid report can still fail source review.

After the local-runtime, coverage, grounded-media, evidence-overview, installer,
statement-projection, catalog recovery guidance, P4 typed source adapter and isolated Vulkan installer, the complete suite passed **268
tests, zero skips** (91.351 seconds on the shared development host). All seven
authored retrieval cases also passed. New checks cover real local HTTP/MCP
transport with scripted model responses, observed-source ID constraints, guarded
clarification, progress/failure artifacts, mid-run dataset changes, external
datasets, installer platform/hash boundaries, and actual decoded frame timestamps.
Additional checks cover connected investigation scope, fractional timestamp
precision, adaptive video sampling, cheap finish preflight, separate synthesis
budgets/context, inspected-only media schemas, rejection feedback/draft preservation,
lossless duplicate-result retention, immutable public-source capture/resume,
conservative offline import, actual-result scope inventories and full edge proofs.
Report-only reasoning tests check request bounds, unchanged planning/defaults,
failure recovery, numeric usage metadata and omission of private reasoning text.
Current-run facts tests separate historical authoring labels from actual returned
pixels, exclude failed/external calls, preserve original source context, and
distinguish no video inspection from sampled-frame coverage.
Thirteen grounded-media checks cover isolated actual-pixel input, exact source/locator order,
fixed dynamic provenance, action reservation/retry reuse, error artifacts, and reasoning/image
payload exclusion. Pinned backend schema compatibility was independently reviewed.
Eight compact-context checks verify exact actual records and variants, source-call
lineage, graph/identity results, retained errors, opt-in boundaries and source-free
metadata. Report-message hashes explicitly exclude the HTTP envelope/schema/settings.
These scripted transport checks do not estimate model reasoning quality.
After the full run, the catalog reminder was clarified to require a returned
full record before using an association as a pivot. Both affected actual HTTP/MCP
checks passed again (3.649 seconds, zero skips); independent review cleared the
final wording. No schema, guard or execution behavior changed in that clarification.

The installer includes a third pinned 9B candidate profile with hash-verified
assets. Its probe and trial13 retained semantic errors; trial14 passes separate
source review with disclosed wording/color caveats. See
[local validation](local-validation.md) for preserved failures and the exact scope
of that acceptance. All installer checks are included in the full suite above.

Ten evidence-overview checks cover exact supplied assertion variants, source dates,
quoted untrusted strings, missing/partial assertions, target-scope associations,
co-mentioned evidence and graph proofs, explicit out-of-scope exclusions, bounded
overflow, opt-in prerequisites, unchanged clarification and immutable complete
summaries. The host-constructed overview is disclosed separately from model findings.
Independent code review found and repaired an initial disconnected-record scope issue
before the live trial. This construction does not determine whether competing source
claims are true or validate the model's remaining analysis.

On 2026-10-06, all 34 tests passed with Python's `unittest` runner in the project virtual environment; none skipped. The 13 core checks include twelve using an independent temporary test corpus and one verifying exact evidence/conflict results across all seven showcase cases in `data/ground_truth.json`.

Checks cover ambiguity, exact aliases, depth boundaries, directed paths, cyclic graphs, entity scope, structured/text retrieval, out-of-scope edge proofs, dated conflicts, citation resolution, content hashes, unsupported inherited conclusions, evidence references, and path containment.

The MCP integration check starts the real server over stdio. Seven media checks verify source PNG pixels, whole-file media hashes, three distinct decoded video content regions, timestamp validation before decoding, beyond-duration rejection, missing decoder behavior, absent media, and path/format boundaries. These tests establish retrieval and decoding, not model interpretation of the media.

Thirteen report/runner checks cover retrieved citation IDs, media timestamp provenance,
required tool calls, report shape, rejected external tool fallback, sanitized traces,
target consistency, and abstention for unresolved identities. These checks do not
automatically establish semantic correctness of a cited claim.

Run from the project directory after installing dependencies and `ffmpeg`:

```sh
python -m unittest discover -s tests -v
```

## Live agent demonstration

On 2026-10-06, the Codex runner investigated `cbri` through the local MCP server. The preserved example is `examples/cbri/`, containing `report.json`, `report.md`, `tool-trace.json`, and `evidence-ledger.json`.

The trace records identity resolution, an initial depth-3 traversal, scoped search, expansion to depth 6, source reads, media availability checks, and source-pixel retrieval: 24 successful calls total. Fifteen evidence records were retrieved; the unrelated arts-event record `tbl-007` was excluded. The agent viewed the attached PNG and MP4 frames at 0, 14, and 27 seconds.

A separate agent reviewed all five findings, both dated conflicts, and all four media observations against source text, graph relationships, and independently decoded pixels. The 15 ledger entries' source locators, dates, and indexed-text hashes matched the current corpus. The report preserved uncertainty, limited the deployment concern to Riverwatch, and did not treat repeated synthetic captions as independent corroboration.

This validates one end-to-end demonstration. It does not measure broad accuracy, autonomous discovery on unfamiliar data, performance across repeated runs, or reduced analyst effort. The CLI used its default model selection; the exact model/version was not recorded. The saved trace omits raw tool results and media bytes, so it records the call sequence rather than a complete replay. Performance measurements and a held-out corpus remain future work.

A second live run with target `Delta` returned `needs_clarification` after one
entity-search call, naming both candidates without retrieving either entity's
evidence. See `examples/ambiguous-delta/`. Both saved reports passed the final
requested-target guard. Markdown presentation was regenerated to add direct media
links; model-authored report JSON and observed tool-call traces were preserved.

## Free local analytic demonstration

[Riverwatch14](../examples/local-riverwatch-guidance-accepted/REVIEW.md) completes
15 actual MCP calls and retrieves nine sources on frozen v12 with the pinned
Qwen3.5-9B Q3_K_M/F16 profile. The 2,538.563-second run follows the complete
Riverwatch → Silt Sensor Batch → Northline supplier path, keeps dated readiness
claims unresolved, distinguishes both planned arrival dates from confirmed
delivery, and avoids treating pending acceptance as proof of defects.

Four findings, two conflicts and actual PNG/MP4 observations pass separate AI
source review. The preserved report uses imprecise shipping-date wording for
expected arrival and cosmetic black-text shorthand for dark-green/white pixels;
the review discloses these without rewriting the model's output. Northline's
external status is not stated, but no ownership/control inference is made.
Host-authored overview/provenance fields are distinguished from model analysis.

This qualifies one tuned, known synthetic investigation. It does not establish
held-out accuracy, repeatability, natural-scene understanding, public-data quality,
human analyst-time savings or clean-device reproduction. Previous failures remain
part of the evidence. Software tests and source review answer different questions.

## Public retrieval preparation

The separate [statement projection](public-statements.md) preserves 154 indexed
source/decision units and the original capture. Ten focused tests pass; separate
review verified literal source fragments, qualification preservation and crosswalk
decision lineage. The [metadata catalog](evidence-catalog.md) passes 19 focused
checks, including actual snapshot-bound cursor-chain validation and refusal of
incomplete discovery. Neither metadata discovery nor a complete catalog grants
citation or edge-proof credit.

The opt-in MCP/agent workflow is now frozen in
[v13](../evaluations/public-pilot/implementation-v13/README.md). Thirteen shared
workflow checks, 22 context-admission checks and eight local transport checks
cover selective reads, actual catalog chains, citation separation, token/byte
bounds and response deadlines. The full 245-test suite passes; independent review
also reconstructs the accepted legacy trial14 context byte-for-byte. The backing
workspace still loads/scans its corpus; this is not a scalable storage benchmark.

The earlier immutable source-v1 package preserves the 202-test implementation;
later v13 work is separate. The [public NCI protocol](../evaluations/public-pilot/PROTOCOL.md)
is fixed for a known, inspected development case. A
[neutral live context probe](../evaluations/public-pilot/context-probe-9b-01.json)
matches 35 preflight tokens to 35 reported prompt tokens and returns the expected
boolean. That narrow compatibility check establishes neither public analytic
acceptance nor capacity. Held-out accuracy, human-gold labeling and larger-scale
capacity remain unqualified.

The first public model trial, [NCI01](../evaluations/public-pilot/public-nci-01/REVIEW.md),
made nine MCP calls and five complete source reads before its tenth decision
exceeded the configured context allowance. The runner stopped before generation;
it produced no report. All ten request hashes reconstruct exactly. The original
failure, metadata and trace are preserved with a separate review. A
[v14 profile experiment](../evaluations/public-pilot/implementation-v14/README.md)
keeps the harness, question, sources and review protocol fixed while changing the
model, context and run budgets. [NCI02](../evaluations/public-pilot/public-nci-02/REVIEW.md)
failed at the report deadline after 4,859.516 seconds. Its 12 successful MCP calls
read all eight required ROR relationship proofs and completed two catalog inventories,
but read no full Wikidata statements or crosswalks. The report request fit its
configured context allowance; no final response, report or ledger was produced.
Independent replay verifies all 15 request hashes and the original failure records.
Structural coverage is not question-wide analytic adequacy. Neither public trial
passes analytic acceptance; the changed settings are not a controlled comparison.
