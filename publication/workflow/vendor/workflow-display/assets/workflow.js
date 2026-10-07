/* Workflow Display: data stays text; connections are a view of declared dependencies. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const control = (text, action, className) => {
    const node = make('button', text, className);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
  };
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const phone = matchMedia('(max-width: 760px)');
  const normalize = text => String(text ?? '').normalize('NFKD').toLowerCase();
  const announce = text => { $('workflow-status').textContent = text; };
  const key = (side, id) => `${side}:${id}`;
  const number = index => String(index + 1).padStart(2, '0');
  const cards = new Map(), rows = new Map(), indexes = new Map(), planButtons = new Map();
  const reveal = $('plan-reveal'), guide = $('workflow-guide'), svg = $('connection-lines');
  let data, plan, expanded = false, pinned = null, active = null, drawFrame = 0;
  let focusTimer, layoutTimer, switchAnimation, fadeAnimation, navigation = 0;

  function related(step) {
    return (step.related || []).filter(id => id !== step.id && rows.has(id));
  }
  function pairsFor(origin) {
    if (!origin || !plan) return [];
    return plan.steps.flatMap(step => [step.id, ...related(step)]
      .filter(target => origin.side === 'plain' ? step.id === origin.id : target === origin.id)
      .map(target => [step.id, target]));
  }
  function stepLabel(id) {
    const index = plan.steps.findIndex(step => step.id === id);
    return `${number(index)} · ${plan.steps[index]?.title || id}`;
  }
  function svgNode(tag, attributes) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, String(value)));
    return node;
  }
  function drawConnections(animate = false) {
    svg.replaceChildren();
    if (!plan || !expanded || phone.matches) return;
    const board = $('workflow-board').getBoundingClientRect();
    if (!board.width || !board.height) return;
    svg.setAttribute('viewBox', `0 0 ${board.width} ${board.height}`);
    const defs = svgNode('defs', {});
    const marker = svgNode('marker', {id: 'dependency-arrow', viewBox: '0 0 8 8', refX: 7, refY: 4, markerWidth: 6, markerHeight: 6, orient: 'auto'});
    marker.append(svgNode('path', {d: 'M1 1 L7 4 L1 7 Z', class: 'dependency-arrow'}));
    defs.append(marker); svg.append(defs);
    const pairs = active ? pairsFor(active) : plan.steps.map(step => [step.id, step.id]);
    pairs.forEach(([left, right]) => {
      if (rows.get(left).hidden || rows.get(right).hidden) return;
      const a = cards.get(key('plain', left)), b = cards.get(key('artifact', right));
      const aRect = a.getBoundingClientRect(), bRect = b.getBoundingClientRect();
      const aTitle = a.querySelector('.card-title').getBoundingClientRect();
      const bTitle = b.querySelector('.card-title').getBoundingClientRect();
      const x1 = aRect.right - board.left, y1 = aTitle.top + aTitle.height / 2 - board.top;
      const x2 = bRect.left - board.left, y2 = bTitle.top + bTitle.height / 2 - board.top;
      const mid = (x1 + x2) / 2;
      const dependency = left !== right;
      const path = svgNode('path', {
        d: `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`,
        class: `connection-wire${active ? ' is-active' : ''}${dependency ? ' is-dependency' : ''}`,
      });
      if (dependency) path.setAttribute('marker-end', 'url(#dependency-arrow)');
      svg.append(path);
      for (const [x, y] of [[x1, y1], [x2, y2]]) {
        svg.append(svgNode('circle', {cx: x, cy: y, r: active ? 3 : 2, class: `connection-port${active ? ' is-active' : ''}`}));
      }
      if (animate && active && !reduced.matches && path.animate) {
        // Animate a bright moving pulse above the stable dashed/solid relationship.
        // Its direction follows the user's reading direction; arrowheads retain dependency meaning.
        const length = path.getTotalLength();
        const pulse = Math.min(30,length * .25);
        const tracer = svgNode('path', {d: path.getAttribute('d'), class: 'connection-tracer', 'stroke-dasharray': `${pulse} ${length + pulse * 2}`});
        svg.append(tracer);
        const motion = tracer.animate([
          {strokeDashoffset: active.side === 'plain' ? pulse : -length},
          {strokeDashoffset: active.side === 'plain' ? -length : pulse},
        ], {duration: 650, easing: 'cubic-bezier(.22,1,.36,1)'});
        motion.onfinish = () => tracer.remove();
      }
    });
  }
  function scheduleDraw() {
    cancelAnimationFrame(drawFrame);
    drawFrame = requestAnimationFrame(() => drawConnections());
  }
  function trace(origin, notify = false, force = false) {
    if (!plan) return;
    origin = pinned || origin;
    const changed = active?.id !== origin?.id || active?.side !== origin?.side;
    if (!changed && !notify && !force) return;
    active = origin;
    const pairs = pairsFor(origin);
    const connected = new Set(pairs.flatMap(([a,b]) => [key('plain',a),key('artifact',b)]));
    cards.forEach((card, id) => {
      const locked = Boolean(pinned && id === key(pinned.side,pinned.id));
      card.classList.toggle('is-connected', connected.has(id));
      card.classList.toggle('is-origin', Boolean(origin && id === key(origin.side,origin.id)));
      card.classList.toggle('is-pinned', locked);
      card.querySelector('.pin-label').hidden = !locked;
      card.querySelector('.card-title').setAttribute('aria-pressed', String(locked));
    });
    indexes.forEach((button,id) => {
      button.classList.toggle('is-traced', origin?.id === id);
      button.classList.toggle('is-related', connected.has(key('plain',id)) || connected.has(key('artifact',id)));
      button.setAttribute('aria-pressed', String(pinned?.id === id));
    });
    $('trace-summary').textContent = origin ? `${pinned ? 'Locked' : 'Preview'} · ${stepLabel(origin.id)}` : 'Select a heading to keep its connections highlighted.';
    $('trace-summary').classList.toggle('is-locked', Boolean(pinned));
    $('clear-trace').hidden = !pinned;
    drawConnections(changed);
    if (notify) {
      if (!origin) { announce('Connections unlocked. Hover or focus a card to preview.'); return; }
      const linked = pairs.map(([a,b]) => stepLabel(origin.side === 'plain' ? b : a)).join('; ');
      const hidden = pairs.filter(([a,b]) => rows.get(a).hidden || rows.get(b).hidden).length;
      announce(`Locked ${stepLabel(origin.id)}. ${origin.side === 'plain' ? 'Connected implementations' : 'Used by explanations'}: ${linked}.${hidden ? ' Some dependencies are hidden by search. Clear search to show them.' : ''} Press Escape or Unlock step to release.`);
    }
  }
  function hold(side, id, toggle = false) {
    if (toggle && pinned?.side === side && pinned.id === id) { pinned = null; trace(null, true); }
    else { pinned = {side,id}; trace(pinned, true); }
  }
  function jump(side, id) {
    if (rows.get(id).hidden) {
      $('step-search').value = '';
      filterSteps(false);
    }
    hold(side,id);
    const card = cards.get(key(side,id));
    card.scrollIntoView({block: 'start', behavior: reduced.matches ? 'auto' : 'smooth'});
    card.querySelector('.card-title').focus({preventScroll: true});
  }
  function bindTrace(card, side, step) {
    card.addEventListener('pointerenter', event => {
      if (event.pointerType !== 'touch') trace({side,id:step.id});
    });
    card.addEventListener('pointerleave', () => {
      const focused = document.activeElement?.closest('.workflow-card');
      trace(focused ? {side:focused.dataset.side,id:focused.dataset.step} : null);
    });
    card.addEventListener('focusin', () => trace({side,id:step.id}));
    card.addEventListener('focusout', event => {
      if (card.contains(event.relatedTarget)) return;
      const next = event.relatedTarget?.closest?.('.workflow-card');
      trace(next ? {side:next.dataset.side,id:next.dataset.step} : null);
    });
    card.addEventListener('click', event => {
      if (event.target.closest('button,a,pre,input,textarea,select,summary') || !window.getSelection()?.isCollapsed) return;
      hold(side,step.id);
    });
  }
  async function copyArtifact(step, button, code) {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(step.artifact.code);
      button.textContent = 'Copied';
      announce(`${step.artifact.title} copied.`);
      setTimeout(() => { if (button.isConnected) button.textContent = 'Copy'; }, 1800);
    } catch {
      const range = document.createRange();
      range.selectNodeContents(code);
      const selection = window.getSelection();
      selection.removeAllRanges(); selection.addRange(range);
      code.parentElement.focus({preventScroll:true});
      announce('Clipboard unavailable. Text selected; use your system copy command.');
    }
  }
  function relationList(step, side) {
    const node = make('p', undefined, 'card-relations');
    node.append(make('span', side === 'plain' ? `Matching implementation: ${step.artifact.title}. ` : `Explains step ${stepLabel(step.id)}. `));
    const ids = side === 'plain' ? (step.related || []) : plan.steps.filter(candidate => (candidate.related || []).includes(step.id)).map(candidate => candidate.id);
    node.append(make('span', ids.length ? (side === 'plain' ? 'Depends on: ' : 'Required by: ') : (side === 'plain' ? 'No other steps required.' : 'No other steps depend on this.')));
    ids.forEach((id,index) => {
      if (index) node.append(document.createTextNode(', '));
      const button = control(stepLabel(id), () => jump(side === 'plain' ? 'artifact' : 'plain', id), 'relation-link');
      button.setAttribute('aria-label', `Show ${side === 'plain' ? 'required implementation' : 'dependent explanation'} ${stepLabel(id)}`);
      node.append(button);
    });
    return node;
  }
  function createCard(step, index, side) {
    const card = make('article', undefined, `workflow-card ${side}-card`);
    card.dataset.side = side; card.dataset.step = step.id;
    const heading = make('h3');
    const title = control('', () => hold(side,step.id,true), 'card-title');
    title.id = `card-${side}-${index}`;
    title.setAttribute('aria-pressed', 'false');
    card.setAttribute('aria-labelledby', title.id);
    title.append(make('span', number(index), 'step-number'), make('span', side === 'plain' ? step.title : step.artifact.title));
    const pin = make('span', 'Locked', 'pin-label'); pin.hidden = true; pin.setAttribute('aria-hidden','true');
    title.append(pin); heading.append(title); card.append(heading);
    if (side === 'plain') {
      card.append(make('p',step.description,'card-description'));
      if (step.checkpoint) {
        const checkpoint = make('div',undefined,'checkpoint');
        checkpoint.append(make('span','CHECKPOINT'),make('p',step.checkpoint));
        card.append(checkpoint);
      }
      if (step.resources?.length) {
        const resources = make('div',undefined,'resources');
        resources.append(make('span','RESOURCES'));
        step.resources.forEach(resource => {
          try {
            const url = new URL(resource.url);
            if (!['https:','http:'].includes(url.protocol)) return;
            const link = make('a',resource.label);
            link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
            resources.append(link);
          } catch { /* Invalid links are not made interactive. */ }
        });
        card.append(resources);
      }
    } else {
      const tools = make('div',undefined,'code-tools');
      const pre = make('pre'), code = make('code',step.artifact.code);
      pre.tabIndex = 0; pre.setAttribute('aria-label',step.artifact.title); pre.append(code);
      const copy = control('Copy',() => copyArtifact(step,copy,code),'copy-button');
      copy.setAttribute('aria-label',`Copy ${step.artifact.title}`);
      const wrap = control('Wrap', () => {
        const wrapped = pre.classList.toggle('is-wrapped');
        wrap.setAttribute('aria-pressed',String(wrapped));
        scheduleDraw();
      },'copy-button');
      wrap.setAttribute('aria-label',`Wrap lines in ${step.artifact.title}`);
      wrap.setAttribute('aria-pressed','false');
      const actions = make('div',undefined,'code-actions');
      actions.append(wrap,copy);
      tools.append(make('span',step.artifact.language ? step.artifact.language.toUpperCase() : 'IMPLEMENTATION'),actions);
      card.append(tools,pre);
      if (step.artifact.note) card.append(make('p',step.artifact.note,'artifact-note'));
    }
    card.append(relationList(step,side));
    bindTrace(card,side,step); cards.set(key(side,step.id),card);
    return card;
  }
  function filterSteps(notify = true) {
    if (!plan) return;
    const query = normalize($('step-search').value).trim();
    const words = query.split(/\s+/).filter(Boolean);
    pinned = null; active = undefined;
    let count = 0;
    plan.steps.forEach(step => {
      const text = normalize([step.title,step.description,step.checkpoint,step.artifact.title,step.artifact.code,step.artifact.note,...(step.resources || []).map(item=>item.label)].join(' '));
      const visible = words.every(word => text.includes(word));
      rows.get(step.id).hidden = !visible; indexes.get(step.id).hidden = !visible;
      if (visible) count++;
    });
    $('step-count').textContent = `${count} / ${plan.steps.length} steps`;
    $('empty-result').hidden = count !== 0;
    $('clear-search').hidden = !$('step-search').value;
    trace(null,false,true); scheduleDraw();
    if (notify) announce(`${count} of ${plan.steps.length} step pairs shown.${query ? ' Clear search to restore all dependencies.' : ''}`);
  }
  function renderPlan() {
    cards.clear(); rows.clear(); indexes.clear(); pinned = null; active = null;
    $('step-search').value = '';
    $('guide-title').textContent = plan.title;
    $('guide-summary').textContent = plan.summary;
    $('guide-end').textContent = 'Use the checkpoints to review your work. Connections show the dependencies declared in this guide.';
    $('step-rows').replaceChildren(); $('step-index').replaceChildren();
    $('step-index').style.setProperty('--step-count', Math.min(8, plan.steps.length));
    $('step-index').style.setProperty('--step-count-medium', Math.min(4, plan.steps.length));
    $('step-index').style.setProperty('--step-count-small', Math.min(3, plan.steps.length));
    plan.steps.forEach((step,index) => {
      const row = make('div',undefined,'workflow-row');
      row.setAttribute('role','group'); row.setAttribute('aria-label',`Step ${index+1}: ${step.title}`);
      row.append(createCard(step,index,'plain'),createCard(step,index,'artifact'));
      rows.set(step.id,row); $('step-rows').append(row);
      const button = control('',() => jump('plain',step.id));
      button.append(make('span',number(index)),make('span',step.title));
      button.setAttribute('aria-label',`Step ${index+1}: ${step.title}`);
      button.setAttribute('aria-pressed','false');
      indexes.set(step.id,button); $('step-index').append(button);
    });
    filterSteps(false);
  }
  function setExpanded(open) {
    if (!open && guide.contains(document.activeElement)) planButtons.get(plan.id)?.focus();
    expanded = open;
    reveal.classList.toggle('is-expanded',open);
    reveal.inert = !open;
    reveal.setAttribute('aria-hidden',String(!open));
    planButtons.forEach((button,id) => {
      const selected = id === plan?.id && open;
      button.classList.toggle('is-selected',selected);
      button.setAttribute('aria-expanded',String(selected));
      button.setAttribute('aria-pressed',String(selected));
      button.querySelector('.plan-choice-action').textContent = selected ? 'Close plan' : 'Open plan';
    });
    if (open) scheduleDraw();
    clearTimeout(layoutTimer);
    layoutTimer = setTimeout(scheduleDraw, reduced.matches ? 0 : 380);
  }
  function selectPlan(id) {
    const next = data.plans.find(item => item.id === id);
    if (!next) return;
    const changed = plan?.id !== id, wasOpen = expanded;
    const oldHeight = reveal.getBoundingClientRect().height;
    const request = ++navigation;
    clearTimeout(focusTimer); switchAnimation?.cancel(); fadeAnimation?.cancel();
    plan = next;
    if (changed) renderPlan();
    const open = changed || !expanded;
    setExpanded(open);
    if (open && wasOpen && changed && !reduced.matches && reveal.animate) {
      const newHeight = reveal.getBoundingClientRect().height;
      switchAnimation = reveal.animate([{height:`${oldHeight}px`},{height:`${newHeight}px`}], {duration:360,easing:'cubic-bezier(.22,1,.36,1)'});
      fadeAnimation = guide.animate([{opacity:.25},{opacity:1}], {duration:260,easing:'ease-out'});
      switchAnimation.onfinish = scheduleDraw;
    }
    announce(`${plan.title} ${open ? 'opened' : 'collapsed'}.${open ? ` ${plan.steps.length} step pairs.` : ''}`);
    if (open) focusTimer = setTimeout(() => {
      if (request !== navigation || !expanded) return;
      $('guide-title').focus({preventScroll:true});
      $('guide-title').scrollIntoView({block:'start',behavior:reduced.matches?'auto':'smooth'});
      scheduleDraw();
    }, reduced.matches ? 0 : 380);
  }
  function exportGuide() {
    if (!plan) return;
    const lines = [`# ${plan.title}`,'',plan.summary,''];
    plan.steps.forEach((step,index) => {
      lines.push(`## ${index+1}. ${step.title}`,'',step.description,'');
      if (step.checkpoint) lines.push(`Checkpoint: ${step.checkpoint}`,'');
      lines.push(`### ${step.artifact.title}`,'');
      const matches = step.artifact.code.match(/`+/g) || [];
      const fence = '`'.repeat(Math.max(3,...matches.map(item=>item.length+1)));
      lines.push(fence,step.artifact.code,fence,'');
      if (step.artifact.note) lines.push(step.artifact.note,'');
      if (step.related?.length) lines.push(`Depends on: ${step.related.map(stepLabel).join('; ')}.`,'');
      if (step.resources?.length) lines.push('Resources:',...step.resources.map(item=>`- ${item.label}: ${item.url}`),'');
    });
    const url = URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/markdown;charset=utf-8'}));
    const link = make('a'); link.href = url; link.download = `${plan.id}-guide.md`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url),1000);
    announce(`${plan.title} guide downloaded.`);
  }
  function clearSearch() {
    $('step-search').value = ''; filterSteps(); $('step-search').focus({preventScroll:true});
  }
  try {
    data = JSON.parse($('workflow-data').textContent);
    if (!Array.isArray(data.plans) || !data.plans.length) throw new Error('Missing plans');
    document.title = data.title;
    $('page-title').textContent = data.title;
    $('page-description').textContent = data.description;
    $('page-eyebrow').textContent = data.eyebrow || 'WORKFLOW DISPLAY';
    $('page-footer').textContent = data.footer || 'Workflow Display · Read the purpose. Inspect the implementation. Follow the connection.';
    data.plans.forEach(item => {
      const button = control('',()=>selectPlan(item.id),'plan-choice');
      button.setAttribute('aria-controls','workflow-guide');
      button.setAttribute('aria-pressed','false'); button.setAttribute('aria-expanded','false');
      const dot = make('span',undefined,'plan-choice-dot'); dot.setAttribute('aria-hidden','true');
      const text = make('span',undefined,'plan-choice-text');
      text.append(make('span',item.title,'plan-choice-title'),make('span',item.summary,'plan-choice-purpose'),make('span',`${item.status ? item.status + ' · ' : ''}${item.steps.length} steps`,'plan-choice-meta'),make('span','Open plan','plan-choice-action'));
      const arrow = make('span','⌄','plan-choice-arrow'); arrow.setAttribute('aria-hidden','true');
      button.append(dot,text,arrow); planButtons.set(item.id,button); $('plan-options').append(button);
    });
    $('plan-options').addEventListener('keydown',event => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const buttons = [...planButtons.values()], index = buttons.indexOf(event.target);
      if (index < 0) return;
      const destination = {ArrowRight:(index+1)%buttons.length,ArrowLeft:(index-1+buttons.length)%buttons.length,Home:0,End:buttons.length-1}[event.key];
      if (destination === undefined) return;
      event.preventDefault(); buttons[destination].focus();
    });
    $('step-search').addEventListener('input',()=>filterSteps());
    $('clear-search').addEventListener('click',clearSearch);
    $('show-all').addEventListener('click',clearSearch);
    $('clear-trace').addEventListener('click',()=>{
      const previous = pinned; pinned = null;
      if (previous) cards.get(key(previous.side,previous.id))?.querySelector('.card-title').focus({preventScroll:true});
      trace(null,true);
    });
    $('download-guide').addEventListener('click',exportGuide);
    document.addEventListener('keydown',event=>{
      if (event.key === 'Escape' && expanded && pinned) { pinned = null; trace(null,true); }
    });
    reveal.addEventListener('transitionend',event => {
      if (event.target === reveal && event.propertyName === 'grid-template-rows') scheduleDraw();
    });
    new ResizeObserver(scheduleDraw).observe($('workflow-board'));
    window.addEventListener('resize',scheduleDraw);
    phone.addEventListener('change',scheduleDraw);
    reduced.addEventListener('change',()=>{
      switchAnimation?.cancel(); fadeAnimation?.cancel();
      svg.getAnimations({subtree:true}).forEach(animation=>animation.finish());
      scheduleDraw();
    });
    document.fonts?.ready.then(scheduleDraw);
  } catch {
    $('load-error').hidden = false;
  }
})();
