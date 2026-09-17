// Validate the actual saved note with the same locked KaTeX dependency as UI.
// The migration is inline-math only; no arbitrary Markdown math inference runs.
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const run = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(run, '../../../..');
const require = createRequire(path.join(root, 'automation/frontend/package.json'));
const katex = require('katex');
const sid = 'RS-a8f812d7-d8f9-4862-8e8f-932cc5649d3b';
const md = readFileSync(path.join(root, 'context/reading-notes', sid, 'current.md'), 'utf8');
const snapshot = JSON.parse(readFileSync(path.join(root, 'context/reading-notes', sid, 'current.json'), 'utf8'));
const formulas = [...md.matchAll(/\$([^$\n]+)\$/g)].map(match => match[1]);
if (snapshot.metadata.revision !== 9 || formulas.length < 15) throw Error('实际修订/公式数量未达到预期');
for (const formula of formulas) katex.renderToString(formula, {throwOnError: true, trust: false});
const result = {session_id: sid, revision: 9, formula_count: formulas.length,
  fixed_references: snapshot.value.references.length, katex: 'passed',
  scope: 'actual saved note syntax rendering only; no scientific recomputation'};
writeFileSync(path.join(run, 'note-math-validation.json'), JSON.stringify(result, null, 2)+'\n');
console.log(JSON.stringify(result));
