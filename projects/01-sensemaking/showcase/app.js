"use strict";

let content;
let currentCase;
let activePanel = "report";
const $ = (id) => document.getElementById(id);
function groundingForCase() { return currentCase.metadata.grounded_media?.enabled ? currentCase.metadata.grounded_media : null; }
function compactForCase() { return currentCase.metadata.compact_synthesis?.enabled ? currentCase.metadata.compact_synthesis : null; }
function evidenceSummaryForCase() { return currentCase.metadata.evidence_summary?.enabled ? currentCase.metadata.evidence_summary : null; }
function datasetForCase() { return content.datasets[currentCase.dataset_id]; }
function evidenceForCase() { return datasetForCase().evidence; }
function isFailureCase() { return currentCase.artifact_kind === "failure"; }
function toolAvailabilityForCase() {
  return currentCase.metadata.retrieval_profile === "catalog" && currentCase.metadata.engine === "local"
    ? "The MCP server exposes six read-only tools; this saved local catalog profile enables five tool types and disables raw pixel reads. Metadata discovery and full source reads remain separate."
    : "The MCP server exposes six read-only tools. The saved trace records which calls this case actually used.";
}
const compactExplanation = "Compact report input retained each exact retrieved record once, preserving differing versions, identity/graph results and tool errors. The final synthesis reused any recorded isolated observations instead of raw pixel blocks; any returned pixels remained available to the original planner. This construction policy does not establish analytic correctness.";
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function link(label, href, download = false) {
  const node = element("a", label);
  node.href = href;
  if (download) node.download = href.split("/").at(-1);
  return node;
}
function links(items) {
  const row = element("div", null, "artifact-links");
  for (const [label, href, download] of items) if (href) row.append(link(label, href, download));
  return row;
}
function list(items) {
  const node = element("ul");
  for (const item of items) node.append(element("li", item));
  return node;
}
function label(text) { return element("p", text, "section-label"); }
function sourceButton(id, style = "source-chip") {
  const button = element("button", id, style);
  button.type = "button";
  button.setAttribute("aria-label", `Inspect source ${id}`);
  button.addEventListener("click", () => openSource(id));
  return button;
}
function citations(ids) {
  const row = element("div", null, "citations");
  for (const id of ids) row.append(sourceButton(id));
  return row;
}
function sideCard(title, text) {
  const card = element("section", null, "side-card");
  card.append(element("h3", title));
  if (text) card.append(element("p", text));
  return card;
}
function fact(value, name) {
  const node = element("div", null, "stat");
  node.append(element("strong", value), element("span", name));
  return node;
}
function keyValue(name, value) {
  const node = element("div", null, "metadata-pair");
  node.append(element("span", name), element("strong", value));
  return node;
}
function formatSeconds(value) {
  return Number.isFinite(value) ? `${value.toLocaleString("en-US", {maximumFractionDigits: 3})}s` : "—";
}

