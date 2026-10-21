import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const jsx = (type, props) => ({ type, props });
const exports = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../src/components/OrderComparisonCard.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText, { exports, require: () => ({ jsx, jsxs: jsx }) });
const flatten = n => Array.isArray(n) ? n.flatMap(flatten) : n?.props ? [n, ...flatten(n.props.children)] : [];
const p = (period, total_amount) => ({ period, total_amount, total_orders: 2, start: `${period}-01`, end_exclusive: '2026-10-01' });
const report = { status: 'ready', model_called: false, source: 'Synthetic acceptance', currency: 'USD', generated_at: '2026-10-18T12:00:00Z',
  comparison: { previous: p('2026-08', 60), current: p('2026-09', 120), amount_delta: 60, change_pct: 100, orders_delta: 0 },
  provenance: { imported_at: '2026-10-18T10:00:00Z', coverage_start: '2026-08-01T00:00:00Z', coverage_end: '2026-09-02T00:00:00Z' },
  issues: [{ code: 'snapshot_only', message: 'Snapshot, not live sync' }] };
for (const english of [false, true]) {
  test(`${english ? 'en' : 'zh'} evidence card shows exact amounts, scope, native disclosure and no AI claim`, () => {
    const tree = exports.OrderComparisonCard({ report, fallback: 'fallback', english });
    const output = JSON.stringify(tree);
    for (const text of ['USD', '60.00', '120.00', '+100.00%', 'Synthetic acceptance', 'Snapshot, not live sync']) assert.ok(output.includes(text), text);
    const nodes = flatten(tree);
    assert.equal(nodes.filter(n => n.type === 'details').length, 1);
    assert.ok(nodes.some(n => n.type === 'caption'));
    assert.ok(nodes.some(n => n.type === 'th' && n.props.scope === 'row'));
    assert.match(output, english ? /not net revenue or profit/ : /不是净收入或利润/);
  });
}
test('zero baseline never formats null as 0% or Infinity', () => {
  const output = JSON.stringify(exports.OrderComparisonCard({ report: { ...report, comparison: { ...report.comparison, change_pct: null } }, fallback: '', english: false }));
  assert.match(output, /基期为零/);
  assert.doesNotMatch(output, /Infinity|NaN/);
});
test('unavailable data has recovery link, not invented totals', () => {
  const nodes = flatten(exports.OrderComparisonCard({ report: { ...report, status: 'unavailable', comparison: null }, fallback: '', english: true }));
  assert.ok(nodes.some(n => n.type === 'a' && n.props.href === '/data'));
  assert.ok(!nodes.some(n => n.type === 'table'));
});
test('malformed server report falls back without crashing', () => {
  for (const value of [null, {}, { ...report, comparison: {} }, { ...report, issues: null }, { ...report, status: 'unavailable', comparison: {} }, { ...report, provenance: { imported_at: {} } }]) {
    assert.equal(exports.OrderComparisonCard({ report: value, fallback: 'Safe text', english: false }).props.children, 'Safe text');
  }
});
