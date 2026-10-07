import { readFile, writeFile, readdir, mkdir, copyFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { buildWorkflow } from './vendor/workflow-display/scripts/build.mjs';

const directory = path.dirname(fileURLToPath(import.meta.url));
const zone = 'America/Los_Angeles';
const names = { '01': 'Organizational sensemaking', '02': 'Conversational 311 analytics', '03': 'Semantic discovery', '04': 'Organizational knowledge graphs', '05': 'GraphRAG discovery', '01–09': 'Collection / all nine projects' };
const slugs = { '01': '01-sensemaking', '02': '02-311-analytics', '03': '03-semantic-discovery', '04': '04-org-knowledge-graphs', '05': '05-graphrag-discovery' };
const date = value => new Intl.DateTimeFormat('en-US', { timeZone: zone, month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value));
const time = value => new Intl.DateTimeFormat('en-US', { timeZone: zone, hour: 'numeric', minute: '2-digit', second: '2-digit', timeZoneName: 'short' }).format(new Date(value));
function elapsed(ms) {
  const seconds = Math.round(ms / 1000);
  const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds % 3600 / 60), remainder = seconds % 60;
  return [hours && `${hours}h`, minutes && `${minutes}m`, `${remainder}s`].filter(Boolean).join(' ');
}
const events = [];
for (const file of (await readdir(directory)).filter(name => /^projects-.*\.json$/.test(name)).sort()) {
  const fragment = JSON.parse(await readFile(path.join(directory, file), 'utf8'));
  events.push(...fragment.events);
}
events.forEach(event => {
  event.project = String(event.project).padStart(2, '0');
  if (!/^[a-z]/i.test(event.id)) event.id = `p${event.id}`;
});
events.sort((a, b) => Date.parse(a.startedAt) - Date.parse(b.startedAt) || a.id.localeCompare(b.id));
assert.equal(new Set(events.map(e => e.id)).size, events.length, 'Event IDs must be unique');
for (const event of events) {
  assert(names[event.project], `Unknown project ${event.project}`);
  assert(Number.isFinite(Date.parse(event.startedAt)), `Missing start: ${event.id}`);
  assert(Number.isFinite(Date.parse(event.completedAt)), `Missing end: ${event.id}`);
  assert(Date.parse(event.completedAt) >= Date.parse(event.startedAt), `Reversed window: ${event.id}`);
  assert(event.durationMs > 0, `Missing recorded duration: ${event.id}`);
  assert(event.promptExcerpt?.trim() && event.outcome?.trim(), `Empty pair: ${event.id}`);
  assert(!/[A-Z]:[\\/]|\/Users\/|\/home\/|<in-app-browser-context|<environment_context|threadId|rolloutOrdinal/i.test(JSON.stringify(event)), `Private/runtime material in ${event.id}`);
}
const lastByProject = new Map();
const steps = events.map(event => {
  const number = event.project === '01–09' ? 'P01–P09' : `P${event.project}`;
  const startLabel = `${date(event.startedAt)} · ${time(event.startedAt)}`;
  const endLabel = `${date(event.completedAt)} · ${time(event.completedAt)}`;
  const prior = lastByProject.get(event.project);
  const related = event.project === '01–09'
    ? Object.keys(slugs).map(project => events.filter(e => e.project === project && Date.parse(e.completedAt) <= Date.parse(event.completedAt)).at(-1)?.id).filter(Boolean)
    : prior ? [prior] : [];
  lastByProject.set(event.project, event.id);
  return {
    id: event.id,
    title: `${number} · ${event.title}`,
    description: event.outcome,
    checkpoint: `${startLabel} → ${endLabel}. ${elapsed(event.durationMs)} elapsed. ${event.timeBasis || 'Recorded session window; not active work time.'}`,
    artifact: {
      title: `${number} · ${startLabel}`,
      language: 'My prompt',
      code: event.promptExcerpt,
      note: `${event.promptKind || event.promptType || 'Verbatim excerpt'}. ${names[event.project]}.${event.context || event.promptContext ? ` ${event.context || event.promptContext}` : ''}`,
    },
    related,
    resources: slugs[event.project]
      ? [{ label: 'Project and demo', url: `https://boomerrawlings.com/work/scads-2026/${slugs[event.project]}/` }, { label: 'Published source snapshot', url: `https://github.com/BoomerRawlings/scads-2026-problems/tree/scads-2026-10-07/projects/${slugs[event.project]}` }]
      : [{ label: 'Nine papers and project pages', url: 'https://boomerrawlings.com/work/scads-2026/#problems' }, { label: 'Published source', url: 'https://github.com/BoomerRawlings/scads-2026-problems' }],
  };
});
const data = {
  eyebrow: 'MY PROCESS / OCTOBER 6–7, 2026',
  title: 'How I worked through the problems',
  description: 'One chronological stream of my prompts, decisions, and development outcomes. Project labels keep the parallel work visible. All displayed times are Pacific (PDT). Elapsed times describe overlapping sessions, not hours worked.',
  footer: 'Curated verbatim prompt excerpts and recorded development outcomes. Timestamps mark session windows; prompts within a session may have arrived later. Sessions overlap, so elapsed times are not summed hours worked. Test counts belong to individual iterations. The log includes later development than some published source and paper snapshots. P06–P09 appear together in the publication step as research proposals; implementation had not begun.',
  plans: [{ id: 'scads-development', title: 'One stream across nine projects', summary: 'Follow the interleaved sessions from the first brief to research, implementation, reviews, and publication. Each outcome stays paired with the prompt that directed it.', status: `${events.length} recorded sessions · Pacific time`, steps }],
};
const dataPath = path.join(directory, 'workflow.json');
await writeFile(dataPath, JSON.stringify(data, null, 2) + '\n');
await writeFile(path.join(directory, 'events.json'), JSON.stringify({ schemaVersion: 1, displayTimeZone: zone, timestampBasis: 'Recorded session windows; overlapping elapsed time is not summed effort.', events }, null, 2) + '\n');
const htmlPath = path.join(directory, 'workflow.html');
await buildWorkflow({ dataPath, outputPath: htmlPath, force: true });
let html = await readFile(htmlPath, 'utf8');
const embeddedData = html.match(/<script type="application\/json" id="workflow-data">[\s\S]*?<\/script>/)?.[0];
assert(embeddedData, 'Expected one safely serialized data block');
const dataMarker = '__SCADS_SERIALIZED_WORKFLOW_DATA__';
assert(!html.includes(dataMarker), 'Reserved build marker in content');
html = html.replace(embeddedData, dataMarker);
const palette = { '#111417': '#182b49', '#181d21': '#203854', '#222a2f': '#2a4563', '#101417': '#14243d', '#e2e8eb': '#fffdf8', '#a6b3bb': '#cfdae7', '#83959f': '#a5bed3', '#3c4a52': '#446079', '#b5d4df': '#00c6d7', '#c9b88e': '#ffcd00', '#202d33': '#284764', '#d1ebf5': '#ffcd00' };
for (const [from, to] of Object.entries(palette)) html = html.replaceAll(from, to);
html = html.replace('Choose a workflow', 'Open the chronological stream').replace('Open a plan to follow each explanation beside its implementation.', 'All projects share one timeline. Read each development outcome beside my prompt.').replaceAll('Open plan', 'Open chronological workflow').replaceAll('Close plan', 'Collapse workflow').replace('01 / EXPLANATION', '01 / WORK & TIMING').replace('02 / IMPLEMENTATION', '02 / MY PROMPT');
const wording = {
  'Matching implementation:': 'Matching prompt:',
  'Connected implementations': 'Connected prompts',
  'Used by explanations': 'Linked outcomes',
  'required implementation': 'earlier prompt',
  'dependent explanation': 'later outcome',
  'No other steps required.': 'No earlier project prompt linked.',
  'No other steps depend on this.': 'No later session linked here.',
  'Depends on:': 'Earlier context:',
  'Required by:': 'Later context:',
  'CHECKPOINT': 'SESSION WINDOW',
  'Checkpoint:': 'Session window:',
  'MATCHING IMPLEMENTATION': 'MY PROMPT',
  'EXPLANATION': 'WORK & TIMING',
  'Purpose and checkpoint on the left. The matching prompt, code, or instructions on the right.': 'Recorded outcome and session timing on the left. My prompt on the right.',
  'Dashed arrows point to other steps this step depends on.': 'Dashed arrows link related project history.',
  'Solid line: matching pair.': 'Solid line: outcome and matching prompt.',
  'Dashed arrow: explanation → earlier prompt.': 'Dashed arrow: related project history.',
  'Dependencies are also listed on every card.': 'Related sessions are also listed on each pair.',
  'Use the checkpoints to review your work. Connections show the dependencies declared in this guide.': 'Session windows may overlap. Connections trace related project history, not the contents of a particular release.',
};
for (const [from, to] of Object.entries(wording)) html = html.replaceAll(from, to);
html = html.replace('pre.tabIndex = 0;', "pre.classList.add('is-wrapped'); pre.tabIndex = 0;").replace("wrap.setAttribute('aria-pressed','false');", "wrap.setAttribute('aria-pressed','true');");
html = html.replace('drawFrame = requestAnimationFrame(() => drawConnections());', 'drawFrame = requestAnimationFrame(() => drawConnections(Boolean(active)));').replace('drawConnections(changed);', 'drawConnections(changed || notify);');
html = html.replace(dataMarker, () => embeddedData);
await writeFile(htmlPath, html);
const siteIndex = process.argv.indexOf('--site');
if (siteIndex !== -1) {
  const site = path.resolve(process.argv[siteIndex + 1]);
  const dataDestination = path.join(site, 'public/data/scads/workflow.json');
  const htmlDestination = path.join(site, 'public/documents/scads-2026/workflow.html');
  await mkdir(path.dirname(dataDestination), { recursive: true });
  await mkdir(path.dirname(htmlDestination), { recursive: true });
  await copyFile(dataPath, dataDestination);
  await copyFile(htmlPath, htmlDestination);
}
console.log(`Workflow built: ${events.length} chronological sessions, one plan; JSON and self-contained HTML.`);