function selectCase(id, updateHash = true) {
  currentCase = content.cases.find((item) => item.id === id) || content.cases.find((item) => item.id === content.default_case);
  $("case-select").value = currentCase.id;
  $("tab-report").textContent = isFailureCase() ? "Failure record" : "Report";
  $("tab-evidence").textContent = isFailureCase() ? "Recorded reads" : "Evidence ledger";
  const report = currentCase.report;
  $("case-title").textContent = isFailureCase() ? currentCase.title : report.title;
  $("engine-label").textContent = currentCase.engine;
  $("review-label").textContent = currentCase.review_label;
  $("review-label").className = `outcome ${currentCase.review_state}`;
  $("case-facts").replaceChildren(
    fact(currentCase.trace.length, "MCP calls"),
    fact(isFailureCase() ? currentCase.failure_summary.full_read_calls : currentCase.ledger.length, isFailureCase() ? "Recorded full-read calls" : "Ledger sources"),
    fact(formatSeconds(currentCase.metadata.elapsed_seconds), "Recorded duration")
  );
  const warning = isFailureCase()
    ? (currentCase.failure.code === "context_token_limit"
      ? "Execution stopped at the context limit; no analytic report or final citation ledger. Captured source assertions remain unverified."
      : currentCase.failure.code === "model_timeout"
        ? `${currentCase.failure_summary.phase === "report" ? "Report generation" : "Local model request"} timed out; no analytic report or final citation ledger. Captured source assertions remain unverified.`
      : "Execution stopped before an analytic report; no final citation ledger. Captured source assertions remain unverified.")
    : currentCase.review_state === "rejected"
    ? `Rejected analysis. ${currentCase.review_note} The original report is preserved below; its “complete” status records runtime acceptance, not analytic correctness.`
    : currentCase.engine_kind === "historical"
      ? "Optional historical Codex run. This does not demonstrate free local execution. The exact model was not recorded."
      : report.status === "needs_clarification"
        ? "Guarded identity behavior only. This is not a completed free-local analytic investigation."
        : report.status === "complete" && currentCase.review_state === "accepted"
          ? `This saved free-local analytic case passed the recorded separate AI source review. It remains one ${datasetForCase().kind === "synthetic" ? "synthetic development" : "captured public-source"} case, not a human or general-accuracy benchmark.`
          : "Saved free-local investigation. Read the separate source-review outcome; runtime acceptance alone does not establish correctness or general accuracy.";
  $("case-warning").textContent = isFailureCase() ? warning : `${warning} ${datasetForCase().note}`;
  $("case-warning").className = `notice ${currentCase.review_state}`;
  renderReport();
  renderTrace();
  renderEvidence();
  renderImplementation();
  $("view-announcement").textContent = `${currentCase.label}. ${currentCase.review_label}.`;
  if (updateHash) history.replaceState(null, "", `#${encodeURIComponent(currentCase.id)}/${activePanel}`);
}

