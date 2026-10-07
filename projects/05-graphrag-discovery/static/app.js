"use strict";

const $ = id => document.getElementById(id);
const state = {token: "", maxBytes: 1048576, snapshots: [], baselines: [], run: null, searchRun: null, items: [], selected: new Set(), seeds: new Set(), entities: new Map(), investigation: null, busy: false, dirty: false, scopeEpoch: 0, activeCorpus: "", activeSnapshot: "", connected: false, zoom: 1};
const NS = "http://www.w3.org/2000/svg";
// Keystrokes never replace the saved analysis or call an embedding model.
const preview = {epoch: 0, timer: null, controller: null, view: null, items: [], scope: null, enabled: true, composing: false, key: "", graphIds: new Set()};
const guide = {step: 0, reached: 0, overview: null, overviewKey: "", overviewEpoch: 0, baselineId: "", runId: "", query: "", corpusId: "", baselineSnapshot: ""};
const value = id => $(id).value.trim();
const optional = id => value(id) || null;
const text = (tag, content, className) => {
  const node = document.createElement(tag);
  node.textContent = content;
  if (className) node.className = className;
  return node;
};

function message(content, error = false) {
  $("message").textContent = content;
  $("message").className = error ? "message error" : "message";
  $("message").hidden = !content;
  $("message").setAttribute("role", error ? "alert" : "status");
}

function dateLabel(value, withTime = false) {
  if (!value) return "Not specified";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", {timeZone: "UTC", month: "short", day: "numeric", year: "numeric", ...(withTime ? {hour: "2-digit", minute: "2-digit"} : {})}).format(date) + (withTime ? " UTC" : "");
}

function snapshotLabel(id) {
  const item = state.snapshots.find(snapshot => snapshot.snapshot_id === id);
  return item?.label || id || "No snapshot";
}

function intervalLabel(item) {
  const status = item.temporal_status || {};
  const start = status.from === "known" ? dateLabel(item.valid_from) : "Unknown start";
  const end = status.to === "open" ? "Open end" : status.to === "known" ? dateLabel(item.valid_to) : "Unknown end";
  return `${start} → ${end}`;
}

function methodLabel(method) {
  if (method === "authored-fixture") return "Authored fixture";
  if (method?.startsWith("local-model")) return "Local model · unverified";
  return method?.replaceAll("_", " ") || "Method unspecified";
}

function updateControls() {
  const hasSnapshot = !!value("snapshot");
  const hasVectors = [...$("vector-index").options].some(option => option.value);
  for (const mode of ["dense", "hybrid"]) $("mode").querySelector(`option[value="${mode}"]`).disabled = !hasVectors;
  if (!hasVectors && ["dense", "hybrid"].includes(value("mode"))) $("mode").value = "lexical";
  $("vector-index").disabled = !hasVectors || value("mode") === "lexical";
  $("valid-time").disabled = value("mode") !== "graphrag";
  const world = value("compare-mode") === "world_state_change";
  for (const id of ["compare-from", "compare-to"]) { $(id).disabled = !world; $(id).required = world; }
  $("download").disabled = !state.run;
  $("more").disabled = !state.run?.next_cursor;
  $("save-baseline").disabled = state.run?.operation !== "search" || !state.searchRun || (value("baseline-kind") === "saved_findings" ? !state.selected.size : !state.seeds.size);
  $("load-investigation").disabled = !value("investigation");
  $("search-form").querySelector('button[type="submit"]').disabled = !hasSnapshot;
  $("compare-form").querySelector('button[type="submit"]').disabled = !hasSnapshot || !value("baseline");
  if ($("selection-count")) $("selection-count").textContent = `${state.selected.size} selected`;
  if ($("clear-selection")) $("clear-selection").disabled = !state.selected.size || state.run?.operation !== "search";
  $("clear-seeds").disabled = !state.seeds.size;
  if (preview.view) for (const id of ["download", "more", "save-baseline", "clear-selection", "clear-seeds"]) $(id).disabled = true;
  if ($("guide-primary")) {
    $("guide-primary").disabled = guide.step === 0 ? !hasSnapshot || !value("guide-query") : guide.step === 1 ? !state.items.length || !state.run : guide.step === 2 ? !state.searchRun || !state.selected.size : guide.step === 3 ? !guide.baselineId || !value("guide-target") : false;
    $("guide-back").disabled = guide.step === 0;
  }
  if ($("connection-status")) {
    $("connection-status").textContent = state.busy ? "Working locally" : state.connected ? "Local workspace" : "Connection unavailable";
    $("connection-status").dataset.state = state.busy ? "busy" : state.connected ? "ready" : "error";
  }
  if (state.busy) document.querySelectorAll("input, select, textarea, button").forEach(control => {
    if (!control.classList.contains("tab") && !control.closest("dialog")) {
      if (state.locks && !state.locks.has(control)) state.locks.set(control, control.disabled);
      control.disabled = true;
    }
  });
}

function clearEvidence() {
  $("evidence-meta").textContent = "Select a finding or edge.";
  $("evidence-text").textContent = "";
  $("evidence-details").textContent = "No evidence selected.";
  $("evidence-facts")?.replaceChildren();
  document.querySelectorAll(".finding.active").forEach(card => card.classList.remove("active"));
}

function clearRun() {
  stopPreview();
  state.run = null; state.searchRun = null; state.items = []; state.selected.clear(); state.seeds.clear();
  $("results").replaceChildren(text("p", "Search the selected snapshot.", "empty"));
  $("results-title").textContent = "Results";
  $("result-summary").textContent = "No search run.";
  $("run-details").textContent = "No run selected."; $("more").hidden = true;
  clearEvidence(); zoomGraph(0); graph([]); updateControls();
}

async function confirmDiscard() {
  if (!state.dirty) return true;
  const dialog = $("draft-dialog");
  return new Promise(resolve => {
    const finish = accepted => { dialog.close(); dialog.oncancel = null; $("draft-keep").onclick = null; $("draft-discard").onclick = null; resolve(accepted); };
    $("draft-keep").onclick = () => finish(false);
    $("draft-discard").onclick = () => finish(true);
    dialog.oncancel = event => { event.preventDefault(); finish(false); };
    dialog.showModal(); $("draft-keep").focus();
  });
}

function resetInvestigation() {
  state.investigation = null; state.dirty = false;
  $("investigation-form").reset();
  $("investigation-context").textContent = "Unsaved investigation.";
}

function showPanel(id) {
  if (id !== "search-panel") stopPreview();
  document.querySelectorAll(".panel").forEach(panel => { panel.hidden = panel.id !== id; });
  document.querySelectorAll(".tab").forEach(tab => {
    const active = tab.dataset.panel === id;
    tab.classList.toggle("active", active);
    if (active) tab.setAttribute("aria-current", "page"); else tab.removeAttribute("aria-current");
  });
  document.querySelectorAll(".scope-bar, .timeline-shell, .results-header, .workspace-grid, .run-details").forEach(section => { section.hidden = id === "instructions-panel"; });
  const titles = {"start-panel": "Start here", "search-panel": "Explore", "compare-panel": "Compare changes", "investigation-panel": "Investigations", "import-panel": "Import sources", "instructions-panel": "Instructions"};
  $("workspace-title").textContent = titles[id];
  if (id === "start-panel") { renderGuide(); loadOverview(); }
}

async function request(operation, data = {}, download = false) {
  const body = JSON.stringify(data);
  if (new TextEncoder().encode(body).length > state.maxBytes) throw new Error("Request exceeds 1 MiB. Use a smaller batch or the CLI.");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);
  try {
  const response = await fetch(`/api/${operation}`, {
    method: "POST", credentials: "same-origin", cache: "no-store",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": state.token}, body, signal: controller.signal
  });
  state.connected = true;
  if (download && response.ok && response.headers.get("Content-Type")?.startsWith("application/zip")) return await response.blob();
  let result;
  try { result = await response.json(); } catch { throw new Error("The local service returned an unreadable response. Refresh sources to reconnect."); }
  if (!response.ok || !result.ok) {
    const error = new Error(`${result.error?.message || "Request failed"} (${result.error?.code || response.status})`);
    error.details = result.error?.details;
    if (result.error?.code === "csrf_rejected") error.message = "The local service restarted. Refresh sources, then retry your action.";
    throw error;
  }
  return result.data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The service took too long to respond. A write may still have completed; refresh or inspect its status before retrying.");
    if (error instanceof TypeError) { state.connected = false; throw new Error("Cannot reach the local service. Start the workspace server, then Refresh sources. Your draft is still here."); }
    throw error;
  } finally { clearTimeout(timer); }
}

async function action(button, work) {
  if (state.busy) return;
  stopPreview();
  state.busy = true;
  const controls = [...document.querySelectorAll("input, select, textarea, button")].filter(control => !control.classList.contains("tab") && !control.closest("dialog"));
  const disabled = new Map(controls.map(control => [control, control.disabled])); state.locks = disabled;
  controls.forEach(control => { control.disabled = true; });
  const caption = button ? [...button.childNodes] : null;
  if (button) { button.textContent = "Working…"; button.setAttribute("aria-busy", "true"); }
  document.body.classList.add("busy");
  document.querySelector("main").setAttribute("aria-busy", "true");
  if ($("connection-status")) $("connection-status").textContent = "Working locally";
  try { await work(); }
  catch (error) {
    if (error instanceof TypeError || ["TimeoutError", "AbortError"].includes(error.name)) { state.connected = false; message("Cannot reach the local workspace. Start the service, then Refresh sources. Your draft is still here.", true); }
    else message(error.message, true);
  }
  finally {
    state.busy = false;
    for (const [control, prior] of disabled) if (control.isConnected) control.disabled = prior;
    state.locks = null;
    if (button) { button.replaceChildren(...caption); button.removeAttribute("aria-busy"); }
    document.body.classList.remove("busy"); document.querySelector("main").setAttribute("aria-busy", "false"); updateControls();
  }
}

