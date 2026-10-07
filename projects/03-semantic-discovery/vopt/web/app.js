'use strict';
const $ = id => document.getElementById(id);
const node = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
const G = VoptGuide;
let info, options, record, selected, activeDoc = '', loadVersion = 0;
let step = 1, furthest = 1, searchVersion = 0, searchController, lastSearch = null, attemptedSource = 'guided';
const freshState = () => ({category:'', model:'', requirements:[], qualifier:'', variant:'', conditions:[]});
let state = freshState();
const basket = new Map();
const saveButtons = new Map();
function error(message) { $('error').textContent = message || ''; $('error').hidden = !message; if(message) $('error').focus(); }
async function api(path, init) { const r = await fetch(path, init); const data = await r.json(); if (!r.ok) throw new Error(data.error || 'Request failed'); return data; }
function busy(button, value) { button.disabled = value; }
function button(text, cls, action) { const b = node('button', text, cls); b.type = 'button'; b.onclick = action; return b; }
function option(value, text) { const o = node('option', text); o.value = value; return o; }
function field(text, input) { const wrapper = node('div'), label = node('label', text); label.htmlFor = input.id; wrapper.append(label, input); return wrapper; }
function clearScope() { state.qualifier = ''; state.variant = ''; state.conditions = []; }
function invalidateResults() { lastSearch = null; furthest = Math.min(furthest, 2); $('step-3').disabled = true; }
function go(next, focus = true) {
  if (next !== 3) {
    searchVersion++; searchController?.abort(); $('results-step').removeAttribute('aria-busy');
    if (!lastSearch) furthest = Math.min(furthest, 2);
  }
  step = next; furthest = Math.max(furthest, next);
  ['equipment','specification','results'].forEach((name, i) => {
    $(name+'-step').hidden = i+1 !== next;
    const b = $('step-'+(i+1)); b.disabled = i+1 > furthest;
    if(i+1 === next) b.setAttribute('aria-current','step'); else b.removeAttribute('aria-current');
  });
  if (next === 2) renderSpecifications();
  if (focus) $({1:'equipment-heading',2:'specification-heading',3:'result-heading'}[next]).focus({preventScroll:true});
}
function renderEquipment() {
  $('categories').replaceChildren();
  const categories = ['', ...G.unique(options.scopes.map(s => s.category))];
  for (const category of categories) {
    const count = new Set(options.scopes.filter(s => !category || s.category === category).map(s => s.doc_id)).size;
    const b = button('', 'category-choice', () => {
      state.category = category;
      if (!options.scopes.some(s => (!category || s.category === category) && s.model === state.model)) state.model = '';
      clearScope(); invalidateResults(); renderEquipment();
      [...$('categories').children].find(el => el.dataset.category === category)?.focus();
    });
    b.dataset.category = category; b.setAttribute('aria-pressed', String(category === state.category));
    const text = node('span', category ? G.label(category) : 'All equipment');
    text.append(node('small', count+' '+(count === 1 ? 'manual' : 'manuals')));
    const mark = node('span', '', 'choice-mark'); mark.setAttribute('aria-hidden','true'); b.append(text, mark); $('categories').append(b);
  }
  $('model').replaceChildren(option('','Any model'));
  for(const model of G.unique(options.scopes.filter(s => !state.category || s.category === state.category).map(s => s.model))) $('model').append(option(model,model));
  $('model').value = state.model;
  $('catalog-summary').textContent = options.scopes.length ? new Set(options.scopes.map(s => s.doc_id)).size+' manuals in this catalog' : 'No manuals in this catalog';
}
$('model').onchange = () => {state.model = $('model').value; clearScope(); invalidateResults();};
$('continue').onclick = () => {error(''); go(2);};
$('back-equipment').onclick = () => go(1);
$('step-1').onclick = () => go(1);
$('step-2').onclick = () => go(2);
$('step-3').onclick = () => {if(lastSearch) go(3);};
function searchHint() {
  const hasSelection = state.category || state.model || state.requirements.length;
  $('find-manuals').disabled = !hasSelection || !options.scopes.length;
  $('search-hint').textContent = !options.scopes.length ? 'This catalog is empty.' : !hasSelection ? 'Choose equipment or add a specification.' : '';
}
function renderSpecifications(focusId) {
  const summary = $('selection-summary');
  summary.replaceChildren(node('span', [state.category ? G.label(state.category) : 'All equipment', state.model || 'Any model'].join(' · ')), button('Change','text-button',()=>go(1)));
  $('coverage-note').hidden = options.numeric_filters;
  $('requirements').replaceChildren();
  const observed = new Set(G.scopes(options,state).flatMap(s=>s.attributes.map(a=>a.key)));
  state.requirements.forEach((row, index) => {
    const container = node('div',undefined,'requirement'), top = node('div',undefined,'requirement-top');
    const remove = button('Remove','remove-button',()=>{
      state.requirements.splice(index,1); clearScope(); invalidateResults(); renderSpecifications();
      $('add-requirement').focus();
    }); remove.setAttribute('aria-label','Remove specification '+(index+1));
    top.append(node('span','SPECIFICATION '+(index+1)),remove);
    const fields = node('div',undefined,'requirement-fields');
    const attr = node('select'); attr.id = 'attribute-'+index; attr.append(option('','Choose a specification'));
    for (const known of [true,false]) {
      const choices = options.attributes.filter(a=>observed.has(a.key) === known);
      if(!choices.length) continue;
      const group = node('optgroup'); group.label = known ? 'In this selection' : 'Other specifications';
      choices.forEach(a=>group.append(option(a.key,G.label(a.label)))); attr.append(group);
    }
    attr.value = row.attribute;
    attr.onchange = ()=>{row.attribute=attr.value; row.unit=options.attributes.find(a=>a.key===row.attribute)?.unit || ''; row.value='';row.maximum='';clearScope();invalidateResults();renderSpecifications('comparison-'+index);};
    const comparison = node('select'); comparison.id='comparison-'+index;
    for(const [key,label] of Object.entries(G.comparisons)) if(options.numeric_filters || key==='present') comparison.append(option(key,label));
    comparison.value=row.comparison; comparison.disabled=!row.attribute;
    comparison.onchange=()=>{row.comparison=comparison.value;invalidateResults();renderSpecifications(row.comparison==='present' ? comparison.id : 'value-'+index);};
    fields.append(field('Specification',attr),field('Requirement',comparison));
    if(row.comparison !== 'present'){
      const numeric = node('div',undefined,'numeric-fields');
      for(const key of row.comparison==='between' ? ['value','maximum'] : ['value']) {
        const input=node('input'); input.id=key+'-'+index; input.type='text';input.inputMode='decimal';input.autocomplete='off';input.value=row[key];input.maxLength=32;
        input.oninput=()=>{row[key]=input.value;invalidateResults();};
        numeric.append(field(key==='maximum'?'Maximum':row.comparison==='between'?'Minimum':'Value',input));
      }
      const unit=node('select'); unit.id='unit-'+index;
      const standard=options.attributes.find(a=>a.key===row.attribute)?.unit;
      (G.units[standard] || []).forEach(u=>unit.append(option(u,u)));unit.value=row.unit;
      unit.onchange=()=>{row.unit=unit.value;invalidateResults();};
      const unitField=field('Unit',unit);unitField.className='unit-field';numeric.append(unitField);fields.append(numeric);
    }
    container.append(top,fields);$('requirements').append(container);
  });
  if(!state.requirements.length) $('requirements').append(node('p','No specification filter.','muted'));
  $('add-requirement').disabled=state.requirements.length>=8;
  renderScopeFilters(); searchHint(); if(focusId) $(focusId)?.focus();
}
function renderScopeFilters() {
  const selectedAttributes = state.requirements.map(r=>r.attribute);
  const attrs=G.scopes(options,state).flatMap(s=>s.attributes).filter(a=>selectedAttributes.includes(a.key));
  const qualifiers=G.unique(attrs.flatMap(a=>a.qualifiers)), variants=G.unique(attrs.flatMap(a=>a.variants));
  const conditions=options.numeric_filters?G.unique(attrs.flatMap(a=>a.conditions)):[];
  $('scope-filters').hidden=!(qualifiers.length || variants.length || conditions.length);
  $('scope-fields').replaceChildren();
  for(const [name,values,title] of [['qualifier',qualifiers,'Rating'],['variant',variants,'Variant']]){
    if(!values.length) continue;
    const select=node('select');select.id='filter-'+name;select.append(option('','Any '+title.toLowerCase()));
    values.forEach(v=>select.append(option(v,name==='qualifier'?G.label(v):v)));select.value=state[name];
    select.onchange=()=>{state[name]=select.value;invalidateResults();};$('scope-fields').append(field(title,select));
  }
  if(conditions.length){
    const choices=node('div',undefined,'condition-options');choices.append(node('p','Operating conditions','muted small'));
    conditions.forEach((value,index)=>{
      const input=node('input');input.type='checkbox';input.id='condition-'+index;input.checked=state.conditions.includes(value);
      input.onchange=()=>{state.conditions=input.checked?G.unique([...state.conditions,value]):state.conditions.filter(v=>v!==value);invalidateResults();};
      const label=node('label');label.append(input,node('span',value));choices.append(label);
    });$('scope-fields').append(choices);
  }
}
$('add-requirement').onclick=()=>{state.requirements.push({attribute:'',comparison:'present',value:'',maximum:'',unit:''});invalidateResults();renderSpecifications('attribute-'+(state.requirements.length-1));};
function criteria() {
  const parts=[state.category?G.label(state.category):'All equipment'];
  if(state.model)parts.push(state.model);
  for(const r of state.requirements){
    let text=G.label(r.attribute);
    if(r.comparison==='present')text+=' covered';
    else text+=' '+G.comparisons[r.comparison].toLowerCase()+' '+r.value+(r.comparison==='between'?'–'+r.maximum:'')+' '+r.unit;
    if(state.qualifier)text=G.label(state.qualifier)+' '+text.toLowerCase();
    parts.push(text);
  }
  if(state.variant)parts.push(state.variant);
  parts.push(...state.conditions);return parts;
}
async function runSearch(query, source) {
  error(''); searchController?.abort(); const version=++searchVersion;searchController=new AbortController();
  lastSearch=null;attemptedSource=source;saveButtons.clear();$('results').replaceChildren();$('gaps').hidden=true;$('plan-wrap').hidden=true;
  $('result-heading').textContent='Searching…';$('result-message').textContent='';$('result-criteria').replaceChildren();
  const labels=source==='guided'?criteria():[query];labels.forEach(text=>$('result-criteria').append(node('span',text,'criterion')));
  go(3);$('results-step').setAttribute('aria-busy','true');
  try{
    const result=await api('/api/search?q='+encodeURIComponent(query)+'&method=lexical',{signal:searchController.signal});
    if(version!==searchVersion)return;
    lastSearch={query,source,result};renderResults(result,query);
  }catch(e){
    if(e.name==='AbortError' || version!==searchVersion)return;
    $('result-heading').textContent='Search unavailable';$('result-message').textContent='Edit your search and try again.';error(e.message);
  }finally{if(version===searchVersion)$('results-step').removeAttribute('aria-busy');}
}
$('guided-form').onsubmit=event=>{event.preventDefault();try{runSearch(G.buildQuery(state,options),'guided');}catch(e){error(e.message);}};
$('search-form').onsubmit=event=>{event.preventDefault();const query=$('query').value.trim();if(query)runSearch(query,'text');};
$('edit-search').onclick=()=>{go(attemptedSource==='text'?1:2);if(attemptedSource==='text'){$('text-search').open=true;$('query').focus();}};
$('new-search').onclick=()=>{state=freshState();invalidateResults();furthest=1;renderEquipment();$('query').value='';$('text-search').open=false;error('');go(1);};
function renderResults(result,query){
  const total=result.total_matches || 0;
  const headings={ready:total+' '+(total===1?'match':'matches'),unknown:'No confirmed matches',conflict:'Conflicting specifications',no_match:'No matches in this catalog',clarify:'Refine your search',unsupported:'Adjust your search'};
  const descriptions={ready:total>result.results.length?'Showing '+result.results.length+' of '+total+' matches. Narrow your search to see the rest.':'Save the manuals you want to request.',unknown:'Review the missing details below, or change your requirements.',conflict:'Review the conflicting records below.',no_match:'Try fewer requirements or another equipment type.'};
  $('result-heading').textContent=headings[result.status]||'Results';
  $('result-message').textContent=descriptions[result.status]||result.message;
  $('results').replaceChildren();
  for(const item of result.results){
    const card=node('article',undefined,'result-card'),top=node('div',undefined,'card-top'),title=node('div');
    title.append(node('h3',item.model || 'Manual'),node('p',item.title,'manual-title'));
    if(item.variant)title.append(node('p',item.variant,'meta'));
    const key=G.key(item),add=button(basket.has(key)?'Saved':'Save','secondary',()=>{
      if(basket.has(key))basket.delete(key);else basket.set(key,{...G.request(item,query),title:item.title});
      renderBasket();
    });
    add.setAttribute('aria-label',(basket.has(key)?'Remove ':'Save ')+(item.model||item.title));add.setAttribute('aria-pressed',String(basket.has(key)));saveButtons.set(key,{button:add,item});
    top.append(title,add);card.append(top);
    if(item.revision)card.append(node('p',item.revision,'meta'));
    for(const warning of item.warnings || [])card.append(node('p',warning==='Document processing is partial; unobserved attributes remain unknown.'?'Partially processed. Other specifications may be missing.':warning,'warning'));
    const details=node('details');details.append(node('summary','Match details'),node('p',item.explanation),node('p','Request reference: '+item.request_ref));card.append(details);$('results').append(card);
  }
  const gaps=result.diagnostics?.details || [];$('gaps').hidden=!gaps.length;$('gap-items').replaceChildren();
  for(const gap of gaps){
    const detail=node('details',undefined,'gap'),summary=node('summary',gap.model||gap.title);
    summary.append(node('small',gap.status==='conflict'?'Conflicting values':'Missing details'));detail.append(summary,node('p',gap.title));
    for(const reason of gap.reasons) detail.append(node('p',reason));
    if(gap.available_conditions?.length)detail.append(node('p','Recorded conditions: '+gap.available_conditions.join('; ')));
    if(gap.available_qualifiers?.length)detail.append(node('p','Recorded ratings: '+gap.available_qualifiers.map(G.label).join(', ')));
    $('gap-items').append(detail);
  }
  const gapCount=(result.diagnostics?.unknown_scopes||0)+(result.diagnostics?.conflicting_scopes||0);
  if(gapCount>gaps.length)$('gap-items').append(node('p','Showing '+gaps.length+' of '+gapCount+' records with missing or conflicting details.','muted'));
  $('plan').textContent=JSON.stringify({query,interpretation:result.plan,diagnostics:result.diagnostics,ranking:result.scoring},null,2);$('plan-wrap').hidden=false;
}
function openBasket(open){$('saved-panel').hidden=!open;$('saved-toggle').setAttribute('aria-expanded',String(open));if(open)$('saved-panel').scrollIntoView({block:'nearest'});}
function renderBasket(){
  $('saved-count').textContent=basket.size;$('download').disabled=!basket.size;$('saved-items').replaceChildren();
  if(!basket.size)$('saved-items').append(node('p','No manuals saved.','saved-empty'));
  for(const [key,item] of basket){
    const row=node('div',undefined,'saved-row'),text=node('div');text.append(node('strong',item.model||'Manual'),node('p',item.title));
    const remove=button('Remove','remove-button',()=>{basket.delete(key);renderBasket();$('saved-toggle').focus();});remove.setAttribute('aria-label','Remove '+(item.model||item.title)+' from request list');row.append(text,remove);$('saved-items').append(row);
  }
  for(const [key,{button:b,item}] of saveButtons){b.textContent=basket.has(key)?'Saved':'Save';b.setAttribute('aria-pressed',String(basket.has(key)));b.setAttribute('aria-label',(basket.has(key)?'Remove ':'Save ')+(item.model||item.title));}
}
$('saved-toggle').onclick=()=>openBasket($('saved-panel').hidden);
$('view-saved').onclick=()=>{openBasket(true);$('saved-toggle').focus();};
$('download').onclick=()=>{
  const payload={schema_version:1,catalog:info.catalog,requests:[...basket.values()].map(({title,...item})=>item),note:'Document request references only; no documents are transmitted.'};
  const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'})),a=node('a');a.href=url;a.download='vopt-document-requests.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};

