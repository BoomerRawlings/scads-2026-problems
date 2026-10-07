"use strict";

// Run the production script in a small DOM/fetch double. This verifies state
// transitions, not layout, browser accessibility, or native dialog behavior.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const project = path.resolve(__dirname, "..");
const script = fs.readFileSync(path.join(project, "static/app.js"), "utf8");
const markup = fs.readFileSync(path.join(project, "static/index.html"), "utf8");
const settle = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return {promise, resolve, reject}; };

class Timers {
  constructor() { this.now = 0; this.next = 0; this.jobs = new Map(); }
  setTimeout(callback, delay = 0, ...args) { const id = ++this.next; this.jobs.set(id, {at: this.now + Math.max(0, delay), callback: () => callback(...args)}); return id; }
  clearTimeout(id) { this.jobs.delete(id); }
  async advance(milliseconds) {
    const end = this.now + milliseconds;
    for (let guard = 0; guard < 1000; guard += 1) {
      const ready = [...this.jobs.entries()].filter(([, job]) => job.at <= end).sort((a, b) => a[1].at - b[1].at || a[0] - b[0])[0];
      if (!ready) { this.now = end; await settle(); return; }
      this.jobs.delete(ready[0]); this.now = ready[1].at; ready[1].callback(); await settle();
    }
    throw new Error("Unexpected timer loop in frontend test");
  }
}

class Events {
  constructor() { this.listeners = new Map(); }
  addEventListener(type, handler, options = {}) { const handlers = this.listeners.get(type) || []; handlers.push({handler, once: options.once}); this.listeners.set(type, handlers); }
  removeEventListener(type, handler) { this.listeners.set(type, (this.listeners.get(type) || []).filter(entry => entry.handler !== handler)); }
  dispatchEvent(event) {
    event.target ||= this;
    event.preventDefault ||= () => { event.defaultPrevented = true; };
    if (typeof this[`on${event.type}`] === "function") this[`on${event.type}`](event);
    for (const entry of [...(this.listeners.get(event.type) || [])]) {
      if (entry.once) this.removeEventListener(event.type, entry.handler);
      entry.handler(event);
    }
    return !event.defaultPrevented;
  }
}

class TextNode {
  constructor(content) { this.textContent = String(content); this.parentElement = null; }
  remove() { if (this.parentElement) this.parentElement._nodes = this.parentElement._nodes.filter(child => child !== this); this.parentElement = null; }
  get isConnected() { return !!this.parentElement?.isConnected; }
}

class Element extends Events {
  constructor(tag = "div") {
    super(); this.tagName = tag.toUpperCase(); this._nodes = []; this.attributes = {}; this.dataset = {};
    const properties = new Map(); this.style = {setProperty: (name, value) => properties.set(name, String(value)), getPropertyValue: name => properties.get(name) || ""};
    this.className = ""; this.hidden = false; this.disabled = false; this.checked = false; this._value = ""; this._text = "";
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      add: (...names) => { this.className = [...new Set([...this.className.split(/\s+/).filter(Boolean), ...names])].join(" "); },
      remove: (...names) => { this.className = this.className.split(/\s+/).filter(name => !names.includes(name)).join(" "); },
      toggle: (name, force) => { const on = force ?? !this.classList.contains(name); this.classList[on ? "add" : "remove"](name); return on; }
    };
  }
  set textContent(value) { for (const child of this._nodes) child.parentElement = null; this._nodes = []; if (String(value ?? "")) this.append(new TextNode(value)); }
  get textContent() { return this._nodes.map(child => child.textContent || "").join(""); }
  set innerHTML(value) { this.textContent = value; }
  get innerHTML() { return this.textContent; }
  set value(value) { this._value = String(value); }
  get value() { return this._value || (this.tagName === "SELECT" ? this.children[0]?.value || "" : ""); }
  set type(value) { this.attributes.type = String(value); }
  get type() { return this.attributes.type || ""; }
  get children() { return this._nodes.filter(child => child instanceof Element); }
  get options() { return this.children; }
  get childNodes() { return this._nodes; }
  get isConnected() { return this.tagName === "DOCUMENT" || !!this.parentElement?.isConnected; }
  append(...children) { for (let child of children) { if (typeof child !== "object") child = new TextNode(child); child.remove(); child.parentElement = this; this._nodes.push(child); } }
  appendChild(child) { this.append(child); return child; }
  replaceChildren(...children) { this.textContent = ""; this._value = ""; this.append(...children); }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === "class") this.className = String(value);
    if (name === "id") this.id = String(value);
    if (name === "value") this.value = value;
    if (name === "type") this.type = value;
    if (name.startsWith("data-")) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase())] = String(value);
  }
  getAttribute(name) { return this.attributes[name] ?? null; }
  hasAttribute(name) { return name in this.attributes; }
  removeAttribute(name) { delete this.attributes[name]; }
  matches(selector) {
    const not = selector.match(/:not\(([^)]+)\)/); if (not && this.matches(not[1])) return false;
    selector = selector.replace(/:not\([^)]+\)/g, "").trim();
    if (selector === "*") return true;
    const attr = selector.match(/\[([\w-]+)(?:=["']?([^\]"']+)["']?)?\]/);
    if (attr && (attr[2] !== undefined ? this.getAttribute(attr[1]) !== attr[2] : this.getAttribute(attr[1]) === null)) return false;
    const id = selector.match(/#([\w-]+)/); if (id && this.id !== id[1]) return false;
    for (const match of selector.matchAll(/\.([\w-]+)/g)) if (!this.classList.contains(match[1])) return false;
    const tag = selector.match(/^[a-z][\w-]*/i); return !tag || this.tagName === tag[0].toUpperCase();
  }
  querySelectorAll(selector) {
    const selectors = selector.split(",").map(value => value.trim()), result = [];
    for (const child of this.children) if (child instanceof Element) { if (selectors.some(item => child.matches(item))) result.push(child); result.push(...child.querySelectorAll(selector)); }
    return result;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; }
  focus() { this.focused = true; let root = this; while (root.parentElement) root = root.parentElement; if (root.tagName === "DOCUMENT") root.activeElement = this; }
  scrollIntoView() {}
  reset() { for (const child of this.querySelectorAll("input, select, textarea")) { child.value = child.getAttribute("value") || ""; child.checked = child.getAttribute("checked") !== null; } }
  remove() { if (this.parentElement) this.parentElement._nodes = this.parentElement._nodes.filter(child => child !== this); this.parentElement = null; }
  click() { if (!this.disabled) this.dispatchEvent({type: "click"}); }
  showModal() { this.open = true; }
  close(value = "") { this.returnValue = value; this.open = false; this.dispatchEvent({type: "close"}); }
}

