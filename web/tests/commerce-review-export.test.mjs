import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const exports = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../src/lib/commerce-review.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports });
test('review export preserves fixed evidence, original decision, adopted check and observation without inferred profit', () => {
  const review = { snapshot: { id: 'synthetic-snapshot', report: { source: 'SYNTHETIC ACCEPTANCE', currency: 'USD', generated_at: '2026-10-21T12:00:00Z', rows: [{ period: '2026-09', total_orders: 2, total_amount: 120 }], issues: [{ message: 'Snapshot only' }] } },
    input: { note: 'Original judgment', nextAction: 'Original check', dueOn: '2026-11-01' }, outcome: 'Synthetic observation',
    adoptedAction: { taskId: 'synthetic-task', task: 'Adopted check', reason: 'Check coverage', measure: 'Stop if incomplete', dueOn: '2026-11-02', model: 'test-model', generatedAt: '2026-10-21T12:01:00Z' } };
  const text = exports.reviewMarkdown(review);
  for (const expected of ['synthetic-snapshot', 'SYNTHETIC ACCEPTANCE', '120 USD', 'Original judgment', 'Original check', 'Adopted check', 'Stop if incomplete', 'Synthetic observation', 'Snapshot only', 'not net revenue or profit']) assert.ok(text.includes(expected), expected);
  assert.ok(!text.includes('undefined'));
});
