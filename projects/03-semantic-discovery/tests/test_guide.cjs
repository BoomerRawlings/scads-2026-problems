'use strict';
// Authored behavior checks for the guided interface; no browser or package dependencies.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const {spawnSync} = require('node:child_process');
const guide = require('../vopt/web/guide.js');

const options = {
  numeric_filters: true,
  attributes: [
    {key:'input_voltage', unit:'V'}, {key:'output_voltage', unit:'V'},
    {key:'input_power', unit:'W'}, {key:'output_power', unit:'W'},
    {key:'horsepower', unit:'hp'}, {key:'speed', unit:'rpm'},
    {key:'weight', unit:'kg'}, {key:'blade_diameter', unit:'mm'},
    {key:'capacity', unit:'L'}, {key:'displacement', unit:'cm3'},
    {key:'pressure', unit:'kPa'}, {key:'frequency', unit:'Hz'},
    {key:'input_current', unit:'A'},
  ],
  scopes: [
    {doc_id:'manual-1', model:'GEN-1', category:'generator'},
    {doc_id:'manual-2', model:'GEN-1', category:'engine'},
    {doc_id:'manual-2', model:'CMP-1', category:'compressor'},
  ],
};
const state = changes => ({category:'', model:'', variant:'', qualifier:'', requirements:[], conditions:[], ...changes});
const row = changes => ({attribute:'weight', comparison:'present', unit:'kg', value:'', maximum:'', ...changes});

test('accepts bounded nonnegative decimal input, including zero and fractional values', () => {
  for (const value of ['0', '0.00', '.125', '12.5', '1000000000000000']) assert.equal(guide.decimal(value), value);
  assert.equal(guide.decimal(' 12.5 '), '12.5');
});

test('rejects empty, negative, exponential, nonfinite and comma-formatted input', () => {
  for (const value of ['', ' ', '-1', '+1', '1e3', '1E-3', '1,000', '1.', 'NaN', 'Infinity', '1000000000000001', null, undefined])
    assert.throws(() => guide.decimal(value), /Enter a number/);
});

test('quotes exact category, model and variant without changing Boolean words or punctuation', () => {
  assert.equal(guide.buildQuery(state({category:'battery charger', model:'AX and BX (Series 2)', variant:'US or export'}), options),
    'category "battery charger" and model "AX and BX (Series 2)" and variant "US or export"');
  assert.equal(guide.quote("Acme's engine"), '"Acme\'s engine"');
});

test('rejects unrepresentable selector text instead of replacing its characters', () => {
  for (const value of ['', 'AX"1', 'AX\n1', 'AX\r1', 'AX\t1', 'AX\x001']) assert.throws(() => guide.quote(value));
  assert.throws(() => guide.buildQuery(state({model:'AX"1'}), options));
});

test('joins specifications, rating and explicit operating conditions conjunctively', () => {
  const query = guide.buildQuery(state({category:'generator', model:'VG-959 QMC', qualifier:'rated',
    requirements:[row({attribute:'output_voltage', comparison:'ge', value:'125', unit:'V'}),
      row({comparison:'between', value:'2.5', maximum:'5', unit:'kg'})],
    conditions:['warm and dry', 'three-phase AC']}), options);
  assert.equal(query, 'category "generator" and model "VG-959 QMC" and rated output_voltage >= 125 V and rated weight between 2.5 and 5 kg and condition "warm and dry" and condition "three-phase AC"');
});

test('presence requires no quantity and remains available when observations are missing', () => {
  const query = guide.buildQuery(state({model:'GEN-1', requirements:[row({attribute:'displacement'})]}), options);
  assert.equal(query, 'model "GEN-1" and displacement');
  assert.equal(guide.buildQuery(state({requirements:[row()]}), {...options, numeric_filters:false}), 'weight');
});

test('coverage profile rejects numeric filtering even when supplied outside the interface', () => {
  assert.throws(() => guide.buildQuery(state({requirements:[row({comparison:'ge', value:'0'})]}), {...options, numeric_filters:false}), /without values/);
});

test('numeric comparisons retain zero and use the selected compatible unit', () => {
  for (const [comparison, symbol] of Object.entries({eq:'=', ge:'>=', le:'<=', gt:'>', lt:'<'})) {
    assert.equal(guide.buildQuery(state({requirements:[row({comparison, value:'0', unit:'lb'})]}), options), `weight ${symbol} 0 lb`);
  }
  assert.throws(() => guide.buildQuery(state({requirements:[row({comparison:'ge', value:'5', unit:'V'})]}), options), /compatible unit/);
});

test('rejects reverse or incomplete ranges and accepts equal bounds', () => {
  assert.throws(() => guide.buildQuery(state({requirements:[row({comparison:'between', value:'5', maximum:'2'})]}), options), /minimum/);
  assert.throws(() => guide.buildQuery(state({requirements:[row({comparison:'between', value:'5', maximum:''})]}), options), /Enter a number/);
  assert.equal(guide.buildQuery(state({requirements:[row({comparison:'between', value:'5', maximum:'5'})]}), options), 'weight between 5 and 5 kg');
});