function options(select, records, idKey, labeler, selected = "", placeholder = "None available") {
  select.replaceChildren();
  if (!records.length) select.append(new Option(placeholder, ""));
  for (const record of records) select.append(new Option(labeler(record), record[idKey]));
  if (records.some(record => record[idKey] === selected)) select.value = selected;
}

function corpus() {
  if (!value("corpus")) throw new Error("Choose a corpus or import a public text batch first.");
  return value("corpus");
}

function snapshot() {
  corpus();
  if (!value("snapshot")) throw new Error("Publish a complete snapshot before searching.");
  return value("snapshot");
}

function snapshotStatus() {
  const current = state.snapshots.find(item => item.snapshot_id === value("snapshot"));
  const graphReady = current?.capabilities?.includes("assertions");
  const graphOption = $("mode").querySelector('option[value="graphrag"]');
  graphOption.disabled = !graphReady;
  if (!graphReady) $("mode").value = "lexical";
  $("corpus-status").textContent = current
    ? `${current.coverage?.active_documents ?? "Unknown"} active sources · ${graphReady ? "Graph ready" : "Source passages only"} · Published ${dateLabel(current.published_at, true)} · ${current.coverage?.excluded_in_batch ?? 0} excluded`
    : "No complete snapshot. Stage and publish a batch in Import.";
  const timeline = $("snapshot-timeline");
  if (timeline) {
    timeline.replaceChildren();
    const recent = state.snapshots.slice(-8);
    if (current && !recent.includes(current)) recent.unshift(current);
    for (const record of recent) {
      const stop = text("button", "", "timeline-stop"); stop.type = "button";
      stop.append(text("span", dateLabel(record.published_at)), text("strong", record.label || "Published snapshot"));
      stop.title = `${record.label || record.snapshot_id} · ${dateLabel(record.published_at, true)}`;
      stop.classList.toggle("active", record.snapshot_id === current?.snapshot_id);
      stop.setAttribute("aria-pressed", String(record.snapshot_id === current?.snapshot_id));
      stop.addEventListener("click", () => { if (!state.busy) { $("snapshot").value = record.snapshot_id; selectSnapshot(); } });
      timeline.append(stop);
    }
  }
  updateControls();
}

function selectSnapshot() {
  stopPreview();
  if (state.activeSnapshot !== value("snapshot")) { state.activeSnapshot = value("snapshot"); clearRun(); }
  snapshotStatus();
  if (!$("start-panel").hidden) { renderGuide(); loadOverview(); }
}

async function refreshLists() {
  if (!value("corpus")) return;
  const selectedCorpus = corpus(), epoch = state.scopeEpoch;
  const selectedBaseline = value("baseline"), selectedInvestigation = value("investigation");
  const [baselines, investigations] = await Promise.all([
    request("baselines", {corpus_id: selectedCorpus}), request("investigations", {corpus_id: selectedCorpus})
  ]);
  if (epoch !== state.scopeEpoch || selectedCorpus !== value("corpus")) return;
  options($("baseline"), baselines, "baseline_id", item => `${item.kind.replaceAll("_", " ")} · ${dateLabel(item.created_at)} · ${item.baseline_id.slice(-6)}`, selectedBaseline, "No baseline saved");
  state.baselines = baselines;
  baselineModes();
  options($("investigation"), investigations, "investigation_id", item => `${item.title} · v${item.version}`, selectedInvestigation, "No investigation saved");
  updateControls();
}

function baselineModes() {
  const baseline = state.baselines.find(item => item.baseline_id === value("baseline"));
  const unavailable = baseline?.kind !== "saved_findings";
  $("compare-mode").querySelector('option[value="source_change"]').disabled = unavailable;
  if (unavailable && value("compare-mode") === "source_change") $("compare-mode").value = "knowledge_change";
  updateControls();
}

async function loadCorpus(preferredSnapshot = "") {
  if (!value("corpus")) return;
  const selectedCorpus = corpus(), epoch = ++state.scopeEpoch;
  if (state.activeCorpus && state.activeCorpus !== selectedCorpus) {
    state.snapshots = []; state.baselines = [];
    for (const id of ["snapshot", "baseline", "investigation", "vector-index"]) options($(id), [], "id", () => "", "", "None available");
    state.activeSnapshot = "";
    $("knowledge").value = ""; $("valid-time").value = "";
    clearRun(); snapshotStatus();
  }
  const [records, status] = await Promise.all([
    request("snapshots", {corpus_id: selectedCorpus}), request("status", {corpus_id: selectedCorpus})
  ]);
  if (epoch !== state.scopeEpoch || selectedCorpus !== value("corpus")) return;
  state.snapshots = records;
  const preferred = preferredSnapshot || value("snapshot");
  options($("snapshot"), [...records].reverse(), "snapshot_id", item => `${item.label || item.snapshot_id} · ${dateLabel(item.published_at)}`, preferred, "No complete snapshot");
  $("import-corpus").value = selectedCorpus;
  const vectorChoice = value("vector-index");
  $("vector-index").replaceChildren(new Option("None · lexical search only", ""));
  for (const index of status.vector_indexes || []) {
    if (index.profile?.provider === "llama.cpp") $("vector-index").append(new Option(`${index.profile.model} · ${index.dimensions} dimensions · ${index.index_id.slice(-8)}`, index.index_id));
  }
  if ([...$("vector-index").options].some(option => option.value === vectorChoice)) $("vector-index").value = vectorChoice;
  const newCorpus = state.activeCorpus !== selectedCorpus;
  const changed = newCorpus || state.activeSnapshot !== value("snapshot");
  state.activeCorpus = selectedCorpus; state.activeSnapshot = value("snapshot");
  if (newCorpus && records.find(record => record.snapshot_id === value("snapshot"))?.capabilities?.includes("assertions")) $("mode").value = "graphrag";
  if (changed) clearRun();
  snapshotStatus();
  await refreshLists();
  if (guide.corpusId !== selectedCorpus) {
    guide.corpusId = selectedCorpus; guide.step = 0; guide.reached = 0; guide.baselineId = ""; guide.runId = ""; guide.query = ""; guide.overview = null; guide.overviewKey = "";
    $("guide-query").value = "";
  }
  if (!$("start-panel").hidden) { renderGuide(); loadOverview(); }
}

async function bootstrap(preferredCorpus = "", preferredSnapshot = "") {
  const previous = preferredCorpus || value("corpus");
  const response = await fetch("/api/bootstrap", {credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(15000)});
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.error?.message || "Could not connect to the local workspace.");
  state.token = result.data.csrf_token;
  state.connected = true;
  state.maxBytes = result.data.limits.request_bytes;
  const preferred = previous || (result.data.corpora.some(item => item.corpus_id === "discovery-network") ? "discovery-network" : "");
  options($("corpus"), result.data.corpora, "corpus_id", item => `${item.corpus_id === "discovery-network" ? "Discovery network · synthetic demo" : item.corpus_id}${item.status === "ready" ? "" : " · not ready"}`, preferred, "No corpus loaded");
  if (value("corpus")) await loadCorpus(preferredSnapshot);
  else { state.snapshots = []; options($("snapshot"), [], "snapshot_id", () => "", "", "Choose a corpus"); snapshotStatus(); }
}

const guideSteps = [
  {label: "Ask", title: "Choose one starting question", copy: "Pick a suggested topic or enter your own. We will start at an earlier snapshot so you can compare what changed later.", action: "Find connections"},
  {label: "Connect", title: "Follow the relationships", copy: "The graph below connects entities found in your search. Hover or focus a node to see its neighbors. Arrows describe claims from the sources; they are not proof by themselves.", action: "Open a source passage"},
  {label: "Verify", title: "Read the source before trusting the claim", copy: "Read Source evidence below: the exact passage, source revision, and relevant dates. Check the findings you want to track. Save them as a baseline: a fixed reference for later comparison.", action: "Save selected findings as a baseline"},
  {label: "Compare", title: "Find what changed since your baseline", copy: "Your baseline is saved. Pick a later snapshot, then compare. Changes may describe a new report, correction, plan, dispute, or withdrawn source. Inspect both sides before drawing conclusions.", action: "Compare with this snapshot"},
  {label: "Keep", title: "Keep the evidence and your observations", copy: "Review the changes below. Export evidence downloads the comparison and citations. Open Investigations to add your own notes and save this run for later.", action: "Write investigation notes"}
];

function guideBaselineSnapshot() {
  return state.snapshots.find(item => item.snapshot_id === guide.overview?.recommended_baseline_snapshot_id)
    || state.snapshots.find(item => item.label === "Synthetic network: full baseline") || state.snapshots[0];
}