function renderReport() {
  if (isFailureCase()) { renderFailure(); return; }
  const report = currentCase.report;
  const grounding = groundingForCase();
  const compact = compactForCase();
  const summaryConstruction = evidenceSummaryForCase();
  const hostSummary = summaryConstruction?.final_summary_constrained;
  const layout = element("div", null, "report-grid");
  const main = element("div");
  main.append(element("p", "Original saved report · presentation only; wording unchanged", "eyebrow"));
  main.append(element("p", hostSummary ? "Overview: host-constructed · Findings and conflicts: model-authored" : "Summary, findings and conflicts: model-authored", "small"));
  if (grounding || compact) {
    const construction = element("details", null, "review-block");
    construction.append(element("summary", "How this report was constructed"));
    if (grounding) construction.append(element("p", `The agent chose tools and authored ${hostSummary ? "findings, conflicts and qualifications. The host constructed the summary from retrieved supplied assertions and recorded scope" : "the summary, findings, conflicts and qualifications"}. ${grounding.observations.length ? "Media observations were fixed from isolated pixel-only model outputs" : "No pixel-only outputs were recorded; the host fixed media observations to an empty list"}; the host supplied provenance limitations. Exact reuse is a consistency check, not semantic acceptance.`));
    if (compact) construction.append(element("p", compactExplanation));
    main.append(construction);
  }
  if (hostSummary) {
    const overview = element("details", null, "review-block");
    overview.append(element("summary", "Host-constructed evidence overview"), element("p", "The software composed this overview from supplied assertion fields in retrieved records. Differing values remain unresolved; they are not independently extracted or verified facts. The model did not author this summary.", "panel-intro"), element("p", report.summary, "report-summary"));
    main.append(overview);
  } else main.append(element("p", report.summary, "report-summary"));
  main.append(label(`Findings / ${report.findings.length}`));
  if (!report.findings.length) main.append(element("p", "The original report records no analytic findings.", "empty"));
  report.findings.forEach((finding, index) => {
    const item = element("article", null, "finding");
    item.append(element("div", String(index + 1).padStart(2, "0"), "number"));
    item.append(element("p", finding.claim));
    if (finding.qualification) item.append(element("p", finding.qualification, "qualification"));
    item.append(citations(finding.evidence_ids));
    main.append(item);
  });
  main.append(label(`Recorded conflicts / ${report.conflicts.length}`));
  if (!report.conflicts.length) main.append(element("p", "The original report lists no conflicts. See review outcome before interpreting this as complete coverage.", "panel-intro"));
  for (const conflict of report.conflicts) {
    const item = element("article", null, "finding");
    item.append(element("h3", `${conflict.subject} / ${conflict.predicate}`), element("p", conflict.description), citations(conflict.evidence_ids));
    main.append(item);
  }
  main.append(label(`Media observations / ${report.media_observations.length}`));
  if (grounding?.observations.length) main.append(element("p", "These strings are preserved exactly from separate pixel-only model responses, in their recorded order. The final synthesis could not rewrite them. Original observation files and source/call lineage are available below.", "panel-intro"));
  if (!report.media_observations.length) main.append(element("p", "No pixel observations in this report. Indexed captions and transcripts are source text, not proof of media inspection.", "panel-intro"));
  for (const observation of report.media_observations) {
    const item = element("article", null, "finding");
    item.append(element("div", observation.locator, "number"), element("p", observation.observation), citations([observation.evidence_id]));
    main.append(item);
  }
  const aside = element("aside", null, "report-aside");
  const outcome = sideCard("Two separate checks", currentCase.review_note);
  outcome.append(keyValue("Runtime", currentCase.runtime_label), keyValue("Source review", currentCase.review_label));
  outcome.append(links([["Read review record", currentCase.artifacts.review]]));
  aside.append(outcome);
  const originals = sideCard("Original artifacts", "The report JSON, call trace and ledger are copied byte for byte. The selected run summary is an explicit metadata extract. Companion source documents retain some links to repository-only files outside this package.");
  originals.append(links([["Report JSON ↓", currentCase.artifacts["report.json"], true], ["Report Markdown ↓", currentCase.artifacts["report.md"], true], ["Call trace ↓", currentCase.artifacts["tool-trace.json"], true], ["Ledger ↓", currentCase.artifacts["evidence-ledger.json"], true], ["Run summary ↓", currentCase.artifacts.run_summary, true]]));
  originals.append(links([["Unavailable document links", "document-link-audit.json"]]));
  aside.append(originals);
  if (grounding) aside.append(groundingCard(grounding));
  if (compact) aside.append(compactCard(compact));
  if (summaryConstruction) aside.append(evidenceSummaryCard(summaryConstruction));
  const limits = sideCard(grounding ? "Host-derived provenance limitations" : "Report limitations", grounding ? "Recorded constrained field. The host constructed these from current-run provenance; they are not independent model-authored conclusions." : null);
  limits.append(list(report.limitations));
  aside.append(limits);
  const fixedFollowup = grounding?.constrained_fields.includes("follow_up");
  const followup = sideCard(fixedFollowup ? "Synthetic follow-up policy" : "Report's proposed follow-up", fixedFollowup ? "The host fixed follow_up to an empty list for this synthetic case; no model recommendations are claimed here." : "Original model suggestions; rejected cases may contain inappropriate follow-ups. Review them before use.");
  followup.append(list(report.follow_up));
  aside.append(followup);
  layout.append(main, aside);
  $("panel-report").replaceChildren(layout);
}

function failureDownloads() {
  return links([["Original failure JSON ↓", currentCase.artifacts["failure.json"], true],
    ["Original trace ↓", currentCase.artifacts["tool-trace.json"], true],
    ["Original run metadata ↓", currentCase.artifacts["run-metadata.json"], true],
    ["Original review ↓", currentCase.artifacts.review, true],
    ["Filtered run summary ↓", currentCase.artifacts.run_summary, true]]);
}

function failureContextCard() {
  const context = currentCase.failure_summary.context_admission;
  const card = sideCard("Recorded context admission", "Allowlisted measurements from the final saved preflight. They describe the final recorded request, not a generated analysis or independently measured model capacity.");
  if (!context) { card.append(element("p", "No context-admission measurements were saved.")); return card; }
  for (const [key, title] of [["prompt_tokens", "Prompt tokens"], ["max_tokens", "Reserved generation tokens"], ["safety_margin", "Safety margin"], ["reserved_tokens", "Total requested allowance"], ["token_limit", "Explicit token limit"], ["remaining_tokens", "Remaining token allowance"], ["generation_request_bytes", "Serialized request bytes"], ["max_request_bytes", "Request byte limit"]]) {
    if (context[key] !== undefined) card.append(keyValue(title, context[key]));
  }
  card.append(element("p", `Preflight admitted: ${context.admitted ? "yes" : "no"}. Exact model fit remains unverified. No rendered prompt or token array is displayed.`, "small"));
  return card;
}