test('requires a supported specification, comparison, rating and search criterion', () => {
  assert.throws(() => guide.buildQuery(state(), options), /Choose equipment or a specification/);
  assert.throws(() => guide.buildQuery(state({requirements:[row({attribute:'unknown'})]}), options), /Choose a specification/);
  for (const comparison of ['near', 'constructor', 'toString', '__proto__'])
    assert.throws(() => guide.buildQuery(state({requirements:[row({comparison, value:'5'})]}), options), /Choose a comparison/);
  assert.throws(() => guide.buildQuery(state({qualifier:'nominal', requirements:[row()]}), options), /Choose a rating/);
});

test('bounds specification count and final query length', () => {
  assert.throws(() => guide.buildQuery(state({requirements:Array.from({length:9}, () => row())}), options), /eight/);
  assert.throws(() => guide.buildQuery(state({model:'X'.repeat(2000)}), options), /Shorten/);
});

test('equipment narrowing uses each scope category and exact model identity', () => {
  assert.equal(guide.scopes(options, state()).length, 3);
  assert.deepEqual(guide.scopes(options, state({category:'generator', model:'GEN-1'})), [options.scopes[0]]);
  assert.deepEqual(guide.scopes(options, state({category:'compressor', model:'GEN-1'})), []);
  assert.deepEqual(guide.scopes(options, state({model:'GEN'})), []);
});

test('request identity distinguishes scope delimiters and variants', () => {
  assert.notEqual(guide.key({doc_id:'a|b', model:'c'}), guide.key({doc_id:'a', model:'b|c'}));
  assert.notEqual(guide.key({doc_id:'d', model:'m', variant:'US'}), guide.key({doc_id:'d', model:'m', variant:'EU'}));
  assert.equal(guide.key({doc_id:'d', model:'m', variant:null}), guide.key({doc_id:'d', model:'m'}));
});

test('saved request snapshots keep the original query and assertion identifiers', () => {
  const item = {doc_id:'manual-1', model:'GEN-1', variant:'US', revision:'2', request_ref:'request:manual-1:2', matched_assertions:['a1']};
  let currentQuery = 'output_voltage >= 125 V';
  const saved = guide.request(item, currentQuery);
  currentQuery = 'weight';
  item.matched_assertions.push('a2');
  item.model = 'OTHER';
  item.request_ref = 'changed';
  assert.deepEqual(saved, {doc_id:'manual-1', model:'GEN-1', variant:'US', revision:'2', request_ref:'request:manual-1:2',
    query:'output_voltage >= 125 V', matched_assertions:['a1']});
  assert.notEqual(saved.query, currentQuery);
});

test('generated queries compile to the intended Python search predicates', () => {
  const root = path.resolve(__dirname, '..');
  const venv = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const python = process.env.VOPT_PYTHON || (fs.existsSync(venv) ? venv : 'python');
  const cases = options.attributes.flatMap(attribute => guide.units[attribute.unit].map(unit => ({
    query:guide.buildQuery(state({requirements:[row({attribute:attribute.key, comparison:'ge', value:'1.5', unit})]}), options),
    attribute:attribute.key, unit:attribute.unit,
  })));
  cases.push({query:guide.buildQuery(state({category:'generator', model:'AX and BX (Series 2)', variant:'US or export', qualifier:'no_load',
    requirements:[row({comparison:'between', value:'2', maximum:'5'})], conditions:['warm and dry']}), options),
    attribute:'weight', unit:'kg', identity:true});
  const result = spawnSync(python, ['-c', 'import json,sys; from vopt.query import parse_query; print(json.dumps([parse_query(q) for q in json.load(sys.stdin)]))'],
    {cwd:root, input:JSON.stringify(cases.map(c => c.query)), encoding:'utf8'});
  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 0, result.stderr);
  const plans = JSON.parse(result.stdout);
  plans.forEach((plan, i) => {
    const expected = cases[i];
    assert.equal(plan.status, 'ready', `${expected.query}: ${plan.message}`);
    assert.equal(plan.clauses.length, 1);
    assert.equal(plan.constraints.length, 1);
    assert.equal(plan.constraints[0].attribute, expected.attribute);
    assert.equal(plan.constraints[0].unit, expected.unit);
    assert.deepEqual(plan.terms, [], expected.query);
    if (expected.identity) {
      assert.deepEqual(plan.categories, ['generator']);
      assert.deepEqual(plan.models, ['ax and bx (series 2)']);
      assert.deepEqual(plan.clauses[0].variants, ['us or export']);
      assert.deepEqual(plan.clauses[0].conditions, ['warm and dry']);
      assert.equal(plan.constraints[0].qualifier, 'no_load');
      assert.equal(plan.constraints[0].op, 'range');
      assert.equal(plan.constraints[0].value, 2);
      assert.equal(plan.constraints[0].value_max, 5);
    }
  });
});