function renderGuide() {
  if (!$("start-panel")) return;
  if (guide.step > 0 && !state.run) { guide.step = 0; guide.reached = 0; }
  const step = guideSteps[guide.step];
  $("guide-step-label").textContent = `STEP ${guide.step + 1} OF ${guideSteps.length}`;
  $("guide-step-title").textContent = step.title; $("guide-step-copy").textContent = step.copy;
  $("guide-primary").textContent = step.action;
  $("guide-question-controls").hidden = guide.step !== 0;
  $("guide-target-controls").hidden = guide.step !== 3;
  $("guide-overview").hidden = guide.step !== 0;
  $("guide-hubs").hidden = guide.step !== 0;
  $("guide-progress").textContent = guide.step ? `Question: ${guide.query}` : "";
  const baseline = guideBaselineSnapshot();
  $("guide-snapshot-hint").textContent = baseline ? `Starts at “${baseline.label || baseline.snapshot_id}”. Uses graph relationships when available, without event-time or model filters.` : "Publish a snapshot in Import sources to begin.";
  $("guide-corpus-note").textContent = value("corpus") === "discovery-network"
    ? "Synthetic discovery network · Fictional organizations, assets, and reports. Connections are authored examples, not real-world facts."
    : value("corpus") === "pump-fixture" ? "Pump fixture · A small authored example of plans, corrections, conflicting reports, and withdrawals." : "Use the corpus and pinned snapshot above. All findings link back to their source evidence.";
  $("guide-steps").replaceChildren();
  guideSteps.forEach((item, index) => {
    const button = text("button", "", "guide-step"); button.type = "button";
    button.append(text("span", index < guide.step ? "✓" : String(index + 1)), text("strong", item.label));
    button.disabled = index > guide.reached;
    if (index === guide.step) button.setAttribute("aria-current", "step");
    button.addEventListener("click", () => goGuideStep(index)); $("guide-steps").append(button);
  });
  const selectedTarget = value("guide-target") || state.snapshots[state.snapshots.length - 1]?.snapshot_id;
  options($("guide-target"), [...state.snapshots].reverse(), "snapshot_id", item => item.label || item.snapshot_id, selectedTarget, "No snapshots available");
  if (!$("start-panel").hidden) {
    document.querySelector(".timeline-shell").hidden = true;
    document.querySelectorAll(".results-header, .workspace-grid, .run-details").forEach(section => { section.hidden = guide.step === 0; });
  }
  updateControls();
}

async function loadOverview() {
  if (!value("corpus") || !value("snapshot")) return;
  const key = JSON.stringify([value("corpus"), value("snapshot")]);
  if (guide.overviewKey === key) return;
  guide.overviewKey = key; guide.overview = null;
  const epoch = ++guide.overviewEpoch;
  $("guide-overview").replaceChildren(text("p", "Reading this snapshot…", "subtle"));
  $("guide-scenarios").replaceChildren(); $("guide-hub-list").replaceChildren();
  try {
    const result = await request("overview", {corpus_id: value("corpus"), snapshot_id: value("snapshot")});
    if (epoch !== guide.overviewEpoch || key !== JSON.stringify([value("corpus"), value("snapshot")])) return;
    guide.overview = result;
    const counts = result.counts || {};
    $("guide-overview").replaceChildren();
    for (const [key, label] of [["active_documents", "source documents"], ["entities", "connected entities"], ["assertions", "relationships"]]) {
      const stat = text("div", "", "guide-stat"); stat.append(text("strong", Number.isFinite(counts[key]) ? counts[key].toLocaleString() : "—"), text("span", label)); $("guide-overview").append(stat);
    }
    const snapshots = text("div", "", "guide-stat"); snapshots.append(text("strong", String(state.snapshots.length)), text("span", "published snapshots")); $("guide-overview").append(snapshots);
    const scenarios = Array.isArray(result.scenarios) && result.scenarios.length ? result.scenarios : (result.top_entities || []).slice(0, 5).map(item => ({title: item.label, query: item.label, description: "Explore this entity and its neighbors."}));
    for (const scenario of scenarios) {
      const button = text("button", "", "guide-scenario"); button.type = "button";
      button.append(text("strong", scenario.title), text("span", scenario.description));
      button.addEventListener("click", () => { $("guide-query").value = scenario.query; $("guide-query").focus(); updateControls(); });
      $("guide-scenarios").append(button);
    }
    if (!value("guide-query") && scenarios.length) $("guide-query").value = (scenarios.find(item => item.query === "Harbor Converter") || scenarios[0]).query;
    for (const entity of result.top_entities || []) {
      const button = text("button", `${entity.label} · ${entity.connections} links`, "secondary"); button.type = "button";
      button.addEventListener("click", () => { $("guide-query").value = entity.label; $("guide-query").focus(); updateControls(); }); $("guide-hub-list").append(button);
    }
    renderGuide();
  } catch (error) {
    if (epoch !== guide.overviewEpoch || key !== JSON.stringify([value("corpus"), value("snapshot")])) return;
    guide.overviewKey = "";
    $("guide-overview").replaceChildren(text("p", `Snapshot summary unavailable: ${error.message} You can still enter a question.`, "subtle"));
  }
}

function goGuideStep(index) {
  if (state.busy || index < 0 || index > guide.reached) return;
  if (index >= 1 && index <= 2 && guide.searchRun && state.run?.run_id !== guide.searchRun.run_id) {
    $("snapshot").value = guide.searchRun.scope.snapshot_id; state.activeSnapshot = value("snapshot"); snapshotStatus();
    renderRun(guide.searchRun);
  } else if (index === 4 && guide.compareRun && state.run?.run_id !== guide.compareRun.run_id) renderRun(guide.compareRun);
  guide.step = index; renderGuide();
}

async function runSearch() {
  const mode = value("mode"), vectorIndex = value("vector-index");
  if (["dense", "hybrid"].includes(mode) && !vectorIndex) throw new Error("Choose a configured local vector index for dense/hybrid search.");
  const useLocal = mode !== "lexical" && !!vectorIndex;
  const params = {corpus_id: corpus(), snapshot_id: snapshot(), query: value("query"), mode, knowledge_cutoff: optional("knowledge"), valid_time: mode === "graphrag" ? optional("valid-time") : null, limit: 100, page_size: 30};
  if (useLocal) params.vector_index_id = vectorIndex;
  const run = await request(useLocal ? "search_local" : "search", params);
  state.selected.clear(); state.seeds.clear(); renderRun(run); message("");
  return run;
}

async function advanceGuide() {
  if (guide.step === 0) {
    const question = value("guide-query"), first = guideBaselineSnapshot();
    if (!question || !first) throw new Error("Choose a published corpus and enter a question first.");
    $("snapshot").value = first.snapshot_id; selectSnapshot();
    $("query").value = question; $("knowledge").value = ""; $("valid-time").value = ""; $("vector-index").value = "";
    $("mode").value = first.capabilities?.includes("assertions") ? "graphrag" : "lexical";
    const run = await runSearch();
    guide.query = question; guide.searchRun = run; guide.runId = run.run_id; guide.baselineId = ""; guide.compareRun = null; guide.reached = 0;
    if (!run.items?.length) throw new Error("No findings for this question. Try another suggested topic or your own keywords.");
  } else if (guide.step === 1) {
    const item = state.items.find(item => item.assertion_id || item.chunk_id || item.id);
    if (!item) throw new Error("Run a search before opening evidence.");
    await openEvidence(item);
  } else if (guide.step === 2) {
    if (!state.searchRun || !state.selected.size) throw new Error("Select findings to track in the baseline.");
    const baseline = await request("baseline_save", {run_id: state.searchRun.run_id, kind: "saved_findings", finding_ids: [...state.selected]});
    guide.baselineId = baseline.baseline_id; guide.baselineSnapshot = state.searchRun.scope.snapshot_id;
    await refreshLists(); $("baseline").value = baseline.baseline_id; baselineModes();
  } else if (guide.step === 3) {
    if (!guide.baselineId || !value("guide-target")) throw new Error("Save a baseline and choose a target snapshot first.");
    const target = value("guide-target");
    const run = await request("compare", {baseline_id: guide.baselineId, target_snapshot_id: target, mode: "knowledge_change"});
    $("snapshot").value = target; state.activeSnapshot = target; snapshotStatus(); renderRun(run); guide.compareRun = run;
  } else {
    if (!await confirmDiscard()) return;
    resetInvestigation(); $("investigation-title").value = `${guide.query} review`; $("investigation-question").value = guide.query;
    state.dirty = true; $("investigation-context").textContent = "Add your observations, then save this investigation.";
    showPanel("investigation-panel"); $("notes").focus(); return;
  }
  guide.step = Math.min(4, guide.step + 1); guide.reached = Math.max(guide.reached, guide.step); renderGuide();
}

function previewStatus(phase, label) {
  $("live-feedback").dataset.phase = phase;
  $("live-status").textContent = label;
}

function previewKey() {
  return JSON.stringify([value("corpus"), value("snapshot"), $("query").value, value("mode"), value("knowledge"), value("valid-time"), value("vector-index")]);
}

function rememberView() {
  if (preview.view) return;
  const ids = ["results", "results-title", "result-summary", "graph", "graph-note", "graph-empty", "evidence-meta", "evidence-facts", "evidence-text", "evidence-details", "run-details"];
  preview.view = {
    parts: ids.map(id => ({node: $(id), children: [...$(id).childNodes], hidden: $(id).hidden})),
    selection: document.querySelector(".selection-bar").hidden,
    more: $("more").hidden, viewBox: $("graph").getAttribute("viewBox"), graphLabel: $("graph").getAttribute("aria-label"), zoom: state.zoom,
    graphHelp: document.querySelector(".graph-help").textContent
  };
  document.querySelector(".workspace-grid").classList.add("live-preview");
  document.querySelector(".selection-bar").hidden = true;
  $("more").hidden = true;
  updateControls();
}