function renderFailure() {
  const layout = element("div", null, "report-grid");
  const main = element("div");
  main.append(element("p", "Original execution failure · no analytic report", "eyebrow"), element("h3", "Stopped without an analytic report"),
    keyValue("Failure code", currentCase.failure.code), element("p", currentCase.failure.message, "report-summary"),
    element("p", "This is the original runtime error, not a model-authored finding. The run produced no analytic report or final citation ledger. Source claims were not adjudicated by this failure."),
    keyValue("Last recorded phase", currentCase.failure_summary.phase));
  const review = element("details", null, "review-block");
  review.append(element("summary", "Read the original failure review"), element("pre", currentCase.review_text, "review-document"));
  main.append(review);
  const aside = element("aside", null, "report-aside");
  aside.append(sideCard("Execution review", currentCase.review_note), failureContextCard());
  const originals = sideCard("Original failure artifacts", "Failure JSON, trace, reviewed run metadata and review are copied byte for byte. The metadata download is explicitly pinned to its reviewed hash; the on-screen summary uses only allowlisted fields. No report or ledger download is invented.");
  originals.append(failureDownloads());
  aside.append(originals);
  layout.append(main, aside);
  $("panel-report").replaceChildren(layout);
}

function groundingCard(grounding) {
  const card = sideCard("Isolated pixel observations", "Only successful isolated outputs are published. Their file hashes and exact concatenation into the final report were verified during packaging.");
  card.append(keyValue("Constrained report fields", grounding.constrained_fields.join(", ")));
  if (!grounding.observations.length) card.append(element("p", "No successful raw-media calls or isolated outputs were recorded."));
  for (const record of grounding.observations) {
    const item = element("details", null, "review-block");
    item.append(element("summary", `MCP call ${record.call} · ${record.evidence_id}`));
    item.append(keyValue("Recorded returned locators", record.locators.join(", ")));
    item.append(keyValue("Output SHA256 · verified", record.output_sha256));
    item.append(keyValue("Input SHA256 · recorded", record.input_sha256));
    item.append(links([["Original observation JSON ↓", currentCase.artifacts[record.path], true]]));
    item.append(sourceButton(record.evidence_id));
    card.append(item);
  }
  card.append(element("p", "Input fingerprints identify the recorded pixel-only requests. Those request bodies, image encodings and private reasoning are not packaged. The builder does not reconstruct inputs or re-run semantic review.", "small"));
  return card;
}

function compactCard(compact) {
  const card = sideCard("Compact report input", "Recorded construction metrics for each synthesis attempt. Hashes and counts are not independently reconstructed or verified by this viewer.");
  compact.generations.forEach((generation, index) => {
    const item = element("details", null, "review-block");
    item.append(element("summary", `Report generation ${index + 1} · action ${generation.step}`));
    item.append(keyValue("Construction policy", generation.policy));
    item.append(keyValue("Canonical message bytes · recorded", generation.input_bytes.toLocaleString("en-US")));
    item.append(keyValue("Message SHA256 · recorded", generation.input_sha256));
    for (const [key, name] of [["mcp_calls", "MCP calls"], ["evidence_occurrences", "Retrieved record occurrences"],
      ["evidence_records", "Distinct exact records"], ["duplicate_evidence_records", "Exact repeats removed"],
      ["identity_graph_results", "Identity/graph results"], ["tool_failures", "Tool failures retained"],
      ["omitted_raw_image_blocks", "Raw image blocks omitted from report input"]]) {
      item.append(keyValue(name, generation.counts[key]));
    }
    card.append(item);
  });
  card.append(element("p", "Fingerprint scope: canonical report messages only. Response schema, generation settings and the full HTTP request are outside that hash. Original request/context bodies and private reasoning are not packaged; these numbers are not token counts or a performance benchmark.", "small"));
  return card;
}

