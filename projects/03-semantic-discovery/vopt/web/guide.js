'use strict';
// Shared by the browser and dependency-free query contract tests.
(function (root) {
  const units = {V:['V','kV'], Hz:['Hz','kHz'], A:['A','mA'], W:['W','kW'], hp:['hp'], rpm:['rpm'], kg:['kg','g','lb','oz'], mm:['mm','cm','m','in'], cm3:['cm3','L'], L:['L','ml'], kPa:['kPa','Pa','MPa','bar','psi']};
  const comparisons = {present:'Is covered', eq:'Equals', ge:'At least', le:'At most', gt:'Above', lt:'Below', between:'Between'};
  const symbols = {eq:'=', ge:'>=', le:'<=', gt:'>', lt:'<'};
  const label = value => value.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
  const unique = values => [...new Set(values.filter(Boolean))].sort((a,b) => a.localeCompare(b));
  const scopes = (options, state) => options.scopes.filter(s => (!state.category || s.category === state.category) && (!state.model || s.model === state.model));
  function quote(value) {
    if (!value || /["\r\n\x00-\x1f]/.test(value)) throw new Error('This catalog label cannot be searched. Choose another label or use text search.');
    return `"${value}"`;
  }
  function decimal(value) {
    const text = String(value).trim();
    if (!/^(?:\d+(?:\.\d+)?|\.\d+)$/.test(text) || !Number.isFinite(Number(text)) || Number(text) > 1e15)
      throw new Error('Enter a number from 0 to 1,000,000,000,000,000. Use a decimal point, without commas.');
    return text;
  }
  function buildQuery(state, options) {
    const parts = [];
    for (const key of ['category','model','variant']) if (state[key]) parts.push(`${key} ${quote(state[key])}`);
    if (state.requirements.length > 8) throw new Error('Use up to eight specifications per search.');
    for (const row of state.requirements) {
      const attribute = options.attributes.find(a => a.key === row.attribute);
      if (!attribute) throw new Error('Choose a specification.');
      if (!Object.hasOwn(comparisons, row.comparison)) throw new Error('Choose a comparison.');
      if (state.qualifier && !['rated','peak','no_load','unspecified'].includes(state.qualifier)) throw new Error('Choose a rating.');
      const name = `${state.qualifier ? state.qualifier+' ' : ''}${attribute.key}`;
      if (row.comparison === 'present') { parts.push(name); continue; }
      if (!options.numeric_filters) throw new Error('This catalog lists specifications without values.');
      if (!(units[attribute.unit] || [attribute.unit]).includes(row.unit)) throw new Error('Choose a compatible unit.');
      const first = decimal(row.value);
      if (row.comparison === 'between') {
        const second = decimal(row.maximum);
        if (Number(first) > Number(second)) throw new Error('The minimum must be no greater than the maximum.');
        parts.push(`${name} between ${first} and ${second} ${row.unit}`);
      } else parts.push(`${name} ${symbols[row.comparison]} ${first} ${row.unit}`);
    }
    for (const condition of state.conditions || []) parts.push(`condition ${quote(condition)}`);
    if (!parts.length) throw new Error('Choose equipment or a specification.');
    const query = parts.join(' and ');
    if (query.length > 2000) throw new Error('Shorten this search.');
    return query;
  }
  const key = item => JSON.stringify([item.doc_id, item.model, item.variant || null]);
  const request = (item, query) => ({doc_id:item.doc_id, model:item.model, variant:item.variant, revision:item.revision, request_ref:item.request_ref, query, matched_assertions:[...(item.matched_assertions || [])]});
  const api = {units, comparisons, label, unique, scopes, quote, decimal, buildQuery, key, request};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.VoptGuide = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