function documentDouble() {
  const document = new Element("document"), stack = [document];
  for (const token of markup.matchAll(/<\/?[a-z][^>]*>/gi)) {
    const tag = token[0].match(/^<\/?([a-z][\w-]*)/i)[1].toLowerCase();
    if (token[0].startsWith("</")) { while (stack.length > 1 && stack.pop().tagName !== tag.toUpperCase()) {} continue; }
    const node = new Element(tag);
    for (const attr of token[0].slice(tag.length + 1, -1).matchAll(/([\w-]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) node.setAttribute(attr[1], attr[2] ?? attr[3] ?? attr[4] ?? "");
    node.hidden = "hidden" in node.attributes; node.disabled = "disabled" in node.attributes;
    stack.at(-1).append(node); if (tag === "body") document.body = node;
    if (!["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"].includes(tag)) stack.push(node);
  }
  document.getElementById = id => document.querySelector(`#${id}`);
  document.createElement = tag => new Element(tag);
  document.createElementNS = (_, tag) => new Element(tag);
  return document;
}

function response(data, status = 200) { return {ok: status >= 200 && status < 300, status, headers: {get: () => "application/json"}, json: async () => data}; }

async function app({timers = null, reducedMotion = false} = {}) {
  const document = documentDouble(), window = new Events(), calls = [];
  const schedule = timers ? timers.setTimeout.bind(timers) : setTimeout;
  const cancel = timers ? timers.clearTimeout.bind(timers) : clearTimeout;
  window.innerWidth = 1440;
  window.matchMedia = () => ({matches: reducedMotion, addEventListener() {}, removeEventListener() {}});
  const context = vm.createContext({document, window, console, TextEncoder, TextDecoder, URL, AbortController, AbortSignal, setTimeout: schedule, clearTimeout: cancel,
    requestAnimationFrame: callback => schedule(() => callback(timers?.now || 0), 0), cancelAnimationFrame: cancel,
    Option: function(label, value) { const node = new Element("option"); node.textContent = label; node.setAttribute("value", value); return node; },
    fetch: async (url, options) => { calls.push({url, options}); return response({ok: true, data: {csrf_token: "test-token", limits: {request_bytes: 1048576}, corpora: []}}); }
  });
  vm.runInContext(script, context, {filename: "static/app.js"});
  await settle();
  const execute = code => vm.runInContext(code, context);
  return {context, document, window, calls, execute, state: execute("state"), node: id => document.getElementById(id)};
}

test("request preserves typed server failures and uses the bootstrap CSRF token", async () => {
  const ui = await app();
  ui.context.fetch = async (url, options) => {
    assert.equal(url, "/api/search"); assert.equal(options.headers["X-CSRF-Token"], "test-token");
    return response({ok: false, error: {code: "scope_mismatch", message: "Different corpus", details: {field: "corpus"}}}, 400);
  };
  await assert.rejects(ui.execute('request("search", {query: "pump"})'), error => error.message.includes("scope_mismatch") && error.details.field === "corpus");
});

test("oversized requests fail before fetch dispatch", async () => {
  const ui = await app(); ui.state.maxBytes = 8; let calls = 0;
  ui.context.fetch = async () => { calls += 1; };
  await assert.rejects(ui.execute('request("search", {query: "longer than allowance"})'));
  assert.equal(calls, 0);
});

test("an active action locks editing and ignores overlapping work", async () => {
  const ui = await app(), pending = deferred(); let duplicateCalls = 0;
  ui.context.pending = pending.promise;
  const active = ui.execute('action(document.getElementById("refresh"), () => pending)');
  assert.equal(ui.state.busy, true);
  assert.equal(ui.node("notes").disabled, true);
  assert.equal(ui.node("corpus").disabled, true);
  ui.context.overlap = () => { duplicateCalls += 1; };
  await ui.execute('action(null, overlap)');
  assert.equal(duplicateCalls, 0);
  pending.resolve(); await active;
  assert.equal(ui.state.busy, false);
  assert.equal(ui.node("notes").disabled, false);
});

test("failed actions release the lock without enabling unavailable result actions", async () => {
  const ui = await app();
  await ui.execute('action(null, async () => { throw new Error("Fixture transport failure"); })');
  assert.equal(ui.state.busy, false);
  assert.equal(ui.node("notes").disabled, false);
  assert.equal(ui.node("download").disabled, true);
  assert.match(ui.node("message").textContent, /Fixture transport failure/);
});

test("temporary action feedback preserves button icons and nested markup", async () => {
  const ui = await app(), button = ui.node("download");
  assert.ok(button.querySelector("svg"), "Exercise the real export icon from HTML");
  await ui.execute('action(document.getElementById("download"), async () => {})');
  assert.ok(button.querySelector("svg"), "Busy feedback must not erase the icon");
});

test("clearing a run removes stale evidence, selection, and pagination", async () => {
  const ui = await app();
  ui.state.run = {run_id: "old", next_cursor: "old-page"}; ui.state.searchRun = ui.state.run;
  ui.state.items = [{id: "old"}]; ui.state.selected.add("old"); ui.state.seeds.add("old-entity");
  ui.node("evidence-text").textContent = "OLD PRIVATE CONTEXT";
  ui.node("evidence-meta").textContent = "OLD PRIVATE CONTEXT";
  ui.node("evidence-details").textContent = "OLD PRIVATE CONTEXT";
  ui.execute("clearRun()");
  assert.equal(ui.state.run, null); assert.equal(ui.state.searchRun, null);
  assert.equal(ui.state.selected.size, 0); assert.equal(ui.state.seeds.size, 0); assert.equal(ui.state.items.length, 0);
  for (const id of ["evidence-text", "evidence-meta", "evidence-details"]) assert.doesNotMatch(ui.node(id).textContent, /OLD PRIVATE CONTEXT/);
  assert.equal(ui.node("download").disabled, true); assert.equal(ui.node("more").hidden, true);
});

test("a stale corpus response cannot replace the newly selected corpus", async () => {
  const ui = await app(), first = deferred();
  ui.node("corpus").value = "old-corpus";
  ui.context.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    if (body.corpus_id === "old-corpus") return first.promise;
    const data = url.endsWith("snapshots") ? [{snapshot_id: "new-snapshot", label: "New", published_at: "2025-01-01T00:00:00Z", capabilities: ["lexical"], coverage: {}}] : url.endsWith("status") ? {vector_indexes: []} : [];
    return response({ok: true, data});
  };
  const stale = ui.execute("loadCorpus()");
  ui.node("corpus").value = "new-corpus";
  await ui.execute("loadCorpus()");
  first.resolve(response({ok: true, data: []})); await stale;
  assert.equal(ui.node("corpus").value, "new-corpus");
  assert.equal(ui.node("snapshot").value, "new-snapshot");
  assert.equal(ui.state.snapshots[0].snapshot_id, "new-snapshot");
});

test("a clean investigation does not prompt for discarded edits", async () => {
  const ui = await app(); ui.state.dirty = false;
  assert.equal(await ui.execute("confirmDiscard()"), true);
});

test("failed corpus loading cannot leave another corpus's choices usable", async () => {
  const ui = await app();
  ui.state.activeCorpus = "original";
  ui.state.snapshots = [{snapshot_id: "original-snapshot"}];
  ui.state.baselines = [{baseline_id: "original-baseline"}];
  for (const [id, value] of [["snapshot", "original-snapshot"], ["baseline", "original-baseline"], ["investigation", "original-investigation"], ["vector-index", "original-vectors"]]) ui.node(id).value = value;
  ui.node("corpus").value = "different";
  ui.context.fetch = async () => response({ok: false, error: {code: "temporarily_unavailable", message: "Fixture service failure"}}, 503);
  await assert.rejects(ui.execute("loadCorpus()"), /Fixture service failure/);
  assert.equal(ui.state.snapshots.length, 0); assert.equal(ui.state.baselines.length, 0);
  for (const id of ["snapshot", "baseline", "investigation", "vector-index"]) assert.equal(ui.node(id).value, "", id);
  ui.execute("updateControls()");
  assert.equal(ui.node("search-form").querySelector('button[type="submit"]').disabled, true);
});

test("unsaved investigation edits trigger the browser leave guard", async () => {
  const ui = await app(); ui.state.dirty = true;
  const event = {type: "beforeunload"}; ui.window.dispatchEvent(event);
  assert.equal(event.defaultPrevented, true);
  ui.state.dirty = false;
  const clean = {type: "beforeunload"}; ui.window.dispatchEvent(clean);
  assert.notEqual(clean.defaultPrevented, true);
});

test("controls created during a request join the lock and recover afterward", async () => {
  const ui = await app(), pending = deferred(); ui.context.pending = pending.promise;
  const active = ui.execute("action(null, () => pending)");
  const added = ui.document.createElement("button"); ui.document.body.append(added);
  ui.execute("updateControls()");
  assert.equal(added.disabled, true);
  pending.resolve(); await active;
  assert.equal(added.disabled, false);
});

test("editing investigation fields marks the draft dirty", async () => {
  const ui = await app(); assert.equal(ui.state.dirty, false);
  ui.node("notes").value = "Unpublished analyst observations";
  ui.node("investigation-form").dispatchEvent({type: "input", target: ui.node("notes")});
  assert.equal(ui.state.dirty, true);
});

test("Keep and Escape retain unsaved notes; Discard requires explicit acceptance", async () => {
  const ui = await app(); ui.state.dirty = true;
  ui.node("notes").value = "Unpublished analyst observations";
  const dialog = ui.node("draft-dialog"); assert.ok(dialog, "HTML must include the discard dialog");
  let answer = ui.execute("confirmDiscard()");
  assert.equal(dialog.open, true);
  ui.node("draft-keep").click(); assert.equal(await answer, false);
  assert.equal(dialog.open, false); assert.equal(ui.state.dirty, true);
  assert.equal(ui.node("notes").value, "Unpublished analyst observations");
  answer = ui.execute("confirmDiscard()");
  const cancellation = {type: "cancel"}; dialog.dispatchEvent(cancellation);
  assert.equal(await answer, false); assert.equal(cancellation.defaultPrevented, true);
  assert.equal(ui.node("notes").value, "Unpublished analyst observations");
  answer = ui.execute("confirmDiscard()");
  ui.node("draft-discard").click(); assert.equal(await answer, true);
  assert.equal(dialog.open, false);
});

test("declining a corpus switch keeps draft identity, notes, and existing results", async () => {
  const ui = await app();
  ui.state.activeCorpus = "original"; ui.state.dirty = true;
  ui.state.investigation = {investigation_id: "draft-original", corpus_id: "original"};
  ui.state.run = {run_id: "original-run", operation: "search", scope: {corpus_id: "original"}};
  ui.node("notes").value = "Original unsaved note";
  ui.node("corpus").value = "another";
  let dispatched = 0; ui.context.fetch = async () => { dispatched += 1; throw new Error("Must not fetch after declined discard"); };
  ui.node("corpus").dispatchEvent({type: "change"});
  await settle();
  assert.equal(ui.node("draft-dialog").open, true);
  ui.node("draft-keep").click(); await settle();
  assert.equal(ui.node("corpus").value, "original");
  assert.equal(ui.state.investigation.investigation_id, "draft-original");
  assert.equal(ui.state.run.run_id, "original-run");
  assert.equal(ui.node("notes").value, "Original unsaved note");
  assert.equal(dispatched, 0); assert.equal(ui.state.busy, false);
});

test("comparison evidence uses each endpoint's active support, not historical conflicts", async () => {
  const ui = await app(), requests = [];
  const earlier = "2025-01-10T00:00:00Z", later = "2025-02-10T00:00:00Z";
  ui.state.run = {operation: "compare", scope: {corpus_id: "original", baseline_id: "baseline", mode: "knowledge_change", baseline_snapshot_id: "earlier", target_snapshot_id: "later", analysis_snapshot_id: "later", knowledge_cutoff: later}};
  ui.context.fetch = async (url, options) => {
    const body = JSON.parse(options.body); requests.push({url, body});
    return response({ok: true, data: url.endsWith("baseline_get") ? {scope: {knowledge_cutoff: earlier}} : {text: "Exact endpoint evidence", document_id: "source", version_id: "v1", start: 0, end: 23, source_status: "active"}});
  };
  await ui.execute('openEvidence({id: "claim", assertion_id: "claim"}, "before")');
  await ui.execute('openEvidence({id: "claim", assertion_id: "claim"}, "after")');
  ui.state.run.scope.mode = "world_state_change";
  await ui.execute('openEvidence({id: "claim", assertion_id: "claim"}, "before")');
  const evidence = requests.filter(item => item.url === "/api/evidence").map(item => item.body);
  assert.deepEqual(evidence.map(item => [item.snapshot_id, item.knowledge_cutoff, item.history]), [["earlier", earlier, false], ["later", later, false], ["later", later, false]]);
  assert.equal(requests.filter(item => item.url === "/api/baseline_get").length, 1);
});

function scopedService(ui, extra = {}) {
  const pinned = {snapshot_id: "pinned", label: "Pinned", published_at: "2025-01-10T00:00:00Z", capabilities: ["lexical", "assertions"], coverage: {active_documents: 1}};
  const saved = {investigation_id: "saved-investigation", corpus_id: "original", snapshot_id: "pinned", title: "Saved title", question: "Broad research question", notes: "Saved notes", status: "active", version: 2, run_ids: ["saved-run"], baseline_ids: [], view: {selected_entity_ids: []}};
  ui.context.fetch = async (url, options = {}) => {
    const operation = url.replace("/api/", "");
    const data = options.body ? JSON.parse(options.body) : {};
    const handlers = {
      bootstrap: () => ({csrf_token: "test-token", limits: {request_bytes: 1048576}, corpora: [{corpus_id: "original", status: "ready"}, {corpus_id: "incoming", status: "ready"}]}),
      snapshots: () => [pinned, {...pinned, snapshot_id: "new-published", label: "New publication", published_at: "2025-02-10T00:00:00Z"}],
      status: () => ({vector_indexes: [{index_id: "saved-vectors", dimensions: 2, profile: {provider: "llama.cpp", model: "fixture-model"}}]}),
      baselines: () => [], investigations: () => [saved], investigation_get: () => saved,
      ...extra
    };
    assert.ok(handlers[operation], `Unexpected operation ${operation}`);
    return response({ok: true, data: handlers[operation](data)});
  };
  return {pinned, saved};
}

for (const operation of ["ingest", "publish"]) test(`${operation} refresh retains the pinned corpus, snapshot, and unsaved investigation`, async () => {
  const ui = await app(); let writes = 0;
  const {pinned, saved} = scopedService(ui, {
    ingest: data => { writes += 1; assert.equal(data.corpus_id, "incoming"); return {job_id: "new-job", accepted: 1, rejected: 0}; },
    publish: data => { writes += 1; assert.equal(data.job_id, "new-job"); return {corpus_id: "incoming", snapshot_id: "new-published"}; }
  });
  ui.state.activeCorpus = "original"; ui.state.activeSnapshot = "pinned";
  ui.state.snapshots = [pinned]; ui.state.investigation = saved; ui.state.dirty = true;
  ui.state.run = {run_id: "kept-run", operation: "search", scope: {corpus_id: "original", snapshot_id: "pinned"}};
  ui.node("corpus").value = "original"; ui.node("snapshot").value = "pinned";
  ui.node("notes").value = "Unsaved notes must survive publication";
  ui.node("investigation-title").value = "Unsaved title";
  ui.node("import-corpus").value = "incoming"; ui.node("import-key").value = "fixture-key";
  ui.node("records-jsonl").value = '{"fixture":true}'; ui.node("job-id").value = "new-job";
  if (operation === "ingest") ui.node("ingest-form").dispatchEvent({type: "submit", submitter: ui.node("ingest-form").querySelector('button[type="submit"]')});
  else ui.node("publish").click();
  await settle();
  assert.equal(writes, 1); assert.equal(ui.state.busy, false);
  assert.equal(ui.node("corpus").value, "original"); assert.equal(ui.node("snapshot").value, "pinned");
  assert.equal(ui.state.run.run_id, "kept-run"); assert.equal(ui.state.investigation.investigation_id, "saved-investigation");
  assert.equal(ui.state.dirty, true); assert.equal(ui.node("notes").value, "Unsaved notes must survive publication");
  assert.equal(ui.node("investigation-title").value, "Unsaved title"); assert.equal(ui.node("import-corpus").value, "incoming");
  assert.equal(ui.node("message").classList.contains("error"), false);
});

test("reopening and saving retains query scope, vector choice, and selected findings", async () => {
  const ui = await app();
  const scope = {corpus_id: "original", snapshot_id: "pinned", mode: "graphrag", knowledge_cutoff: "2025-01-10T00:00:00Z", valid_time: "2025-01-05T00:00:00Z", vector_index_id: "saved-vectors"};
  const items = ["first", "second"].map(id => ({id, chunk_id: id, kind: "chunk", text: `Passage ${id}`, evidence: {document_id: "source", version_id: "v1"}}));
  let writePayload;
  const {saved} = scopedService(ui, {
    run_get: () => ({run_id: "saved-run", operation: "search", query: "Pump P specific query", scope, items, total_returned: 2, next_cursor: null}),
    investigation_save: payload => { writePayload = payload; return {...payload.data, version: 3, investigation_id: "saved-investigation"}; }
  });
  saved.view.selected_finding_ids = ["second", "no-longer-in-this-run"];
  ui.node("investigation").value = "saved-investigation";
  ui.execute("updateControls()"); ui.node("load-investigation").click(); await settle();
  assert.equal(ui.state.busy, false); assert.equal(ui.state.run.run_id, "saved-run");
  assert.equal(ui.node("query").value, "Pump P specific query"); assert.equal(ui.node("mode").value, "graphrag");
  assert.equal(ui.node("knowledge").value, scope.knowledge_cutoff); assert.equal(ui.node("valid-time").value, scope.valid_time);
  assert.equal(ui.node("vector-index").value, "saved-vectors"); assert.equal(ui.node("advanced-search").open, true);
  assert.equal(ui.node("message").classList.contains("error"), false);
  assert.deepEqual([...ui.state.selected], ["second"]);
  assert.deepEqual(ui.node("results").querySelectorAll('input[type="checkbox"]').map(input => input.checked), [false, true]);
  ui.node("investigation-form").dispatchEvent({type: "submit", submitter: ui.node("investigation-form").querySelector('button[type="submit"]')});
  await settle();
  assert.equal(writePayload.expected_version, 2);
  assert.deepEqual(writePayload.data.view.selected_finding_ids, ["second"]);
  assert.equal(ui.state.investigation.version, 3);
});

function previewItem(id) {
  return {id, assertion_id: id, kind: "assertion", subject_id: `${id}-subject`, subject_label: id, object_id: `${id}-pump`, object_label: "Pump P", text: `Exact evidence for ${id}`, modality: "reported", method: "authored-fixture", temporal_status: {from: "unknown", to: "unknown"}, evidence: {document_id: `source-${id}`, version_id: "v1", processing_version: "plain-text-v1", start: 0, end: 24, source_status: "active"}};
}

function previewResponse(id, body = {}) {
  return response({ok: true, data: {operation: "preview", items: [previewItem(id)], scope: {corpus_id: body.corpus_id || "original", snapshot_id: body.snapshot_id || "pinned", knowledge_cutoff: body.knowledge_cutoff || "2025-01-10T00:00:00Z"}, truncated: false}});
}

async function previewApp(options = {}) {
  const timers = new Timers(), ui = await app({timers, ...options});
  // The application starts on its guide; typing previews belong to Explore.
  ui.execute('showPanel("search-panel")');
  ui.timers = timers; ui.preview = ui.execute("preview");
  ui.state.activeCorpus = "original"; ui.state.activeSnapshot = "pinned";
  ui.state.snapshots = [{snapshot_id: "pinned", label: "Pinned", published_at: "2025-01-10T00:00:00Z", capabilities: ["lexical", "assertions"], coverage: {active_documents: 1}}];
  ui.node("corpus").value = "original"; ui.node("snapshot").value = "pinned";
  ui.execute("snapshotStatus()"); ui.node("mode").value = "graphrag";
  ui.context.committed = {operation: "search", run_id: "committed-run", query: "Original search", scope: {corpus_id: "original", snapshot_id: "pinned", mode: "graphrag", knowledge_cutoff: "2025-01-10T00:00:00Z"}, items: [previewItem("committed")], total_returned: 1, next_cursor: "committed-page"};
  ui.execute("renderRun(committed); evidenceView(committed.items[0]); state.seeds.add('committed-subject'); graph(state.items)");
  ui.node("query").focus();
  ui.type = value => { ui.node("query").value = value; ui.node("query").dispatchEvent({type: "input"}); };
  return ui;
}

test("live preview debounces typing without locking input or mutating saved analysis", async () => {
  const ui = await previewApp(), pending = deferred(), requests = [];
  const committedRun = ui.state.run, committedItems = ui.state.items, committedEntities = ui.state.entities;
  ui.context.fetch = async (url, options) => { requests.push({url, options, body: JSON.parse(options.body)}); return pending.promise; };
  ui.type("Pu"); await ui.timers.advance(299); assert.equal(requests.length, 0);
  ui.type("Pump"); await ui.timers.advance(300); assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/api/preview"); assert.equal(requests[0].body.query, "Pump");
  assert.equal(ui.state.busy, false); assert.equal(ui.node("query").disabled, false);
  pending.resolve(previewResponse("live")); await settle();
  assert.deepEqual([...ui.preview.items].map(item => item.id), ["live"]);
  assert.equal(ui.state.run, committedRun); assert.equal(ui.state.searchRun, committedRun);
  assert.equal(ui.state.items, committedItems); assert.equal(ui.state.entities, committedEntities);
  assert.deepEqual([...ui.state.selected], ["committed"]); assert.deepEqual([...ui.state.seeds], ["committed-subject"]);
  for (const id of ["download", "save-baseline", "more"]) assert.equal(ui.node(id).disabled, true, id);
  ui.node("graph").querySelector(".graph-node").click();
  assert.deepEqual([...ui.state.seeds], ["committed-subject"]);
  assert.equal(requests.length, 1, "Tracing live support must not fetch or save another run");
  assert.equal(ui.document.activeElement, ui.node("query"), "Tracing must preserve typing focus");
  ui.execute("stopPreview()");
});

test("out-of-order preview replies cannot replace the latest query", async () => {
  const ui = await previewApp(), requests = [];
  ui.context.fetch = (url, options) => { const job = deferred(); requests.push({url, options, job}); return job.promise; };
  ui.type("Pump"); await ui.timers.advance(300);
  ui.type("Pump "); assert.equal(requests[0].options.signal.aborted, true); await ui.timers.advance(300);
  assert.equal(JSON.parse(requests[0].options.body).query, "Pump");
  assert.equal(JSON.parse(requests[1].options.body).query, "Pump ", "Trailing whitespace ends prefix matching and must reach the service");
  requests[1].job.resolve(previewResponse("latest")); await settle();
  requests[0].job.resolve(previewResponse("stale")); await settle();
  assert.equal(ui.preview.items[0].id, "latest"); assert.match(ui.node("evidence-text").textContent, /latest/);
  assert.doesNotMatch(ui.node("results").textContent, /stale/);
  ui.execute("stopPreview()");
});

test("clearing live text restores the exact committed result, graph, evidence, and selection", async () => {
  const ui = await previewApp();
  const resultNode = ui.node("results").childNodes[0], graphNode = ui.node("graph").childNodes[0];
  const oldEvidence = ui.node("evidence-text").textContent, oldDetails = ui.node("run-details").textContent;
  const oldLabel = ui.node("graph").getAttribute("aria-label");
  ui.execute("zoomGraph(1.25)"); const oldViewBox = ui.node("graph").getAttribute("viewBox");
  ui.context.fetch = async () => previewResponse("temporary");
  ui.type("Pump"); await ui.timers.advance(300);
  assert.match(ui.node("evidence-text").textContent, /temporary/);
  ui.type("");
  assert.equal(ui.preview.view, null); assert.equal(ui.preview.items.length, 0);
  assert.equal(ui.node("results").childNodes[0], resultNode); assert.equal(ui.node("graph").childNodes[0], graphNode);
  assert.equal(ui.node("graph").getAttribute("aria-label"), oldLabel); assert.equal(ui.node("graph").getAttribute("viewBox"), oldViewBox);
  assert.equal(ui.node("evidence-text").textContent, oldEvidence); assert.equal(ui.node("run-details").textContent, oldDetails);
  assert.deepEqual([...ui.state.selected], ["committed"]); assert.deepEqual([...ui.state.seeds], ["committed-subject"]);
  assert.equal(ui.node("download").disabled, false); assert.equal(ui.node("more").hidden, false);
});

test("IME, query bounds, pause, and Escape suppress unwanted preview dispatch", async () => {
  const ui = await previewApp(); let calls = 0;
  ui.context.fetch = async () => { calls += 1; return previewResponse("live"); };
  for (const query of ["P", "x".repeat(257), Array.from({length: 17}, (_, index) => `term${index}`).join(" ")]) { ui.type(query); await ui.timers.advance(300); }
  assert.equal(calls, 0);
  ui.node("query").dispatchEvent({type: "compositionstart"});
  ui.node("query").value = "Pump"; ui.node("query").dispatchEvent({type: "input", isComposing: true});
  await ui.timers.advance(600); assert.equal(calls, 0);
  ui.node("query").dispatchEvent({type: "compositionend"}); await ui.timers.advance(300); assert.equal(calls, 1);
  ui.node("query").dispatchEvent({type: "keydown", key: "Escape"}); assert.equal(ui.preview.view, null);
  ui.node("live-toggle").click(); assert.equal(ui.preview.enabled, false);
  ui.type("Pump changed"); await ui.timers.advance(400); assert.equal(calls, 1);
  ui.node("live-toggle").click(); await ui.timers.advance(300); assert.equal(calls, 2);
  ui.execute("stopPreview()");
});

for (const transition of ["tab", "snapshot", "action", "corpus"]) test(`${transition} transition cancels pending preview and rejects its late response`, async () => {
  const ui = await previewApp(), pending = deferred(); let signal;
  ui.context.fetch = async (url, options) => {
    if (url === "/api/preview") { signal = options.signal; return pending.promise; }
    return response({ok: true, data: url === "/api/status" ? {vector_indexes: []} : []});
  };
  ui.type("Pump"); await ui.timers.advance(300);
  if (transition === "tab") ui.execute('showPanel("compare-panel")');
  if (transition === "snapshot") { ui.node("snapshot").value = "another-snapshot"; ui.node("snapshot").dispatchEvent({type: "change"}); }
  if (transition === "action") await ui.execute("action(null, async () => {})");
  if (transition === "corpus") { ui.node("corpus").value = "another-corpus"; ui.node("corpus").dispatchEvent({type: "change"}); await settle(); }
  assert.equal(signal.aborted, true);
  pending.resolve(previewResponse("obsolete")); await settle();
  assert.equal(ui.preview.view, null); assert.equal(ui.preview.items.length, 0);
  assert.doesNotMatch(ui.node("evidence-text").textContent, /obsolete/);
  assert.equal(ui.state.run?.run_id || null, ["snapshot", "corpus"].includes(transition) ? null : "committed-run");
});

test("dense and hybrid typing use lexical preview without model or vector requests", async () => {
  const ui = await previewApp(), requests = [];
  ui.node("vector-index").append(new ui.context.Option("Local model", "model-vectors"));
  ui.node("vector-index").value = "model-vectors";
  ui.context.fetch = async (url, options) => { requests.push({url, body: JSON.parse(options.body)}); return previewResponse("keyword"); };
  for (const mode of ["dense", "hybrid"]) {
    ui.node("mode").value = mode; ui.type("Pump"); await ui.timers.advance(300);
    assert.equal(ui.node("mode").value, mode, "Preview must not rewrite the committed search method");
    ui.execute("stopPreview()");
  }
  assert.equal(requests.length, 2);
  for (const item of requests) { assert.equal(item.url, "/api/preview"); assert.equal(item.body.mode, "lexical"); assert.equal(item.body.valid_time, null); assert.equal("vector_index_id" in item.body, false); }
});

test("editing temporal scope aborts the old preview and sends the new explicit filters", async () => {
  const ui = await previewApp(), requests = [];
  ui.context.fetch = (url, options) => { const job = deferred(); requests.push({body: JSON.parse(options.body), signal: options.signal, job}); return job.promise; };
  ui.type("Pump"); await ui.timers.advance(300);
  ui.node("knowledge").value = "2025-01-07T00:00:00Z"; ui.node("knowledge").dispatchEvent({type: "input"});
  ui.node("valid-time").value = "2025-01-01T00:00:00Z"; ui.node("valid-time").dispatchEvent({type: "input"});
  assert.equal(requests[0].signal.aborted, true); await ui.timers.advance(300);
  assert.equal(requests[1].body.knowledge_cutoff, "2025-01-07T00:00:00Z"); assert.equal(requests[1].body.valid_time, "2025-01-01T00:00:00Z");
  requests[0].job.resolve(previewResponse("wrong-time")); await settle(); assert.equal(ui.preview.view, null);
  requests[1].job.resolve(previewResponse("right-time", requests[1].body)); await settle();
  assert.equal(ui.preview.items[0].id, "right-time"); ui.execute("stopPreview()");
});

test("reduced-motion preview delivers the same evidence without waiting for animation events", async () => {
  const snapshots = [];
  for (const reducedMotion of [false, true]) {
    const ui = await previewApp({reducedMotion}); ui.context.fetch = async () => previewResponse("motion-independent");
    ui.type("Pump"); await ui.timers.advance(300);
    snapshots.push({ids: [...ui.preview.items].map(item => item.id), evidence: ui.node("evidence-text").textContent, selected: [...ui.state.selected], seeds: [...ui.state.seeds]});
    assert.equal(ui.node("live-feedback").dataset.phase, "ready");
    ui.execute("stopPreview()");
  }
  assert.deepEqual(snapshots[0], snapshots[1]);
});

test("preview timeout restores committed evidence and leaves typing available", async () => {
  const ui = await previewApp();
  ui.context.fetch = async () => previewResponse("first-preview"); ui.type("Pump"); await ui.timers.advance(300);
  ui.context.fetch = (_, options) => new Promise((resolve, reject) => options.signal.addEventListener("abort", () => { const error = new Error("Timed out"); error.name = "AbortError"; reject(error); }, {once: true}));
  ui.type("Pump timeout"); await ui.timers.advance(300); await ui.timers.advance(5000);
  assert.equal(ui.preview.view, null); assert.equal(ui.state.run.run_id, "committed-run");
  assert.equal(ui.node("evidence-text").textContent, previewItem("committed").text);
  assert.equal(ui.node("query").disabled, false); assert.equal(ui.state.busy, false);
  assert.equal(ui.node("live-feedback").dataset.phase, "error");
});