function evidenceSummaryCard(construction) {
  const card = sideCard("Summary construction", construction.final_summary_constrained
    ? "The final summary is a host-constructed field. Packaging verified its UTF-8 byte count and SHA256 against the last recorded construction. That proves content identity, not analytic correctness."
    : "Evidence-summary mode was requested, but this final report is not complete. Its summary remains model-authored; any earlier complete-report construction below is a prior attempt.");
  card.append(keyValue("Construction policy", construction.policy));
  construction.generations.forEach((generation, index) => {
    const item = element("details", null, "review-block");
    item.append(element("summary", `Summary construction ${index + 1} · action ${generation.step}`));
    item.append(keyValue("Author", "Host software"), keyValue("Intended report status", generation.status));
    const finalVerified = construction.final_summary_hash_verified && index === construction.generations.length - 1;
    item.append(keyValue(`Summary bytes · ${finalVerified ? "verified against final report" : "recorded"}`, generation.summary_bytes));
    item.append(keyValue(`Summary SHA256 · ${finalVerified ? "verified against final report" : "recorded"}`, generation.summary_sha256));
    for (const [key, name] of [["source_ids", "Scope-eligible source IDs"], ["record_versions", "Eligible exact record versions"],
      ["comparable_assertions", "Comparable assertions in eligible records"], ["ignored_assertions", "Ignored entries in eligible records"],
      ["records_without_assertions", "Eligible records without assertions"], ["differing_groups", "Eligible groups with differing values"]]) {
      item.append(keyValue(`${name} · recorded`, generation.counts[key]));
    }
    card.append(item);
  });
  card.append(element("p", "Counts are recorded construction metrics for records admitted by the host's scope rules, not independently reconstructed by this viewer. They describe supplied assertion fields, not all retrieved records or all disagreements in source prose. Other retrieved records remained available to the analyst model. Source/scope lineage, candidate-group arrays, request bodies and private reasoning are excluded from the published metadata extract.", "small"));
  return card;
}

const toolDescriptions = {
  entity_search: "Resolve the requested name or expose ambiguous candidates.",
  traverse_relationships: "Follow the recorded directed graph to the requested depth.",
  search_evidence: "Retrieve matching evidence using the recorded query and entity scope.",
  catalog_evidence: "Discover bounded source metadata. Only an actual complete terminal cursor chain establishes inventory; metadata is not retrieved source content or citation proof.",
  read_evidence: "Read the full indexed source record.",
  inspect_media: "Check source-media availability and metadata; this is not pixel inspection.",
  read_media: "Retrieve original image pixels or decoded video frames. Arguments are requested seeks, not necessarily returned frame timestamps."
};
function renderTrace() {
  const panel = $("panel-trace");
  panel.replaceChildren(element("p", content.replay_note, "trace-intro"));
  panel.append(element("p", "This is the actual saved order, including repeated calls. Expand a step to inspect its exact arguments. It contains no private model reasoning. Model finish intents and report-generation actions are not MCP tool calls.", "trace-intro"));
  const ordered = element("ol", null, "trace-list");
  currentCase.trace.forEach((call) => {
    const row = element("li");
    const details = element("details");
    const summary = element("summary");
    summary.append(element("strong", call.name), element("span", call.status, "call-status"));
    const body = element("div", null, "trace-detail");
    body.append(element("p", toolDescriptions[call.name] || "Recorded tool invocation."), element("pre", JSON.stringify(call.args, null, 2)));
    if (call.args.evidence_id && evidenceForCase()[call.args.evidence_id]) body.append(sourceButton(call.args.evidence_id));
    details.append(summary, body);
    row.append(details);
    ordered.append(row);
  });
  panel.append(ordered, links([["Download original trace", currentCase.artifacts["tool-trace.json"], true]]));
}