function stopPreview(restore = true) {
  preview.epoch++;
  clearTimeout(preview.timer); preview.timer = null;
  preview.controller?.abort(); preview.controller = null;
  if (preview.view) {
    if (restore) {
      for (const part of preview.view.parts) { part.node.replaceChildren(...part.children); part.node.hidden = part.hidden; }
      document.querySelector(".selection-bar").hidden = preview.view.selection;
      $("more").hidden = preview.view.more;
      $("graph").setAttribute("viewBox", preview.view.viewBox);
      $("graph").setAttribute("aria-label", preview.view.graphLabel);
      state.zoom = preview.view.zoom;
      document.querySelector(".graph-help").textContent = preview.view.graphHelp;
    }
    preview.view = null;
    document.querySelector(".workspace-grid").classList.remove("live-preview");
    document.querySelector(".evidence-column").classList.remove("tracing");
    updateControls();
  }
  preview.items = []; preview.scope = null; preview.key = ""; preview.graphIds.clear();
  previewStatus("idle", preview.enabled ? "Type to trace matching evidence." : "Preview paused.");
}

function queryMatches(content) {
  const words = (content || "").toLocaleLowerCase().match(/[\p{L}\p{N}]+/gu) || [];
  const terms = value("query").toLocaleLowerCase().match(/[\p{L}\p{N}]+/gu) || [];
  return terms.some(term => term.length >= 2 && words.some(word => word.startsWith(term)));
}

function highlightQuery() {
  if (!preview.view) return;
  $("graph").querySelectorAll(".graph-node").forEach(node => node.classList.toggle("query-match", queryMatches(node.dataset.label)));
}

function schedulePreview() {
  clearTimeout(preview.timer);
  preview.controller?.abort(); preview.controller = null;
  const epoch = ++preview.epoch;
  if (!preview.enabled || preview.composing || state.busy || $("search-panel").hidden || !value("corpus") || !value("snapshot") || value("query").length < 2) { stopPreview(); return; }
  if ($("query").value.length > 256 || (value("query").match(/[\p{L}\p{N}]+/gu) || []).length > 16) { stopPreview(); previewStatus("idle", "Long question · use Search evidence."); return; }
  highlightQuery();
  previewStatus("typing", preview.view ? "Typing · previous preview shown" : "Matching as you type…");
  const key = previewKey();
  preview.timer = setTimeout(() => runPreview(epoch, key), 300);
}

async function runPreview(epoch, key) {
  if (epoch !== preview.epoch || key !== previewKey() || state.busy) return;
  const controller = new AbortController(); preview.controller = controller;
  const timeout = setTimeout(() => controller.abort(), 5000);
  const current = () => epoch === preview.epoch && key === previewKey() && !state.busy && !$("search-panel").hidden;
  previewStatus("loading", preview.view ? "Matching · previous preview shown" : "Finding connections…");
  try {
    const mode = value("mode") === "graphrag" ? "graphrag" : "lexical";
    const body = {corpus_id: value("corpus"), snapshot_id: value("snapshot"), query: $("query").value.trimStart(), mode, knowledge_cutoff: optional("knowledge"), valid_time: mode === "graphrag" ? optional("valid-time") : null};
    const response = await fetch("/api/preview", {method: "POST", credentials: "same-origin", cache: "no-store", headers: {"Content-Type": "application/json", "X-CSRF-Token": state.token}, body: JSON.stringify(body), signal: controller.signal});
    const result = await response.json();
    if (!current()) return;
    if (!response.ok || !result.ok) throw new Error(result.error?.message || "Preview unavailable.");
    rememberView();
    preview.items = result.data.items || []; preview.scope = result.data.scope; preview.key = key;
    $("results").replaceChildren(...preview.items.map(previewFinding));
    $("results-title").textContent = "Live preview";
    $("result-summary").textContent = `${preview.items.length} preview findings · ${snapshotLabel(preview.scope.snapshot_id)}${result.data.truncated ? " · Limited preview" : ""} · Search to retain findings.`;
    $("run-details").textContent = JSON.stringify(result.data, null, 2);
    clearEvidence();
    graph(preview.items, true);
    document.querySelector(".graph-help").textContent = "Select a node, link, or source to trace its evidence.";
    if (preview.items.length) tracePreview(preview.items[0]);
    else $("results").append(text("p", "No keyword matches in this preview. Continue typing or run a full search.", "empty"));
    const modelHint = value("vector-index") && value("mode") !== "lexical" || ["dense", "hybrid"].includes(value("mode"));
    previewStatus(preview.items.length ? "ready" : "empty", `${preview.items.length ? "Evidence connected" : "No preview matches"}${modelHint ? " · Keyword preview; Search uses the local model." : " · Search to retain findings."}`);
  } catch (error) {
    if (!current()) return;
    stopPreview();
    previewStatus("error", error.name === "AbortError" ? "Preview timed out. Search or keep typing to retry." : `Preview unavailable: ${error.message}`);
  } finally {
    clearTimeout(timeout);
    if (preview.controller === controller) preview.controller = null;
  }
}

function sourceKey(item) {
  const cite = item.evidence || item;
  return JSON.stringify([cite.document_id, cite.version_id]);
}

function traceGraph(item) {
  $("graph").querySelectorAll(".graph-edge, .evidence-tether").forEach(edge => edge.classList.toggle("evidence-active", edge.dataset.findingId === item.id));
  $("graph").querySelectorAll(".graph-node").forEach(node => node.classList.toggle("evidence-active", [item.subject_id, item.object_id].includes(node.dataset.entityId)));
  $("graph").querySelectorAll(".graph-source").forEach(node => node.classList.toggle("evidence-active", node.dataset.sourceKey === sourceKey(item)));
}

function tracePreview(item) {
  if (!preview.items.includes(item)) return;
  evidenceView(item);
  traceGraph(item);
  $("results").querySelectorAll(".finding").forEach(card => card.classList.toggle("preview-focus", card.dataset.findingId === item.id));
  const column = document.querySelector(".evidence-column");
  column.classList.remove("tracing");
  // Restart a finite cue without timers, scrolling, or taking focus from typing.
  void column.offsetWidth;
  column.classList.add("tracing");
}

function previewFinding(item, index) {
  const card = text("article", "", "finding entering"); card.dataset.findingId = item.id;
  card.style.setProperty("--reveal-delay", `${Math.min(index * 65, 500)}ms`);
  card.append(text("div", item.subject_label && item.object_label ? `${item.subject_label} → ${item.object_label}` : "Source passage", "finding-head"), text("p", item.text, "finding-text"));
  const chips = text("div", "", "chips");
  if (item.modality) chips.append(text("span", item.modality, `chip${item.modality === "planned" ? " warn" : ""}`));
  if (item.disputed) chips.append(text("span", "Disputed", "chip conflict"));
  if (item.temporal_status?.from === "unknown" || item.temporal_status?.to === "unknown") chips.append(text("span", "Time unknown", "chip warn"));
  card.append(chips);
  const cite = item.evidence || item;
  card.append(text("p", `${cite.document_id || "Source"} · ${cite.version_id || "Unknown revision"}`, "subtle"));
  const actions = text("div", "", "actions"), trace = text("button", "Trace evidence", "secondary");
  trace.type = "button"; trace.addEventListener("click", () => tracePreview(item)); actions.append(trace); card.append(actions);
  card.addEventListener("mouseenter", () => tracePreview(item));
  trace.addEventListener("focus", () => tracePreview(item));
  return card;
}

function seedSummary() {
  $("seeds").textContent = state.seeds.size
    ? `Seeds: ${[...state.seeds].map(id => state.entities.get(id) || id).join(", ")}`
    : "Select graph nodes for a neighborhood baseline.";
  updateControls();
}

