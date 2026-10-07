'use strict';
// Controller regressions against app.js. This small DOM double does not test
// layout, browser accessibility behavior, or replace actual browser checks.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const guide = require('../vopt/web/guide.js');
const root = path.resolve(__dirname, '../vopt/web');
const tick = () => new Promise(resolve => setImmediate(resolve));

class Element {
  constructor(tag, document) {
    this.tagName = tag.toUpperCase(); this.document = document;
    this.children = []; this.dataset = {}; this.attributes = new Map();
    this.hidden = false; this.disabled = false; this.value = ''; this.open = false;
    this.checked = false; this._text = '';
  }
  set id(value) { this._id = value; this.document.elements.set(value, this); }
  get id() { return this._id; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this._text = ''; this.children = children; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  removeAttribute(name) { this.attributes.delete(name); }
  focus() { this.document.activeElement = this; }
  scrollIntoView() {}
  click() { if (!this.disabled) return this.onclick?.({target:this, preventDefault(){}}); }
}

const fixtureOptions = {
  catalog_id:'fixture', sequence:1, integrity:'a'.repeat(64), profile:'values', numeric_filters:true,
  attributes:[{key:'output_power', label:'output power', unit:'W'}],
  scopes:[{doc_id:'d1', title:'Generator manual', category:'generator', model:'G1', manufacturer:'Fixture',
    attributes:[{key:'output_power', label:'output power', unit:'W', qualifiers:['rated'], variants:['US'], conditions:['full load']}]}],
};

async function browser(optionsOverride={}) {
  const options = {...structuredClone(fixtureOptions), ...structuredClone(optionsOverride)};
  const document = {elements:new Map(), activeElement:null};
  document.createElement = tag => new Element(tag, document);
  document.getElementById = id => document.elements.get(id) ?? null;
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  for (const match of html.matchAll(/<([a-z][\w-]*)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const element = document.createElement(match[1]); element.id = match[3];
    element.hidden = /\bhidden\b/.test(match[2]); element.disabled = /\bdisabled\b/.test(match[2]);
  }
  const pending = [], downloads = [];
  const response = (payload, ok=true) => ({ok, json:async () => payload});
  const context = vm.createContext({
    document, VoptGuide:guide, AbortController, Blob,
    URL:{createObjectURL(blob){ downloads.push(blob); return 'blob:fixture'; }, revokeObjectURL(){}},
    setTimeout(){},
    fetch(url, init={}) {
      if (url === '/api/info') return Promise.resolve(response({mode:'discovery', catalog:{catalog_id:'fixture'}}));
      if (url === '/api/options') return Promise.resolve(response(options));
      assert.match(url, /^\/api\/search\?/);
      // Deliberately ignore cancellation: a response already in flight may
      // settle after abort, so the controller must also reject stale versions.
      return new Promise((resolve, reject) => pending.push({url, signal:init.signal, reject,
        resolve:(payload, ok=true) => resolve(response(payload, ok))}));
    },
  });
  vm.runInContext(fs.readFileSync(path.join(root, 'app.js'), 'utf8'), context);
  await tick();
  const get = id => { const value=document.getElementById(id); assert.ok(value, `Missing element ${id}`); return value; };
  const change = (id, value) => { get(id).value=value; get(id).onchange(); };
  const input = (id, value) => { get(id).value=value; get(id).oninput(); };
  const submit = id => get(id).onsubmit({preventDefault(){}});
  return {get, change, input, submit, document, pending, downloads};
}

const result = (total=1, title='Generator manual') => ({status:'ready', total_matches:total,
  results:[{doc_id:'d1', title, model:'G1', variant:'US', revision:'1', request_ref:'fixture:d1', matched_assertions:['a1'], explanation:'Matches selected requirements.'}],
  diagnostics:{details:[], unknown_scopes:0, conflicting_scopes:0}, plan:{}, scoring:'fixture'});
function textSearch(ui, query) { ui.get('query').value=query; ui.submit('search-form'); }

test('late responses from an aborted search cannot replace a newer result', async () => {
  const ui = await browser();
  textSearch(ui, 'generator');
  ui.get('edit-search').click();
  textSearch(ui, 'output power above 20 kW');
  assert.equal(ui.pending[0].signal.aborted, true);
  ui.pending[1].resolve(result(2, 'Current result')); await tick();
  assert.equal(ui.get('result-heading').textContent, '2 matches');
  ui.pending[0].resolve(result(1, 'Stale result')); await tick();
  assert.equal(ui.get('result-heading').textContent, '2 matches');
  assert.match(ui.get('results').textContent, /Current result/);
  assert.doesNotMatch(ui.get('results').textContent, /Stale result/);
  assert.equal(ui.get('results-step').getAttribute('aria-busy'), null);
});

test('failed text search Edit restores the text flow and retains its query', async () => {
  const ui = await browser();
  textSearch(ui, 'generator output voltage');
  ui.pending[0].resolve({error:'Fixture transport error'}, false); await tick();
  assert.equal(ui.get('result-heading').textContent, 'Search unavailable');
  ui.get('edit-search').click();
  assert.equal(ui.get('equipment-step').hidden, false);
  assert.equal(ui.get('specification-step').hidden, true);
  assert.equal(ui.get('text-search').open, true);
  assert.equal(ui.get('query').value, 'generator output voltage');
  assert.equal(ui.document.activeElement, ui.get('query'));
});

test('leaving an unfinished search clears busy state and disables an empty Results step', async () => {
  const ui = await browser();
  ui.change('model', 'G1'); ui.get('continue').click(); ui.submit('guided-form');
  assert.equal(ui.get('results-step').getAttribute('aria-busy'), 'true');
  ui.get('step-1').click();
  assert.equal(ui.pending[0].signal.aborted, true);
  assert.equal(ui.get('results-step').getAttribute('aria-busy'), null);
  assert.equal(ui.get('step-3').disabled, true);
  ui.pending[0].resolve(result()); await tick();
  assert.equal(ui.get('equipment-step').hidden, false);
  assert.equal(ui.get('step-3').disabled, true);
  ui.get('step-3').click();
  assert.equal(ui.get('equipment-step').hidden, false);
});

test('guided back and continue retain quantity, rating, variant and operating conditions', async () => {
  const ui = await browser();
  ui.change('model', 'G1'); ui.get('continue').click(); ui.get('add-requirement').click();
  ui.change('attribute-0', 'output_power'); ui.change('comparison-0', 'ge'); ui.input('value-0', '25000');
  ui.change('filter-qualifier', 'rated'); ui.change('filter-variant', 'US');
  ui.get('condition-0').checked=true; ui.get('condition-0').onchange();
  ui.get('back-equipment').click(); ui.get('continue').click();
  assert.equal(ui.get('attribute-0').value, 'output_power');
  assert.equal(ui.get('comparison-0').value, 'ge');
  assert.equal(ui.get('value-0').value, '25000');
  assert.equal(ui.get('filter-qualifier').value, 'rated');
  assert.equal(ui.get('filter-variant').value, 'US');
  assert.equal(ui.get('condition-0').checked, true);
  ui.submit('guided-form');
  const query = new URL(ui.pending[0].url, 'http://fixture').searchParams.get('q');
  assert.equal(query, 'model "G1" and variant "US" and rated output_power >= 25000 W and condition "full load"');
});

test('saved requests retain their originating query after a later search and export', async () => {
  const ui = await browser();
  const original='generator output power above 20 kW';
  textSearch(ui, original); ui.pending[0].resolve(result()); await tick();
  const save=ui.get('results').children[0].children[0].children[1]; save.click();
  assert.equal(ui.get('saved-count').textContent, '1');
  ui.get('new-search').click();
  textSearch(ui, 'generator output power'); ui.pending[1].resolve(result()); await tick();
  ui.get('download').click();
  assert.equal(ui.downloads.length, 1);
  const exported=JSON.parse(await ui.downloads[0].text());
  assert.equal(exported.requests.length, 1);
  assert.equal(exported.requests[0].query, original);
  assert.deepEqual(exported.requests[0].matched_assertions, ['a1']);
  assert.equal(ui.get('results').children[0].children[0].children[1].textContent, 'Saved');
});

test('coverage catalogs offer presence without numeric comparisons or operating-condition hints', async () => {
  const ui = await browser({profile:'coverage', numeric_filters:false});
  ui.get('continue').click(); ui.get('add-requirement').click(); ui.change('attribute-0', 'output_power');
  assert.equal(ui.get('coverage-note').hidden, false);
  assert.deepEqual(ui.get('comparison-0').children.map(option => option.value), ['present']);
  assert.equal(ui.get('comparison-0').value, 'present');
  assert.equal(ui.get('comparison-0').disabled, false);
  assert.equal(ui.document.getElementById('value-0'), null);
  assert.equal(ui.document.getElementById('condition-0'), null);
  assert.doesNotMatch(ui.get('scope-fields').textContent, /Operating conditions|full load/);
  assert.equal(ui.get('find-manuals').disabled, false);
  ui.submit('guided-form');
  assert.equal(new URL(ui.pending[0].url, 'http://fixture').searchParams.get('q'), 'output_power');
});

test('empty catalogs keep Find disabled even after choosing a supported specification', async () => {
  const ui = await browser({scopes:[]});
  assert.equal(ui.get('catalog-summary').textContent, 'No manuals in this catalog');
  ui.get('continue').click();
  assert.equal(ui.get('find-manuals').disabled, true);
  ui.get('add-requirement').click(); ui.change('attribute-0', 'output_power');
  assert.equal(ui.get('attribute-0').value, 'output_power');
  assert.equal(ui.get('find-manuals').disabled, true);
  assert.equal(ui.get('search-hint').textContent, 'This catalog is empty.');
  assert.equal(ui.pending.length, 0);
});

test('confirmed matches retain separate missing and conflicting record details', async () => {
  const ui = await browser();
  textSearch(ui, 'generator output power above 20 kW');
  const found = result();
  found.results[0].warnings=['Document processing is partial; unobserved attributes remain unknown.'];
  found.diagnostics={unknown_scopes:3, conflicting_scopes:1, details:[
    {doc_id:'d2', model:'G2', title:'Missing power manual', status:'unknown', reasons:['Output power has not been observed.'],
      available_conditions:['full load'], available_qualifiers:['rated']},
    {doc_id:'d3', model:'G3', title:'Conflicting power manual', status:'conflict', reasons:['Two reviewed values disagree.']},
  ]};
  ui.pending[0].resolve(found); await tick();
  assert.equal(ui.get('result-heading').textContent, '1 match');
  assert.equal(ui.get('results').children.length, 1);
  assert.match(ui.get('results').textContent, /Partially processed\. Other specifications may be missing\./);
  assert.equal(ui.get('gaps').hidden, false);
  assert.match(ui.get('gap-items').textContent, /Missing details/);
  assert.match(ui.get('gap-items').textContent, /Output power has not been observed\./);
  assert.match(ui.get('gap-items').textContent, /Conflicting values/);
  assert.match(ui.get('gap-items').textContent, /Two reviewed values disagree\./);
  assert.match(ui.get('gap-items').textContent, /Recorded conditions: full load/);
  assert.match(ui.get('gap-items').textContent, /Recorded ratings: Rated/);
  assert.match(ui.get('gap-items').textContent, /Showing 2 of 4 records/);
  assert.equal(ui.get('plan-wrap').hidden, false);
});
