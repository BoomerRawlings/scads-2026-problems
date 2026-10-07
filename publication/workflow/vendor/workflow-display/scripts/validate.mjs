#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ID = /^[A-Za-z][A-Za-z0-9_-]*$/;
const fail = (location, message) => { throw new Error(`${location}: ${message}`); };

function object(value, location, allowed) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    fail(location, 'expected an object');
  }
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) fail(`${location}.${key}`, `unknown field; allowed: ${allowed.join(', ')}`);
  }
}

function text(value, location, optional = false) {
  if (optional && value === undefined) return;
  if (typeof value !== 'string' || !value.trim()) fail(location, 'expected a nonempty string');
}

function id(value, location) {
  text(value, location);
  if (!ID.test(value)) fail(location, 'start with a letter; use only letters, digits, underscores, or hyphens');
}

function array(value, location, required = false) {
  if (!Array.isArray(value)) fail(location, 'expected an array');
  if (required && !value.length) fail(location, 'include at least one item');
}

/** Validate the portable display schema; return the input unchanged. */
export function validateData(data) {
  object(data, 'data', ['title', 'description', 'eyebrow', 'footer', 'plans']);
  text(data.title, 'data.title');
  text(data.description, 'data.description');
  text(data.eyebrow, 'data.eyebrow', true);
  text(data.footer, 'data.footer', true);
  array(data.plans, 'data.plans', true);
  const planIds = new Set();
  data.plans.forEach((plan, planIndex) => {
    const p = `data.plans[${planIndex}]`;
    object(plan, p, ['id', 'title', 'summary', 'status', 'steps']);
    id(plan.id, `${p}.id`);
    if (planIds.has(plan.id)) fail(`${p}.id`, `duplicate plan ID "${plan.id}"`);
    planIds.add(plan.id);
    text(plan.title, `${p}.title`);
    text(plan.summary, `${p}.summary`);
    text(plan.status, `${p}.status`, true);
    array(plan.steps, `${p}.steps`, true);
    const stepIds = new Set();
    plan.steps.forEach((step, stepIndex) => {
      const s = `${p}.steps[${stepIndex}]`;
      object(step, s, ['id', 'title', 'description', 'checkpoint', 'artifact', 'related', 'resources']);
      id(step.id, `${s}.id`);
      if (stepIds.has(step.id)) fail(`${s}.id`, `duplicate step ID "${step.id}" in plan "${plan.id}"`);
      stepIds.add(step.id);
      text(step.title, `${s}.title`);
      text(step.description, `${s}.description`);
      text(step.checkpoint, `${s}.checkpoint`, true);
      object(step.artifact, `${s}.artifact`, ['title', 'language', 'code', 'note']);
      text(step.artifact.title, `${s}.artifact.title`);
      text(step.artifact.language, `${s}.artifact.language`, true);
      text(step.artifact.code, `${s}.artifact.code`);
      text(step.artifact.note, `${s}.artifact.note`, true);
      if (step.related !== undefined) {
        array(step.related, `${s}.related`);
        const relations = new Set();
        step.related.forEach((target, relationIndex) => {
          const r = `${s}.related[${relationIndex}]`;
          id(target, r);
          if (target === step.id) fail(r, `step "${step.id}" cannot reference itself`);
          if (relations.has(target)) fail(r, `duplicate related step "${target}"`);
          relations.add(target);
        });
      }
      if (step.resources !== undefined) {
        array(step.resources, `${s}.resources`);
        step.resources.forEach((resource, resourceIndex) => {
          const r = `${s}.resources[${resourceIndex}]`;
          object(resource, r, ['label', 'url']);
          text(resource.label, `${r}.label`);
          text(resource.url, `${r}.url`);
          let url;
          try { url = new URL(resource.url); } catch { fail(`${r}.url`, 'expected an absolute http:// or https:// URL'); }
          if (!/^https?:\/\//i.test(resource.url) || !['http:', 'https:'].includes(url.protocol)) {
            fail(`${r}.url`, 'only absolute http:// and https:// URLs are allowed');
          }
          if (url.username || url.password) fail(`${r}.url`, 'credentials in resource URLs are not allowed');
          if (/[\u0000-\u0020\u007f]/.test(resource.url)) fail(`${r}.url`, 'encode spaces and remove control characters');
        });
      }
    });
    plan.steps.forEach((step, stepIndex) => {
      (step.related ?? []).forEach((target, relationIndex) => {
        if (!stepIds.has(target)) {
          fail(`${p}.steps[${stepIndex}].related[${relationIndex}]`, `unknown step "${target}" in plan "${plan.id}"; available: ${[...stepIds].join(', ')}`);
        }
      });
    });
  });
  return data;
}

export async function readData(filename) {
  let contents;
  try { contents = await readFile(filename, 'utf8'); }
  catch (error) { throw new Error(`Cannot read data file "${filename}": ${error.message}`); }
  let data;
  try { data = JSON.parse(contents.replace(/^\uFEFF/, '')); }
  catch (error) { throw new Error(`Invalid JSON in "${filename}": ${error.message}`); }
  return validateData(data);
}

async function main(args) {
  if (args.includes('--help') || args.includes('-h')) {
    console.log('Usage: node scripts/validate.mjs <data.json>\nValidate explanation/artifact pairs and within-plan connections.');
    return;
  }
  if (args.length !== 1 || args[0].startsWith('-')) throw new Error('Usage: node scripts/validate.mjs <data.json>');
  const data = await readData(path.resolve(args[0]));
  console.log(`Valid: ${data.plans.length} plan(s), ${data.plans.reduce((n, plan) => n + plan.steps.length, 0)} pair(s).`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch(error => { console.error(`Validation failed: ${error.message}`); process.exitCode = 1; });
}