// Layout depends only on the displayed topology, never random state or timers.
// The fixed node/iteration limits bound this work even for a large corpus.
function graphLayout(entities, edges, live = false) {
  const ids = [...entities.keys()].sort(), adjacency = new Map(ids.map(id => [id, new Set()]));
  for (const edge of edges) {
    adjacency.get(edge.subject_id).add(edge.object_id);
    adjacency.get(edge.object_id).add(edge.subject_id);
  }
  const groups = [], assigned = new Set();
  for (const id of ids) {
    if (assigned.has(id)) continue;
    const members = [], pending = [id]; assigned.add(id);
    while (pending.length) {
      const current = pending.pop(); members.push(current);
      for (const neighbor of [...adjacency.get(current)].sort()) if (!assigned.has(neighbor)) { assigned.add(neighbor); pending.push(neighbor); }
    }
    groups.push(members.sort());
  }
  groups.sort((a, b) => b.length - a.length || a[0].localeCompare(b[0]));
  const top = 36, bottom = live ? 238 : 374, width = 568, height = bottom - top;
  const columns = Math.max(1, Math.ceil(Math.sqrt(groups.length * width / height))), rows = Math.max(1, Math.ceil(groups.length / columns));
  const points = new Map(), radii = new Map(), count = ids.length;
  const spacing = Math.max(38, Math.min(112, Math.sqrt(width * height / Math.max(count, 1)) * .92));
  groups.forEach((members, group) => {
    const row = Math.floor(group / columns), rowSize = Math.min(columns, groups.length - row * columns);
    const cx = 320 + ((group % columns) - (rowSize - 1) / 2) * width / columns;
    const cy = top + (row + .5) * height / rows;
    members.forEach((id, index) => {
      const angle = index * 2.399963229728653 + group * .71;
      const radius = members.length === 1 ? 0 : Math.sqrt((index + .5) / members.length) * Math.min(width / columns, height / rows) * .37;
      points.set(id, {x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius, vx: 0, vy: 0, cx, cy, group});
      radii.set(id, Math.min(25, (count > 30 ? 11 : 17) + Math.sqrt(adjacency.get(id).size) * 1.9));
    });
  });
  const links = [];
  for (const id of ids) for (const other of [...adjacency.get(id)].sort()) if (id < other) links.push([id, other]);
  for (let iteration = 0; iteration < 160 && count > 1; iteration++) {
    const forces = new Map(ids.map(id => [id, [0, 0]]));
    for (let i = 0; i < count; i++) for (let j = i + 1; j < count; j++) {
      const a = points.get(ids[i]), b = points.get(ids[j]);
      let dx = a.x - b.x, dy = a.y - b.y;
      if (Math.abs(dx) + Math.abs(dy) < .01) { dx = .7; dy = (i % 2 ? .7 : -.7); }
      const distance = Math.hypot(dx, dy), separation = radii.get(ids[i]) + radii.get(ids[j]) + 10;
      const force = Math.min(8, spacing * spacing / (distance * distance) * 1.1) + Math.max(0, separation - distance) * .32;
      const fx = dx / distance * force, fy = dy / distance * force;
      forces.get(ids[i])[0] += fx; forces.get(ids[i])[1] += fy;
      forces.get(ids[j])[0] -= fx; forces.get(ids[j])[1] -= fy;
    }
    for (const [aId, bId] of links) {
      const a = points.get(aId), b = points.get(bId), dx = b.x - a.x, dy = b.y - a.y;
      const distance = Math.hypot(dx, dy) || 1, force = (distance - spacing) * .045;
      const fx = dx / distance * force, fy = dy / distance * force;
      forces.get(aId)[0] += fx; forces.get(aId)[1] += fy;
      forces.get(bId)[0] -= fx; forces.get(bId)[1] -= fy;
    }
    const maxStep = 6 * (1 - iteration / 160) + .45;
    for (const id of ids) {
      const point = points.get(id), [fx, fy] = forces.get(id);
      point.vx = (point.vx + fx + (point.cx - point.x) * .007) * .68;
      point.vy = (point.vy + fy + (point.cy - point.y) * .007) * .68;
      const movement = Math.hypot(point.vx, point.vy) || 1, scale = Math.min(1, maxStep / movement);
      point.x = Math.max(36, Math.min(604, point.x + point.vx * scale));
      point.y = Math.max(top, Math.min(bottom, point.y + point.vy * scale));
    }
  }
  return {coordinates: new Map(ids.map(id => [id, [Number(points.get(id).x.toFixed(2)), Number(points.get(id).y.toFixed(2))]])), radii, adjacency, components: groups.length, top, bottom};
}

function graphLabels(entities, layout, preferred, live = false) {
  const labels = new Map(), occupied = [], limit = entities.size > 40 ? 10 : entities.size > 18 ? 12 : 18;
  const ordered = [...entities.keys()].sort((a, b) => Number(preferred.has(b)) - Number(preferred.has(a)) || layout.adjacency.get(b).size - layout.adjacency.get(a).size || a.localeCompare(b));
  for (const id of ordered) {
    const [x, y] = layout.coordinates.get(id), radius = layout.radii.get(id), full = entities.get(id);
    const length = entities.size > 18 ? 18 : 24, label = full.length > length ? `${full.slice(0, length - 1)}…` : full;
    const width = label.length * 11.5, candidates = [{dx: 0, dy: radius + 23, anchor: "middle"}, {dx: 0, dy: -radius - 11, anchor: "middle"}, {dx: radius + 9, dy: 7, anchor: "start"}, {dx: -radius - 9, dy: 7, anchor: "end"}];
    let chosen = null, visible = false;
    for (const candidate of candidates) {
      const left = x + candidate.dx - (candidate.anchor === "middle" ? width / 2 : candidate.anchor === "end" ? width : 0);
      const box = {left, right: left + width, top: y + candidate.dy - 20, bottom: y + candidate.dy + 6};
      if (box.left < 8 || box.right > 632 || box.top < 5 || box.bottom > (live ? 282 : 422)) continue;
      chosen ||= candidate;
      const overlapsLabel = occupied.some(other => box.left < other.right + 7 && box.right > other.left - 7 && box.top < other.bottom + 5 && box.bottom > other.top - 5);
      const overlapsNode = [...layout.coordinates].some(([other, [nx, ny]]) => other !== id && nx + layout.radii.get(other) > box.left && nx - layout.radii.get(other) < box.right && ny + layout.radii.get(other) > box.top && ny - layout.radii.get(other) < box.bottom);
      if (!overlapsLabel && !overlapsNode && occupied.length < limit) { chosen = candidate; occupied.push(box); visible = true; break; }
    }
    chosen ||= {dx: 0, dy: y < 180 ? radius + 23 : -radius - 11, anchor: x < 130 ? "start" : x > 510 ? "end" : "middle"};
    labels.set(id, {...chosen, label, visible});
  }
  return labels;
}

function graphEdgePath(item, layout, index, count) {
  const a = layout.coordinates.get(item.subject_id), b = layout.coordinates.get(item.object_id);
  const r1 = layout.radii.get(item.subject_id), r2 = layout.radii.get(item.object_id);
  if (item.subject_id === item.object_id) {
    const direction = a[1] < (layout.top + layout.bottom) / 2 ? 1 : -1;
    const room = direction > 0 ? layout.bottom + 25 - a[1] : a[1] - 8;
    const reach = Math.min(room / 2, r1 + 20 + (count > 1 ? index / (count - 1) * 30 : 0));
    const start = [a[0] - r1 * .72, a[1] + direction * r1 * .72], end = [a[0] + r1 * .72, start[1]];
    const c1 = [a[0] - reach, a[1] + direction * reach * 2], c2 = [a[0] + reach, c1[1]];
    return {d: `M${start} C${c1} ${c2} ${end}`, midpoint: [(start[0] + 3 * c1[0] + 3 * c2[0] + end[0]) / 8, (start[1] + 3 * c1[1] + 3 * c2[1] + end[1]) / 8]};
  }
  const dx = b[0] - a[0], dy = b[1] - a[1], distance = Math.hypot(dx, dy) || 1;
  const orientation = item.subject_id < item.object_id ? 1 : -1;
  const offset = count > 1 ? (index / (count - 1) - .5) * 2 * Math.min(92, (count - 1) * 17) * orientation : 0;
  const control = [Math.max(12, Math.min(628, (a[0] + b[0]) / 2 - dy / distance * offset)), Math.max(12, Math.min(layout.bottom + 26, (a[1] + b[1]) / 2 + dx / distance * offset))];
  const startLength = Math.hypot(control[0] - a[0], control[1] - a[1]) || 1, endLength = Math.hypot(control[0] - b[0], control[1] - b[1]) || 1;
  const start = [a[0] + (control[0] - a[0]) * (r1 + 2) / startLength, a[1] + (control[1] - a[1]) * (r1 + 2) / startLength];
  const end = [b[0] + (control[0] - b[0]) * (r2 + 5) / endLength, b[1] + (control[1] - b[1]) * (r2 + 5) / endLength];
  return {d: `M${start} Q${control} ${end}`, midpoint: [(start[0] + 2 * control[0] + end[0]) / 4, (start[1] + 2 * control[1] + end[1]) / 4]};
}

