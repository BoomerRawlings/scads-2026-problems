#!/usr/bin/env node
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readData, validateData } from './validate.mjs';

const skillDirectory = fileURLToPath(new URL('../', import.meta.url));
const defaultData = path.join(skillDirectory, 'examples', 'content-pipeline.json');
const defaultAssets = path.join(skillDirectory, 'assets');

export function serializeData(data) {
  return JSON.stringify(data)
    .replace(/</g, '\\u003c')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

/** Produce one self-contained document; no runtime network or Node required. */
export async function renderWorkflow(data, { assetsDirectory = defaultAssets } = {}) {
  validateData(data);
  const [template, styles, script] = await Promise.all([
    readFile(path.join(assetsDirectory, 'template.html'), 'utf8'),
    readFile(path.join(assetsDirectory, 'workflow.css'), 'utf8'),
    readFile(path.join(assetsDirectory, 'workflow.js'), 'utf8'),
  ]);
  const values = { STYLES: styles, DATA: serializeData(data), SCRIPT: script };
  for (const key of Object.keys(values)) {
    const marker = `{{${key}}}`;
    const count = template.split(marker).length - 1;
    if (count !== 1) throw new Error(`Template must contain ${marker} exactly once; found ${count}`);
  }
  // One pass and callback replacement keep $&, $', and marker text in data literal.
  return template.replace(/\{\{(STYLES|DATA|SCRIPT)\}\}/g, (_, key) => values[key]);
}

export async function buildWorkflow({ dataPath = defaultData, outputPath = 'workflow.html', force = false } = {}) {
  const data = await readData(path.resolve(dataPath));
  const html = await renderWorkflow(data);
  const destination = path.resolve(outputPath);
  await mkdir(path.dirname(destination), { recursive: true });
  try { await writeFile(destination, html, { encoding: 'utf8', flag: force ? 'w' : 'wx' }); }
  catch (error) {
    if (error.code === 'EEXIST') throw new Error(`Output already exists: ${destination}. Choose another --out or pass --force to replace it.`);
    throw error;
  }
  return destination;
}

const help = `Usage: node scripts/build.mjs [--data <file.json>] [--out <file.html>] [--force]

Create a self-contained animated workflow display. Requires Node.js 18+.
  --data   Workflow JSON; default: bundled examples/content-pipeline.json
  --out    Output HTML; default: workflow.html in the current directory
  --force  Replace an existing output file
  --help   Show this help

Open the generated HTML directly in a browser. No install, server, or npm step.`;

function parseArgs(args) {
  const options = {};
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === '--help' || arg === '-h') return { help: true };
    if (arg === '--force') { options.force = true; continue; }
    if (arg === '--data' || arg === '--out') {
      if (!args[i + 1] || args[i + 1].startsWith('--')) throw new Error(`${arg} needs a file path. Use --help for usage.`);
      options[arg === '--data' ? 'dataPath' : 'outputPath'] = args[++i];
      continue;
    }
    throw new Error(`Unknown argument "${arg}". Use --help for usage.`);
  }
  return options;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  Promise.resolve().then(async () => {
    const options = parseArgs(process.argv.slice(2));
    if (options.help) { console.log(help); return; }
    console.log(`Created ${await buildWorkflow(options)}\nOpen this file directly in a browser.`);
  }).catch(error => { console.error(`Build failed: ${error.message}`); process.exitCode = 1; });
}