function shownItems() { const f=$('review-filter').value; return record.items.filter(i => f==='all' || (f==='pending' && ['pending','stale'].includes(i.review_status)) || (f==='accepted' && ['accept','correct'].includes(i.review_status)) || (f==='rejected' && i.review_status==='reject')); }
function candidates(prefer) { const items=shownItems(); $('candidates').replaceChildren(); selected=items.find(i=>i.assertion.assertion_id===prefer) || items[0];
  for (const i of items) { const a=i.assertion, b=node('button',`${a.model} · ${a.attribute.replaceAll('_',' ')}`,`candidate${selected===i?' active':''}`);b.append(node('small',`${a.value}${a.value_max===null||a.value_max===undefined?'':'–'+a.value_max} ${a.unit} · p.${a.evidence.page} · ${i.review_status}`));b.onclick=()=>candidates(a.assertion_id);$('candidates').append(b); }
  detail();
}
function detail() { $('candidate-detail').replaceChildren();$('decision-form').hidden=!selected;$('source-page').hidden=true;$('page-full').hidden=true;$('page-label').textContent='';if(!selected){$('candidate-detail').append(node('p','No candidates in this view. Empty extraction does not establish absence.'));return;}
  const a=selected.assertion, current={...a,...(selected.review_status==='correct' ? selected.event.correction : {})};$('candidate-detail').append(node('h2',`${current.attribute.replaceAll('_',' ')} · ${current.model}`),node('p',`${current.value}${current.value_max===null||current.value_max===undefined?'':'–'+current.value_max} ${current.unit} · ${current.qualifier} · ${selected.review_status}`));
  if(current.conditions?.length)$('candidate-detail').append(node('p',`Conditions: ${current.conditions.join('; ')}`));
  if(typeof current.value==='string')$('candidate-detail').append(node('p','Discrete alternatives: presence can be approved for coverage. Value release requires an explicit supported value and variant correction.', 'warning'));
  $('candidate-detail').append(node('p',`Extraction: ${a.method} · confidence ${a.confidence}. Confidence is not validated probability.`, 'meta'),node('div',a.evidence.text,'evidence'));
  if(a.evidence.context?.length){
    const context=node('details');context.append(node('summary','Inherited headers and qualifying evidence'));
    for(const item of a.evidence.context){const link=node('a',`View context on PDF page ${item.page}`);link.href=`/api/page/${encodeURIComponent(activeDoc)}?page=${item.page}&assertion=${encodeURIComponent(a.assertion_id)}`;link.target='_blank';link.rel='noopener';context.append(node('p',item.text),link);}
    $('candidate-detail').append(context);
  }
  if(selected.event)$('candidate-detail').append(node('p',`Latest review: ${selected.event.actor} (${selected.event.actor_kind}), ${selected.event.reason || 'no note'}.`));
  $('reason').value='';$('correction').value=JSON.stringify(Object.fromEntries(['model','variant','attribute','value','value_max','unit','qualifier','conditions','tolerance'].filter(k=>k in current).map(k=>[k,current[k]])),null,2);
  $('page-label').textContent=`PDF page ${a.evidence.page} · evidence box: ${a.evidence.bbox.map(v=>Math.round(v)).join(', ')}`;
  const pageURL=`/api/page/${encodeURIComponent(activeDoc)}?page=${a.evidence.page}&assertion=${encodeURIComponent(a.assertion_id)}`;
  $('source-page').onload=()=>{$('source-page').hidden=false;$('page-full').hidden=false;};$('source-page').onerror=()=>{error('Source page could not be rendered. Check source hash and local extraction dependencies.');};$('source-page').src=pageURL;$('page-full').href=pageURL;
}
async function loadRecord(prefer) { const version=++loadVersion;activeDoc=$('documents').value;if(!activeDoc)return;try{const r=await api(`/api/record/${encodeURIComponent(activeDoc)}`);if(version!==loadVersion)return;record=r;const pending=r.items.filter(i=>['pending','stale'].includes(i.review_status)).length;$('review-summary').textContent=`${r.pages.length} pages · ${r.items.length} candidates · ${pending} pending/stale · processing ${r.processing_status}. Human review is recorded only when you decide.`;candidates(prefer);}catch(e){error(e.message);} }
$('documents').onchange=()=>loadRecord();$('review-filter').onchange=()=>candidates();
async function decide(decision) {
  if(!selected)return;
  error('');
  const id=selected.assertion.assertion_id;
  const buttons=['accept','correct','reject'].map($);
  buttons.forEach(b=>busy(b,true));
  try {
    const body={doc_id:activeDoc,assertion_id:id,decision,actor:$('actor').value.trim(),reason:$('reason').value,
      fingerprint:record.fingerprint,event_id:selected.event?.event_id || 0};
    if(decision==='correct')body.correction=JSON.parse($('correction').value);
    // Re-approval keeps the effective value shown above; it never silently restores raw extraction.
    if(decision==='accept' && selected.review_status==='correct'){
      body.decision='correct';body.correction=selected.event.correction;
    }
    await api('/api/review',{method:'POST',headers:{'Content-Type':'application/json','X-VOPT-Token':info.csrf},body:JSON.stringify(body)});
    await loadRecord(id);
  } catch(e) {
    if(e.message.includes('reload'))await loadRecord(id);
    error(e.message);
  } finally { buttons.forEach(b=>busy(b,false)); }
}
$('accept').onclick=()=>decide('accept');$('correct').onclick=()=>decide('correct');$('reject').onclick=()=>decide('reject');


(async()=>{
  try{
    info=await api('/api/info');$('mode').textContent=info.mode==='review'?'Offline · Review':'Offline';
    if(info.mode==='discovery'){
      options=await api('/api/options');renderEquipment();renderBasket();
      $('discovery').hidden=false;
    }else{
      $('review').hidden=false;const records=await api('/api/records');
      for(const r of records){const o=option(r.document.doc_id,r.document.title+' · '+r.pending+' pending');$('documents').append(o);}
      if(!records.length)$('review-summary').textContent='No processed documents.';else await loadRecord();
    }
  }catch(e){error(e.message);}finally{$('loading').hidden=true;}
})();