function graph(items, live = false) {
  const svg = $("graph");
  svg.replaceChildren();
  svg.setAttribute("aria-label", live ? "Live evidence connections. Select a node, relationship, or source to trace support." : "Select an entity as a baseline seed, or an edge to inspect its evidence");
  const seen = new Set();
  const reveal = (node, id, delay) => {
    seen.add(id);
    if (live && !preview.graphIds.has(id)) node.classList.add("entering");
    node.style.setProperty("--reveal-delay", `${Math.min(delay, 600)}ms`);
  };
  const assertions = items.filter(item => item.assertion_id && item.subject_id && item.object_id);
  const entities = new Map();
  const edges = [];
  for (const item of assertions) {
    const needed = [item.subject_id, item.object_id].filter(id => !entities.has(id));
    if (edges.length >= 200 || entities.size + new Set(needed).size > 100) continue;
    entities.set(item.subject_id, item.subject_label || item.subject_id);
    entities.set(item.object_id, item.object_label || item.object_id);
    edges.push(item);
  }
  if (!live) state.entities = entities;
  const layout = graphLayout(entities, edges, live), coordinates = layout.coordinates;
  const preferred = new Set([...entities].filter(([id, label]) => queryMatches(label) || (!live && state.seeds.has(id))).map(([id]) => id));
  const labels = graphLabels(entities, layout, preferred, live), bundles = new Map();
  for (const item of edges) {
    const key = JSON.stringify([item.subject_id, item.object_id].sort());
    if (!bundles.has(key)) bundles.set(key, []);
    bundles.get(key).push(item);
  }
  for (const bundle of bundles.values()) bundle.sort((a, b) => String(a.id).localeCompare(String(b.id)));
  const scene = document.createElementNS(NS, "g"); scene.setAttribute("class", "graph-scene");
  const edgeLayer = document.createElementNS(NS, "g"), nodeLayer = document.createElementNS(NS, "g"), sourceLayer = document.createElementNS(NS, "g");
  edgeLayer.setAttribute("class", "graph-edge-layer"); nodeLayer.setAttribute("class", "graph-node-layer"); sourceLayer.setAttribute("class", "graph-source-layer");
  scene.append(edgeLayer, nodeLayer, sourceLayer);
  let summary = "";
  const emphasize = (entityId = null, findingId = null) => {
    if (state.busy) return;
    const related = edges.filter(item => entityId ? [item.subject_id, item.object_id].includes(entityId) : item.id === findingId);
    const findingIds = new Set(related.map(item => item.id)), nodeIds = new Set(related.flatMap(item => [item.subject_id, item.object_id])), sourceIds = new Set(related.map(sourceKey));
    scene.classList.toggle("has-neighborhood-focus", !!related.length);
    scene.querySelectorAll(".graph-edge, .evidence-tether").forEach(edge => edge.classList.toggle("neighbor-active", findingIds.has(edge.dataset.findingId)));
    scene.querySelectorAll(".graph-node").forEach(node => { node.classList.toggle("neighbor-active", nodeIds.has(node.dataset.entityId)); node.classList.toggle("interaction-focus", node.dataset.entityId === entityId); });
    scene.querySelectorAll(".graph-source").forEach(node => node.classList.toggle("neighbor-active", sourceIds.has(node.dataset.sourceKey)));
    $("results").querySelectorAll(".finding").forEach(card => card.classList.toggle("graph-related", findingIds.has(card.dataset.findingId)));
    $("graph-note").textContent = entityId ? `${entities.get(entityId)} · ${related.length} retrieved relationship${related.length === 1 ? "" : "s"}. ${summary}` : summary;
  };
  const clearEmphasis = () => {
    scene.classList.remove("has-neighborhood-focus");
    scene.querySelectorAll(".neighbor-active").forEach(node => node.classList.remove("neighbor-active"));
    scene.querySelectorAll(".interaction-focus").forEach(node => node.classList.remove("interaction-focus"));
    $("results").querySelectorAll(".graph-related").forEach(card => card.classList.remove("graph-related"));
    $("graph-note").textContent = summary;
  };
  if (live) zoomGraph(0);
  const sources = new Map();
  if (live) for (const item of items) {
    const key = sourceKey(item);
    if (!sources.has(key) && sources.size < 6) {
      const index = sources.size;
      sources.set(key, {item, x: 110 + (index % 3) * 210, y: (entities.size ? 330 : 175) + Math.floor(index / 3) * 64});
    }
  }
  [...sources.values()].forEach((source, index) => {
    const rowSize = Math.min(3, sources.size - Math.floor(index / 3) * 3);
    source.x = 320 + ((index % 3) - (rowSize - 1) / 2) * 210;
  });
  const defs = document.createElementNS(NS, "defs");
  const marker = document.createElementNS(NS, "marker");
  for (const [key, val] of Object.entries({id: "arrow", viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "5", markerHeight: "5", orient: "auto-start-reverse"})) marker.setAttribute(key, val);
  const arrow = document.createElementNS(NS, "path");
  arrow.setAttribute("d", "M 0 0 L 10 5 L 0 10 z"); arrow.setAttribute("fill", "#65ccb5"); marker.append(arrow); defs.append(marker); svg.append(defs, scene);
  for (const item of edges) {
    const bundle = bundles.get(JSON.stringify([item.subject_id, item.object_id].sort())), path = graphEdgePath(item, layout, bundle.indexOf(item), bundle.length);
    const edge = document.createElementNS(NS, "path");
    const attrs = {d: path.d, fill: "none", "marker-end": "url(#arrow)", tabindex: "0", role: "button", "aria-label": `Inspect ${item.text}`};
    for (const [key, val] of Object.entries(attrs)) edge.setAttribute(key, String(val));
    edge.setAttribute("class", `graph-edge ${item.modality === "planned" ? "planned" : ""} ${item.disputed ? "disputed" : ""}`);
    edge.dataset.findingId = item.id;
    reveal(edge, `edge:${item.id}`, 130 + edges.indexOf(item) * 45);
    const title = document.createElementNS(NS, "title"); title.textContent = item.text; edge.append(title);
    const activate = () => { if (state.busy) return; if (live) tracePreview(item); else action(null, () => openEvidence(item)); };
    edge.addEventListener("click", activate); edge.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); activate(); } });
    const focusEdge = () => { emphasize(null, item.id); if (live && !state.busy) tracePreview(item); };
    edge.addEventListener("mouseenter", focusEdge); edge.addEventListener("focus", focusEdge);
    edge.addEventListener("mouseleave", clearEmphasis); edge.addEventListener("blur", clearEmphasis);
    edgeLayer.append(edge);
    const source = sources.get(sourceKey(item));
    if (source) {
      const tether = document.createElementNS(NS, "line");
      for (const [key, val] of Object.entries({x1: path.midpoint[0], y1: path.midpoint[1], x2: source.x, y2: source.y-22, class: "evidence-tether", "aria-hidden": "true"})) tether.setAttribute(key, val);
      tether.dataset.findingId = item.id; reveal(tether, `tether:${item.id}`, 280 + edges.indexOf(item) * 45); edgeLayer.append(tether);
    }
  }
  for (const [id, label] of [...entities].sort(([a], [b]) => a.localeCompare(b))) {
    const [x, y] = coordinates.get(id);
    const node = document.createElementNS(NS, "g");
    node.setAttribute("transform", `translate(${x},${y})`); node.setAttribute("class", `graph-node${!live && state.seeds.has(id) ? " selected" : ""}`);
    node.setAttribute("tabindex", "0"); node.setAttribute("role", "button");
    if (!live) node.setAttribute("aria-pressed", String(state.seeds.has(id)));
    const relationshipCount = edges.filter(item => [item.subject_id, item.object_id].includes(id)).length;
    node.setAttribute("aria-label", `${label}, ${relationshipCount} retrieved relationships. ${live ? "Trace evidence" : "Toggle baseline seed"}`);
    node.dataset.label = label;
    if (queryMatches(label)) node.classList.add("query-match");
    reveal(node, `entity:${id}`, [...entities.keys()].indexOf(id) * 65);
    const circle = document.createElementNS(NS, "circle"); circle.setAttribute("r", String(layout.radii.get(id))); node.append(circle);
    const dot = document.createElementNS(NS, "circle"); dot.setAttribute("r", entities.size > 30 ? "3" : "5"); dot.setAttribute("class", "entity-dot"); node.append(dot);
    const labelLayout = labels.get(id), caption = document.createElementNS(NS, "text");
    caption.setAttribute("text-anchor", labelLayout.anchor); caption.setAttribute("x", String(labelLayout.dx)); caption.setAttribute("y", String(labelLayout.dy));
    caption.setAttribute("class", `graph-label${labelLayout.visible ? "" : " label-suppressed"}`); caption.textContent = labelLayout.label; node.append(caption);
    const title = document.createElementNS(NS, "title"); title.textContent = `${label} (${id}) · ${relationshipCount} retrieved relationships`; node.append(title);
    const activate = () => {
      if (state.busy) return;
      if (live) { tracePreview(edges.find(item => [item.subject_id, item.object_id].includes(id))); return; }
      if (state.seeds.has(id)) state.seeds.delete(id); else state.seeds.add(id);
      graph(state.items); const selected = [...svg.querySelectorAll('.graph-node')].find(node => node.dataset.entityId === id); selected?.focus();
    };
    node.dataset.entityId = id;
    node.addEventListener("click", activate); node.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); activate(); } });
    const focusNode = () => { emphasize(id); if (!state.busy) nodeLayer.append(node); };
    node.addEventListener("mouseenter", focusNode); node.addEventListener("focus", focusNode);
    node.addEventListener("mouseleave", clearEmphasis); node.addEventListener("blur", clearEmphasis);
    nodeLayer.append(node);
  }
  for (const [key, source] of sources) {
    const node = document.createElementNS(NS, "g"), cite = source.item.evidence || source.item;
    for (const [attr, val] of Object.entries({transform: `translate(${source.x},${source.y})`, class: "graph-source", tabindex: "0", role: "button", "aria-label": `Trace source ${cite.document_id} ${cite.version_id}`})) node.setAttribute(attr, val);
    node.dataset.sourceKey = key;
    const box = document.createElementNS(NS, "rect");
    for (const [attr, val] of Object.entries({x: -96, y: -22, width: 192, height: 52, rx: 7})) box.setAttribute(attr, val);
    const label = document.createElementNS(NS, "text"); label.setAttribute("text-anchor", "middle"); label.setAttribute("y", "0");
    const caption = `${cite.document_id || "Source"} · ${cite.version_id || "?"}`;
    const name = cite.document_id || "Source";
    label.textContent = name.length > 17 ? `${name.slice(0, 15)}…` : name;
    const revision = document.createElementNS(NS, "text"); revision.setAttribute("text-anchor", "middle"); revision.setAttribute("y", "20"); revision.setAttribute("class", "source-revision");
    const version = cite.version_id || "Unknown revision";
    revision.textContent = version.length > 24 ? `${version.slice(0, 22)}…` : version;
    const title = document.createElementNS(NS, "title"); title.textContent = caption;
    node.append(box, label, revision, title); reveal(node, `source:${key}`, 400);
    const activate = () => { if (!state.busy) tracePreview(source.item); };
    node.addEventListener("click", activate); node.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); activate(); } });
    node.addEventListener("mouseenter", activate); node.addEventListener("focus", activate);
    sourceLayer.append(node);
  }
  $("graph-note").textContent = assertions.length
    ? `${entities.size} nodes · ${edges.length} relationships · ${layout.components} connected group${layout.components === 1 ? "" : "s"}${edges.length < assertions.length ? ` · ${assertions.length - edges.length} omitted by 100-node/200-edge display caps` : ""}. Retrieved subset only. Hover or focus nodes for labels and related findings.`
    : "";
  if (live) {
    $("graph-note").textContent = `${entities.size} entities · ${edges.length} relationships · ${sources.size} source revision${sources.size === 1 ? "" : "s"}${new Set(items.map(sourceKey)).size > sources.size ? " shown (display cap)" : ""}. Retrieved preview only; dotted links trace source support.`;
    preview.graphIds = seen;
  }
  $("graph-note").hidden = live ? !items.length : !assertions.length;
  summary = $("graph-note").textContent;
  if ($("graph-empty")) $("graph-empty").hidden = !!(edges.length || sources.size);
  if (!live) seedSummary();
}