function renderEvidence() {
  const panel = $("panel-evidence");
  if (isFailureCase()) {
    panel.replaceChildren(element("p", "Recorded retrieval bookkeeping · no final citation ledger", "eyebrow"), element("p", currentCase.failure_summary.retrieval_note, "panel-intro"), element("p", currentCase.dataset_binding.note, "small"));
    for (const id of currentCase.failure_summary.recorded_retrieved_ids) {
      const row = element("article", null, "finding");
      row.append(sourceButton(id, "text-button"), element("p", evidenceForCase()[id].title), element("p", "Recorded full read; not a citation or final ledger entry.", "small"));
      panel.append(row);
    }
    panel.append(failureDownloads(), links([["Inspect dataset graph", datasetForCase().graph_url], ["Capture manifest", datasetForCase().capture_url], ["Import manifest", datasetForCase().import_url]]));
    return;
  }
  panel.replaceChildren(element("p", "Saved source ledger, compared with this case's packaged dataset. A matching hash establishes content identity; it does not establish that the interpretation is correct or that sources are independent.", "panel-intro"), element("p", currentCase.dataset_binding.note, "small"));
  if (!currentCase.ledger.length) {
    panel.append(element("p", "The saved ledger contains no retrieved sources.", "empty"));
    return;
  }
  const wrapper = element("div", null, "table-wrap");
  const table = element("table");
  const header = element("tr");
  for (const name of ["Source", "Saved locator / date", "Content verification"]) header.append(element("th", name));
  const head = element("thead");
  head.append(header);
  const body = element("tbody");
  for (const entry of currentCase.ledger) {
    const source = evidenceForCase()[entry.id];
    const verification = currentCase.source_verification.find((item) => item.id === entry.id);
    const row = element("tr");
    const first = element("td");
    first.append(sourceButton(entry.id, "text-button"), element("small", source.title));
    const locator = element("td", entry.source);
    locator.append(element("small", entry.date));
    const verified = element("td", verification.text_matches ? "Indexed text hash matches" : "WARNING: indexed text differs");
    if (verification.media_matches !== null) verified.append(element("small", verification.media_matches ? "Raw media hash matches" : "WARNING: raw media differs"));
    verified.append(element("small", entry.sha256));
    row.append(first, locator, verified);
    body.append(row);
  }
  table.append(head, body);
  wrapper.append(table);
  panel.append(wrapper, links([["Download original ledger", currentCase.artifacts["evidence-ledger.json"], true], ["Inspect dataset graph", datasetForCase().graph_url], ["Structured records CSV", datasetForCase().records_url], ["Capture manifest", datasetForCase().capture_url], ["Import manifest", datasetForCase().import_url]]));
}

