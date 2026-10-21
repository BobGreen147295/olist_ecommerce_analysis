import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const helpers = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../src/lib/task-workflow.ts', import.meta.url), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText, {exports:helpers});
test('multiple tasks require selection; requested old task never falls back to newest', () => {
  const tasks = [{task_id:'new',status:'confirmed'}, {task_id:'old',status:'completed'}];
  assert.equal(helpers.selectTask(tasks,''),null);
  assert.equal(helpers.selectTask(tasks,'old'),tasks[1]);
  assert.equal(helpers.selectTask(tasks,'foreign'),null);
  assert.equal(helpers.selectTask([tasks[0]],'foreign'),null);
  assert.equal(helpers.selectTask([tasks[0]],''),tasks[0]);
});
test('task links carry the selected ID and encode it', () => {
  assert.equal(helpers.taskHref('/learning','old'),'/learning?task=old');
  assert.equal(helpers.taskHref('/campaigns','a&b'),'/campaigns?task=a%26b');
});
test('observation deadline uses explicit timezone and approved integer days', () => {
  assert.equal(helpers.observationEnd({execution:{started_at:'2026-01-01T00:00:00+00:00'},attribution_window_days:14}),'2026-01-15T00:00:00.000Z');
  for (const started of [undefined,'bad','2026-01-01T00:00:00']) assert.equal(helpers.observationEnd({execution:{started_at:started},attribution_window_days:14}),null);
  for (const days of [0,91,1.5,undefined]) assert.equal(helpers.observationEnd({execution:{started_at:'2026-01-01T00:00:00Z'},attribution_window_days:days}),null);
});