function evidenceView(item) {
  const cite = item.evidence || item;
  $("evidence-meta").textContent = `${cite.document_id || "Source"} · ${cite.version_id || "Unknown revision"}`;
  $("evidence-text").textContent = item.text || "No passage returned.";
  $("evidence-details").textContent = JSON.stringify(item, null, 2);
  const facts = $("evidence-facts");
  if (facts) {
    facts.replaceChildren();
    const fields = [["Source status", cite.source_status || "Unknown"], ["Evidence", item.assertion_id ? `${item.modality || "Unknown modality"} · ${item.method || "Method unspecified"}` : "Exact source passage"], ["Source available", dateLabel(cite.source_available_at, true)], ["Known from", dateLabel(item.recorded_at || cite.visible_from, true)], ["Applies", item.assertion_id ? intervalLabel(item) : "No assertion interval"], ["Passage", `Characters ${cite.start ?? "?"}–${cite.end ?? "?"}`]];
    if (item.disputed) fields.splice(1, 0, ["Review signal", "Conflicting support in this scope"]);
    if (item.status === "superseded") fields.splice(1, 0, ["Assertion status", "Superseded"]);
    for (const [label, detail] of fields) facts.append(text("dt", label), text("dd", detail));
  }
}

async function openEvidence(item, side = null) {
  const scope = state.run?.scope;
  if (!scope) return;
  let snapshotId = scope.snapshot_id, cutoff = scope.knowledge_cutoff;
  if (scope.baseline_id) {
    snapshotId = scope.mode === "world_state_change" ? scope.analysis_snapshot_id : side === "before" ? scope.baseline_snapshot_id : scope.target_snapshot_id;
    if (side === "before" && scope.mode !== "world_state_change") {
      const baseline = await request("baseline_get", {baseline_id: scope.baseline_id});
      cutoff = baseline.scope.knowledge_cutoff;
    }
  }
  const data = {corpus_id: scope.corpus_id, snapshot_id: snapshotId, knowledge_cutoff: cutoff, history: false};
  if (item.assertion_id) data.assertion_id = item.assertion_id; else data.chunk_id = item.chunk_id || item.id;
  const evidence = await request("evidence", data);
  evidenceView(evidence);
  traceGraph(item);
  document.querySelectorAll(".finding").forEach(card => card.classList.toggle("active", card.dataset.findingId === item.id));
  const heading = $("evidence-title"); heading.setAttribute("tabindex", "-1"); heading.focus({preventScroll: true});
  if (window.innerWidth < 1200) heading.scrollIntoView({block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
}

function finding(item) {
  const card = text("article", "", "finding");
  card.dataset.findingId = item.id;
  const head = text("div", "", "finding-head");
  if (state.run?.operation === "search") {
    const choice = document.createElement("input"); choice.type = "checkbox"; choice.checked = state.selected.has(item.id); choice.setAttribute("aria-label", `Include ${item.id} in a saved-findings baseline`);
    choice.addEventListener("change", () => { if (choice.checked) state.selected.add(item.id); else state.selected.delete(item.id); updateControls(); }); head.append(choice);
  }
  const identifier = text("span", item.subject_label && item.object_label ? `${item.subject_label} → ${item.object_label}` : item.evidence?.document_id || "Source passage"); identifier.title = item.id;
  head.append(identifier); card.append(head, text("p", item.text, "finding-text"));
  const chips = text("div", "", "chips");
  chips.append(text("span", item.assertion_id ? "Relationship" : "Source passage", "chip"));
  if (item.modality) chips.append(text("span", item.modality, `chip${item.modality === "planned" ? " warn" : ""}`));
  if (item.method) chips.append(text("span", methodLabel(item.method), "chip"));
  if (item.disputed) chips.append(text("span", "Disputed", "chip conflict"));
  if (item.temporal_status?.from === "unknown" || item.temporal_status?.to === "unknown") chips.append(text("span", "Time unknown", "chip warn"));
  card.append(chips);
  const cite = item.evidence || {};
  card.append(text("p", `${cite.document_id || "Source"} · ${cite.version_id || "unknown revision"}`, "subtle"));
  const actions = text("div", "", "actions"), inspect = text("button", "Open exact evidence", "secondary");
  inspect.addEventListener("click", () => action(inspect, () => openEvidence(item))); actions.append(inspect); card.append(actions);
  return card;
}

function changeCard(change) {
  const card = text("article", "", "finding");
  card.append(text("p", (change.categories || [change.category]).map(item => item.replaceAll("_", " ")).join(" · "), "finding-text"));
  card.append(text("p", change.matching_basis || change.uncertainty || "Change candidate; inspect both sides.", "subtle"));
  const pair = text("div", "", "change-pair");
  for (const side of ["before", "after"]) {
    const panel = text("div", ""); panel.append(text("h4", side));
    if (!(change[side] || []).length) panel.append(text("p", "No eligible support on this side."));
    for (const item of change[side] || []) {
      panel.append(text("p", item.text));
      const inspect = text("button", `Inspect ${side} source`, "secondary"); inspect.title = item.id;
      inspect.addEventListener("click", () => action(inspect, () => openEvidence(item, side))); panel.append(inspect);
    }
    pair.append(panel);
  }
  card.append(pair); return card;
}

function renderRun(run, append = false) {
  if (append && state.run?.run_id !== run.run_id) return;
  state.run = run;
  $("download").disabled = false;
  $("run-details").textContent = JSON.stringify({scope: run.scope, coverage: run.coverage, usage: run.usage, budget: run.budget, stop_reasons: run.stop_reasons, notice: run.notice, retrieval_channels: [...new Set((run.items || []).map(item => item.selection_reason?.channel).filter(Boolean))]}, null, 2);
  if (!append) { $("results").replaceChildren(); state.items = []; state.selected.clear(); state.seeds.clear(); clearEvidence(); zoomGraph(0); }
  if (run.operation === "compare") {
    state.searchRun = null;
    $("results-title").textContent = "Change review";
    for (const change of run.changes || []) $("results").append(changeCard(change));
    if (!(run.changes || []).length) $("results").append(text("p", "No changes found within the examined scope.", "empty"));
    state.items = [...(run.changes || []).flatMap(change => change.after || []), ...(run.unchanged || [])];
    const count = run.changes?.length || 0, unchanged = run.unchanged?.length || 0;
    $("result-summary").textContent = `${count} change candidate${count === 1 ? "" : "s"} · ${unchanged} unchanged item${unchanged === 1 ? "" : "s"} · ${run.truncated ? "Partial: budget reached" : "Within examined scope"}`;
  } else {
    state.searchRun = append ? state.searchRun : run;
    $("results-title").textContent = "Retrieved evidence";
    for (const item of run.items || []) { state.selected.add(item.id); state.items.push(item); $("results").append(finding(item)); }
    if (!state.items.length) $("results").append(text("p", "No evidence matched these filters. Adjust the query or scope.", "empty"));
    $("result-summary").textContent = `${state.items.length} of ${run.total_returned ?? state.items.length} retained findings · ${snapshotLabel(run.scope.snapshot_id)}${run.truncated ? " · Partial: " + (run.stop_reasons || []).join(", ") : ""}`;
  }
  $("more").hidden = !run.next_cursor;
  graph(state.items);
}

document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", () => showPanel(tab.dataset.panel)));
$("guide-query").addEventListener("input", updateControls);
$("guide-query").addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); action($("guide-primary"), advanceGuide); } });
$("guide-primary").addEventListener("click", () => action($("guide-primary"), advanceGuide));
$("guide-target").addEventListener("change", updateControls);
$("guide-back").addEventListener("click", () => goGuideStep(guide.step - 1));
$("guide-explore").addEventListener("click", () => { showPanel("search-panel"); $("query").focus(); });
$("query").addEventListener("input", event => { if (!event.isComposing) schedulePreview(); });
$("query").addEventListener("compositionstart", () => { preview.composing = true; stopPreview(); });
$("query").addEventListener("compositionend", () => { preview.composing = false; schedulePreview(); });
$("query").addEventListener("keydown", event => { if (event.key === "Escape") { stopPreview(); event.preventDefault(); } });
for (const id of ["mode", "vector-index"]) $(id).addEventListener("change", () => { stopPreview(); schedulePreview(); });
for (const id of ["knowledge", "valid-time"]) $(id).addEventListener("input", () => { stopPreview(); schedulePreview(); });
$("live-toggle").addEventListener("click", () => {
  preview.enabled = !preview.enabled;
  $("live-toggle").setAttribute("aria-pressed", String(preview.enabled));
  stopPreview(); if (preview.enabled) schedulePreview();
});
document.addEventListener("visibilitychange", () => { if (document.hidden) stopPreview(); });
$("refresh").addEventListener("click", () => action($("refresh"), async () => { await bootstrap(); message(""); }));
$("corpus").addEventListener("change", () => action(null, async () => {
  const chosen = value("corpus"); $("corpus").value = state.activeCorpus;
  if (!await confirmDiscard()) return;
  $("corpus").value = chosen; resetInvestigation(); clearRun(); await loadCorpus(); message("");
}));
$("snapshot").addEventListener("change", selectSnapshot);
for (const id of ["mode", "vector-index", "compare-mode", "baseline-kind", "investigation"]) $(id).addEventListener("change", updateControls);