function processStep(number, title) {
  const node = element("section", null, "process-step");
  node.append(element("p", `${number} / ${title}`, "eyebrow"));
  return node;
}
function renderImplementation() {
  const grounding = groundingForCase();
  const compact = compactForCase();
  const summaryConstruction = evidenceSummaryForCase();
  const hostSummary = summaryConstruction?.final_summary_constrained;
  const layout = element("div", null, "implementation-grid");
  const main = element("div");
  const problem = processStep("01", "Problem");
  problem.append(element("h3", "Make the path from question to evidence inspectable."), element("p", "Project 1 asks an agent to resolve an entity, traverse organizational relationships, reconcile evidence across data structures and media, and produce a cited analysis. These saved cases expose both the working path and the failures."));
  main.append(problem);
  const prompting = processStep("02", "User direction");
  prompting.append(element("p", "Verbatim excerpts from the recorded design decisions. Consequences below are documented summaries, not reconstructed dialogue."));
  for (const prompt of content.prompts) {
    const row = element("div", null, "prompt-row");
    row.append(element("blockquote", prompt.excerpt), element("p", prompt.consequence));
    prompting.append(row);
  }
  prompting.append(links([["Full decision record", "artifacts/docs/decisions.md"], ["EAD Implementation reference", "https://boomerrawlings.com/ead"]]));
  main.append(prompting);
  const decision = processStep("03", "Implementation decision");
  decision.append(element("h3", "Keep identity, evidence and interpretation separate."), element("p", `${toolAvailabilityForCase()} ${isFailureCase() ? "The agent chose calls, but this run stopped before an analytic report. A separate AI review examined its execution and source provenance." : "The agent chooses calls and writes a report; guards check identity, source access and workflow provenance. A separate AI review checks the claims against the sources."} Free local execution is evaluated independently from optional Codex examples.`));
  if (grounding) decision.append(element("p", `${grounding.observations.length ? "Dedicated pixel-only model calls produced the media observations. The final synthesis had to reuse them exactly" : "No pixel-only outputs were recorded. The final synthesis had to retain an empty media-observation list"}, accept host-derived provenance limitations, and obey the recorded constrained fields. The main agent still chose the tools and authored ${hostSummary ? "findings, conflicts and qualifications; the host constructed the summary from supplied retrieved assertions and recorded scope" : "the substantive summary, findings, conflicts and qualifications"}.`));
  if (compact) decision.append(element("p", compactExplanation));
  decision.append(links([["Tool contracts", "artifacts/docs/integration.md"], ["Scaling plan and current limits", "artifacts/docs/scaling.md"], ["Review protocol", datasetForCase().review_protocol_url]]));
  main.append(decision);
  const validation = processStep("04", "Validation & learning");
  validation.append(element("h3", currentCase.review_label), element("p", currentCase.lesson), element("p", currentCase.review_note));
  const review = element("details", null, "review-block");
  review.append(element("summary", "Read the original review/acceptance document"), element("pre", currentCase.review_text, "review-document"));
  validation.append(review, links([["Review source file", currentCase.artifacts.review], ["Local validation history", "artifacts/docs/local-validation.md"]]));
  main.append(validation);
  const result = processStep("05", "Artifact");
  result.append(element("h3", "Preserve the result, including its limitations."), element("p", isFailureCase() ? "Original failure, actual call trace, reviewed metadata and execution review are available for scrutiny. No report or final citation ledger was produced. This viewer cannot resume the run or verify a new organization." : "Original saved report JSON, actual tool sequence and saved evidence ledger are available for scrutiny. This viewer presents recorded work; it cannot execute an investigation or verify a new organization."));
  result.append(isFailureCase() ? failureDownloads() : links([["Original report JSON ↓", currentCase.artifacts["report.json"], true], ["Original trace ↓", currentCase.artifacts["tool-trace.json"], true], ["Original ledger ↓", currentCase.artifacts["evidence-ledger.json"], true]]));
  main.append(result);
  const aside = element("aside");
  const question = sideCard("This run's recorded input");
  if (currentCase.metadata.question) question.append(element("p", "Exact question from the saved run metadata:"), element("pre", currentCase.metadata.question));
  else question.append(element("p", currentCase.question_note || "No exact question text is available in the saved artifacts."));
  question.append(keyValue("Target", currentCase.metadata.requested_target || currentCase.report?.target), keyValue("Engine", currentCase.engine));
  if (currentCase.metadata.prompt_sha256) question.append(keyValue("Saved prompt SHA256", currentCase.metadata.prompt_sha256));
  question.append(element("p", "A prompt hash is not the prompt text. Current templates are not presented as historical prompts.", "small"));
  aside.append(question);
  if (grounding) aside.append(groundingCard(grounding));
  if (compact) aside.append(compactCard(compact));
  if (summaryConstruction) aside.append(evidenceSummaryCard(summaryConstruction));
  if (isFailureCase()) aside.append(failureContextCard());
  const measures = sideCard("What the numbers mean", "Call/source counts come from saved artifacts. Duration is one development run on a busy host; a dash means it was not recorded. These are not comparative performance benchmarks.");
  if (currentCase.metadata.retrieval_profile === "catalog") {
    const successful = (name) => currentCase.trace.filter((call) => call.name === name && call.status === "completed").length;
    measures.append(keyValue("Successful catalog calls", successful("catalog_evidence")), keyValue("Successful full-record read calls", successful("read_evidence")), element("p", `Counts come from the saved call trace. Catalog calls return metadata, not source bodies; these counts alone do not establish a complete cursor chain or sufficient evidence. ${isFailureCase() ? "Only bounded failure-context measurements are displayed separately." : "Context-admission metrics are not included in this public metadata extract."}`, "small"));
  }
  measures.append(element("p", content.review_note), element("p", datasetForCase().note), keyValue("Dataset", datasetForCase().name), keyValue("Dataset SHA256", datasetForCase().sha256), element("p", currentCase.dataset_binding.note));
  aside.append(measures);
  layout.append(main, aside);
  $("panel-implementation").replaceChildren(layout);
}