$("search-form").addEventListener("submit", event => { event.preventDefault(); action(event.submitter, async () => {
  await runSearch();
}); });
$("more").addEventListener("click", () => action($("more"), async () => { const run = await request("page", {cursor: state.run.next_cursor}); renderRun(run, true); }));
$("clear-seeds").addEventListener("click", () => { state.seeds.clear(); graph(state.items); });

$("save-baseline").addEventListener("click", () => action($("save-baseline"), async () => {
  if (!state.searchRun) throw new Error("Run a search before saving a baseline.");
  if (state.searchRun.scope.corpus_id !== corpus()) throw new Error("The current search belongs to another corpus. Run a search in the selected corpus.");
  const kind = value("baseline-kind");
  if (kind === "saved_findings" && !state.selected.size) throw new Error("Select at least one finding in the result list.");
  if (kind === "entity_neighborhood" && !state.seeds.size) throw new Error("Select at least one graph node as a seed.");
  const baseline = await request("baseline_save", {run_id: state.searchRun.run_id, kind, finding_ids: kind === "saved_findings" ? [...state.selected] : null, seed_entity_ids: kind === "entity_neighborhood" ? [...state.seeds] : null, hops: 1});
  await refreshLists(); $("baseline").value = baseline.baseline_id; baselineModes(); message(`Baseline saved: ${snapshotLabel(state.searchRun.scope.snapshot_id)}.`);
}));
$("baseline").addEventListener("change", baselineModes);
$("compare-form").addEventListener("submit", event => { event.preventDefault(); action(event.submitter, async () => {
  if (!value("baseline")) throw new Error("Save or select a baseline first.");
  const world = value("compare-mode") === "world_state_change";
  const run = await request("compare", {baseline_id: value("baseline"), target_snapshot_id: snapshot(), mode: value("compare-mode"), knowledge_cutoff: optional("compare-knowledge"), valid_from_time: world ? optional("compare-from") : null, valid_to_time: world ? optional("compare-to") : null});
  renderRun(run); message("");
}); });

$("new-investigation").addEventListener("click", () => action($("new-investigation"), async () => {
  if (!await confirmDiscard()) return;
  resetInvestigation(); $("investigation-question").value = value("query"); message("");
}));
$("load-investigation").addEventListener("click", () => action($("load-investigation"), async () => {
  if (!value("investigation")) throw new Error("Select a saved investigation.");
  if (!await confirmDiscard()) return;
  message("");
  const saved = await request("investigation_get", {investigation_id: value("investigation")});
  await bootstrap(saved.corpus_id, saved.snapshot_id);
  clearRun();
  state.investigation = saved; state.dirty = false;
  $("investigation-title").value = saved.title; $("investigation-question").value = saved.question;
  $("notes").value = Array.isArray(saved.notes) ? saved.notes.join("\n") : saved.notes || "";
  $("investigation-status").value = saved.status || "active";
  if (saved.run_ids?.length) {
    try {
      const restored = await request("run_get", {run_id: saved.run_ids[saved.run_ids.length - 1]});
      renderRun(restored);
      if (restored.operation === "search") {
        $("query").value = restored.query; $("mode").value = restored.scope.mode;
        $("knowledge").value = restored.scope.knowledge_cutoff || "";
        $("valid-time").value = restored.scope.valid_time || "";
        $("vector-index").value = restored.scope.vector_index_id || "";
        $("advanced-search").open = !!(restored.scope.valid_time || restored.scope.vector_index_id);
      }
    } catch (error) { message(`Notes opened. Saved evidence could not be restored: ${error.message}`, true); }
  }
  state.seeds = new Set(saved.view?.selected_entity_ids || []); seedSummary();
  if (Array.isArray(saved.view?.selected_finding_ids) && state.run?.operation === "search") {
    state.selected = new Set(saved.view.selected_finding_ids.filter(id => state.items.some(item => item.id === id)));
    $("results").querySelectorAll('.finding').forEach(card => { const choice = card.querySelector('input[type="checkbox"]'); if (choice) choice.checked = state.selected.has(card.dataset.findingId); });
  }
  if (saved.baseline_ids?.length) { $("baseline").value = saved.baseline_ids[0]; baselineModes(); }
  graph(state.items);
  $("investigation-context").textContent = `Saved version ${saved.version} · ${snapshotLabel(saved.snapshot_id)}. Notes are analyst observations.`;
  if (!$("message").classList.contains("error")) message("");
}));
$("investigation-form").addEventListener("submit", event => { event.preventDefault(); action(event.submitter, async () => {
  const selectedCorpus = corpus();
  const runIds = [...new Set([...(state.investigation?.run_ids || []), ...(state.run?.scope.corpus_id === selectedCorpus ? [state.run.run_id] : [])])];
  const baselineIds = [...new Set([...(state.investigation?.baseline_ids || []), ...(value("baseline") ? [value("baseline")] : [])])];
  const data = {corpus_id: selectedCorpus, snapshot_id: snapshot(), title: value("investigation-title"), question: value("investigation-question"), notes: $("notes").value, status: value("investigation-status"), run_ids: runIds, baseline_ids: baselineIds, view: {selected_entity_ids: [...state.seeds], selected_finding_ids: [...state.selected]}};
  if (state.investigation) data.investigation_id = state.investigation.investigation_id;
  const saved = await request("investigation_save", {data, expected_version: state.investigation?.version ?? null});
  state.investigation = saved; state.dirty = false; await refreshLists(); $("investigation").value = saved.investigation_id;
  $("investigation-context").textContent = `Saved version ${saved.version} · ${snapshotLabel(saved.snapshot_id)}. Notes are analyst observations.`;
  message(`Investigation saved · version ${saved.version}.`);
}); });

$("investigation-form").addEventListener("input", () => { state.dirty = true; $("investigation-context").textContent = "Unsaved changes."; });
window.addEventListener("beforeunload", event => { if (state.dirty) { event.preventDefault(); event.returnValue = ""; } });

$("clear-selection")?.addEventListener("click", () => {
  state.selected.clear(); $("results").querySelectorAll('input[type="checkbox"]').forEach(input => { input.checked = false; }); updateControls();
});
function zoomGraph(factor) {
  state.zoom = factor === 0 ? 1 : Math.min(3, Math.max(0.7, state.zoom * factor));
  const width = 640 / state.zoom, height = 430 / state.zoom;
  $("graph").setAttribute("viewBox", `${(640 - width) / 2} ${(430 - height) / 2} ${width} ${height}`);
}
$("graph-zoom-in")?.addEventListener("click", () => zoomGraph(1.25));
$("graph-zoom-out")?.addEventListener("click", () => zoomGraph(0.8));
$("graph-reset")?.addEventListener("click", () => zoomGraph(0));
document.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key === "k") { event.preventDefault(); if (!state.busy) { showPanel("search-panel"); $("query").focus(); } }
});

async function loadFile(input, target) {
  const file = input.files[0]; if (!file) return;
  if (file.size > state.maxBytes) throw new Error("File exceeds the browser request limit. Use smaller batches or the CLI.");
  $(target).value = new TextDecoder("utf-8", {fatal: true}).decode(await file.arrayBuffer());
}
$("document-file").addEventListener("change", () => action(null, () => loadFile($("document-file"), "records-jsonl")));
$("assertion-file").addEventListener("change", () => action(null, () => loadFile($("assertion-file"), "assertions-json")));
$("ingest-form").addEventListener("submit", event => { event.preventDefault(); action(event.submitter, async () => {
  const importingCorpus = value("import-corpus");
  const result = await request("ingest", {corpus_id: value("import-corpus"), idempotency_key: value("import-key"), records_jsonl: $("records-jsonl").value});
  $("job-id").value = result.job_id; $("job-report").textContent = JSON.stringify(result, null, 2);
  await bootstrap(); $("import-corpus").value = importingCorpus;
  message("Batch staged. Review rejected records before publishing.");
}); });
$("stage-assertions").addEventListener("click", () => action($("stage-assertions"), async () => {
  if (!value("job-id")) throw new Error("Stage documents or enter a job ID first.");
  const assertions = JSON.parse($("assertions-json").value);
  if (!Array.isArray(assertions)) throw new Error("Authored assertions must be a JSON array.");
  const result = await request("assertions", {job_id: value("job-id"), assertions});
  $("job-report").textContent = JSON.stringify(result, null, 2); message("Authored assertions staged.");
}));
for (const [button, operation] of [["job-status", "job"], ["cancel-job", "cancel"]]) $(button).addEventListener("click", () => action($(button), async () => {
  if (!value("job-id")) throw new Error("Enter a job ID.");
  const result = await request(operation, {job_id: value("job-id")}); $("job-report").textContent = JSON.stringify(result, null, 2); message(operation === "cancel" ? "Job cancelled." : "Job status updated.");
}));
$("publish").addEventListener("click", () => action($("publish"), async () => {
  if (!value("job-id")) throw new Error("Enter a staged job ID.");
  const result = await request("publish", {job_id: value("job-id"), label: optional("publish-label"), allow_exclusions: $("allow-exclusions").checked});
  $("job-report").textContent = JSON.stringify(result, null, 2);
  const importingCorpus = value("import-corpus"); await bootstrap(); $("import-corpus").value = importingCorpus;
  message("Snapshot published. Select it to explore the update.");
}));

$("download").addEventListener("click", () => action($("download"), async () => {
  if (!state.run) throw new Error("Run a search or comparison first.");
  const blob = await request("export", {run_id: state.run.run_id}, true), url = URL.createObjectURL(blob);
  const link = document.createElement("a"); link.href = url; link.download = "graphrag-evidence.zip"; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000); message("Evidence bundle downloaded.");
}));

action(null, async () => { await bootstrap(); showPanel("start-panel"); });