function openSource(id) {
  const source = evidenceForCase()[id];
  if (!source) return;
  const body = $("source-content");
  const title = element("h2", source.title);
  title.id = "source-title";
  const ledger = currentCase.ledger?.find((item) => item.id === id);
  const verification = currentCase.source_verification?.find((item) => item.id === id);
  body.replaceChildren(title, element("p", `${id} · ${source.kind} · ${source.date}`, "muted"));
  body.append(element("p", isFailureCase() ? (currentCase.failure_summary.recorded_retrieved_ids.includes(id) ? "Recorded in run metadata and successful full-read call arguments. No final citation ledger or analytic report was produced." : "Not listed in recorded retrieval bookkeeping. Packaged availability does not prove this run retrieved the source.") : ledger ? "Present in this run's saved evidence ledger." : "Not present in this run's saved evidence ledger. Packaged source availability does not prove the agent retrieved it.", "notice"));
  body.append(element("p", datasetForCase().note), keyValue("Indexed locator", source.file_locator), keyValue("Extraction label", source.extraction));
  if (source.date_meaning) body.append(keyValue("Date meaning", source.date_meaning));
  if (verification) body.append(keyValue("Saved text fingerprint", verification.text_matches ? "Matches the packaged indexed text" : "Mismatch — packaged text differs from this saved ledger"));
  body.append(element("p", source.text, "source-text"));
  body.append(links([["Open source file", source.file_url], ["Download source file ↓", source.file_url, true]]));
  if (source.media_url) {
    body.append(label("Attached raw source media"));
    body.append(element("p", source.media_provenance || "Attached source. Availability alone does not establish the model inspected it."));
    let media;
    if (source.media_url.endsWith(".mp4")) {
      media = element("video");
      media.controls = true;
      media.preload = "none";
      media.setAttribute("aria-label", datasetForCase().kind === "synthetic" ? `${source.title}: authored caption video, no audio` : source.title);
      media.append(element("p", "Your browser does not support this video. Use the original media link."));
    } else {
      media = element("img");
      media.alt = datasetForCase().kind === "synthetic" ? "Authored synthetic planning-board caption fixture. Indexed source text is shown above." : `${source.title}. Indexed source text is shown above.`;
    }
    media.src = source.media_url;
    body.append(media, links([["Open original media", source.media_url], ["Download media ↓", source.media_url, true]]));
    body.append(element("p", "The viewer does not reconstruct sampled frames. See report locators and the saved review; tool arguments may request a different seek from the frame actually returned.", "small"));
  } else if (/image|video|transcript/.test(source.kind)) body.append(element("p", "No raw media is attached for this indexed annotation/transcript.", "notice"));
  $("source-dialog").showModal();
}

function switchPanel(name, focus = false) {
  if (!["report", "trace", "evidence", "implementation"].includes(name)) name = "report";
  activePanel = name;
  for (const button of document.querySelectorAll("[role=tab]")) {
    const selected = button.dataset.panel === name;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    $(button.getAttribute("aria-controls")).hidden = !selected;
    if (focus && selected) button.focus();
  }
  if (currentCase) history.replaceState(null, "", `#${encodeURIComponent(currentCase.id)}/${name}`);
}
for (const button of document.querySelectorAll("[role=tab]")) {
  button.addEventListener("click", () => switchPanel(button.dataset.panel));
  button.addEventListener("keydown", (event) => {
    const tabs = [...document.querySelectorAll("[role=tab]")];
    const index = tabs.indexOf(button);
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next !== undefined) { event.preventDefault(); switchPanel(tabs[next].dataset.panel, true); }
  });
}
$("case-select").addEventListener("change", (event) => selectCase(event.target.value));
$("close-source").addEventListener("click", () => $("source-dialog").close());
$("source-dialog").addEventListener("close", () => {
  const video = $("source-dialog").querySelector("video");
  if (video) video.pause();
});
async function init() {
  try {
    const response = await fetch("content.json");
    if (!response.ok) throw new Error(`Artifact package returned HTTP ${response.status}`);
    content = await response.json();
    $("project-status").textContent = content.project_status;
    $("case-select").replaceChildren(...content.cases.map((item) => {
      const option = element("option", item.label); option.value = item.id; return option;
    }));
    $("case-select").disabled = false;
    $("case-shell").hidden = false;
    const [caseId, panel] = location.hash.slice(1).split("/");
    selectCase(caseId ? decodeURIComponent(caseId) : content.default_case, false);
    switchPanel(panel || "report");
  } catch (error) {
    $("load-error").hidden = false;
    $("load-error").textContent = "The saved artifact package could not be loaded. Build the showcase and serve showcase/dist through a local HTTP server; opening index.html directly is not supported. " + error.message;
  }
}
init();
