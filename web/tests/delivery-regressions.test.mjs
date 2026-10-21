import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const read = path => fs.readFileSync(new URL(path, import.meta.url), 'utf8');
const compile = source => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const jsx = (type, props) => ({ type, props });

function mount(path) {
  const source = read(path);
  const changes = [];
  const initial = [];
  const effects = [];
  const requests = [];
  const removed = [];
  let token = 'merchant-a-session';
  const exports = {};
  vm.runInNewContext(compile(source), {
    exports, window: { location: { search: '' } }, URLSearchParams, AbortSignal,
    process: { env: { NEXT_PUBLIC_REVENUEOPS_API_URL: 'https://example.invalid' } },
    localStorage: { getItem() { assert.fail('No browser-wide merchant cache may be read'); }, removeItem(key) { removed.push(key); } },
    sessionStorage: { getItem: () => token, removeItem: () => { token = null; } },
    fetch: url => new Promise(resolve => requests.push({ url, resolve })),
    require(name) {
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
      if (name === 'react') return {
        useCallback: fn => fn,
        useEffect: effect => effects.push(effect),
        useState(value) { const index = initial.length; const resolved = typeof value === 'function' ? value() : value; initial.push(resolved); return [resolved, next => changes.push({ index, value: next })]; },
      };
      if (name === '@/components/I18n') return { useI18n: () => ({ locale: 'en', t: key => key }) };
      if (name === '@/lib/demo-data') return { opportunities: [], workspace: {}, connectors: [] };
      if (name === '@/lib/task-workflow') { const helpers = {}; vm.runInNewContext(compile(read('../src/lib/task-workflow.ts')), {exports:helpers}); return helpers; }
      if (name === '@/components/TaskPicker') return { TaskPicker: 'select' };
      if (name === 'next/link') return { default: 'a' };
      if (name.endsWith('.css')) return { default: {} };
      return {};
    },
  });
  exports.default();
  return { changes, initial, effects, requests, removed, switchAccount: () => { token = 'merchant-b-session'; } };
}

const cachePages = ['../src/app/page.tsx', '../src/app/data/page.tsx', '../src/app/opportunities/page.tsx'];
test('data page discloses manual sync and distinguishes order adjustments from profit', () => {
  const source = read('../src/app/data/page.tsx');
  assert.match(source, /手动同步（本版）/);
  assert.match(source, /Manual sync \(current version\)/);
  assert.match(source, /currentTotalPriceSet/);
  assert.match(source, /不等同 Shopify 报表的净销售口径/);
  assert.match(source, /不能计算净利润/);
});
for (const path of cachePages) {
  test(`${path}: starts without cached merchant data and removes the legacy key`, () => {
    const page = mount(path);
    page.effects.forEach(effect => effect());
    assert.ok(page.removed.includes('revenueops_shopify_summary_v1'));
    assert.doesNotMatch(read(path), /localStorage\.(?:getItem|setItem)\(SHOPIFY_SUMMARY_CACHE_KEY/);
  });
}

for (const path of ['../src/app/page.tsx', '../src/app/opportunities/page.tsx', '../src/app/learning/page.tsx']) {
  for (const stop of ['switch', 'unmount']) {
    test(`${path}: ${stop} discards delayed account data`, async () => {
      const page = mount(path);
      const cleanup = page.effects[0]();
      if (stop === 'switch') page.switchAccount(); else cleanup();
      for (const request of page.requests) request.resolve({ ok: true, status: 200, json: async () => ({ connection: { summary: { orders: 123 } }, signal: { state: 'ready' }, tasks: [{ source_diagnosis: { source: 'consented_reactivation_aggregate' }, execution: { mode: 'manual_handoff' }, status: 'confirmed' }] }) });
      await new Promise(resolve => setImmediate(resolve));
      assert.equal(page.changes.length, 0);
    });
  }
}

function submit(overrides = {}) {
  const tree = ts.createSourceFile('page.tsx', read('../src/app/learning/page.tsx'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let handler;
  function visit(node) { if (ts.isFunctionDeclaration(node) && node.name?.text === 'submitResult') handler = node.getText(tree); ts.forEachChild(node, visit); }
  visit(tree);
  const state = { saving: false, messages: [], task: null, screen: '', calls: 0, token: 'merchant-a-session' };
  const context = {
    task: { task_id: 'synthetic-task' }, API_BASE_URL: 'https://example.invalid', saving: false, canSubmit: true, english: false, tx: zh => zh,
    form: { treatment_users: '100', treatment_orders: '20', treatment_revenue: '2000', control_users: '100', control_orders: '10', control_revenue: '1000', cost: '200', currency: 'USD' },
    sessionStorage: { getItem: () => state.token },
    setSaving: value => { state.saving = value; }, setMessage: value => state.messages.push(value),
    setTask: value => { state.task = value; }, setState: value => { state.screen = value; },
    setTasks: () => {},
    fetch: async () => { state.calls++; return { status: 200, ok: true, json: async () => ({ task: { result: { roi: 4 } } }) }; }, ...overrides,
  };
  return { state, send: vm.runInNewContext(compile(`const handler=${handler}; handler;`), context) };
}

test('observed results: unknown numbers do not become zeros and no request is made', async () => {
  const { state, send } = submit({ form: { treatment_users: '', treatment_orders: '', treatment_revenue: '', control_users: '', control_orders: '', control_revenue: '', cost: '' } });
  await send(); assert.equal(state.calls, 0); assert.match(state.messages.at(-1), /未知不能当作 0/);
});
test('observed results: network failure retains inputs, explains uncertainty and releases saving', async () => {
  const { state, send } = submit({ fetch: async () => { throw new Error('offline'); } });
  await send(); assert.equal(state.saving, false); assert.equal(state.task, null); assert.match(state.messages.at(-1), /未能确认结果已保存/);
});
test('observed results: expired session routes to sign-in, not a completed result', async () => {
  const { state, send } = submit({ fetch: async () => ({ status: 401, ok: false, json: async () => ({}) }) });
  await send(); assert.equal(state.screen, 'signed-out'); assert.equal(state.task, null); assert.equal(state.saving, false);
});
test('observed results: failed and malformed success responses never mark completion', async () => {
  for (const ok of [false, true]) {
    const { state, send } = submit({ fetch: async () => ({ status: ok ? 200 : 503, ok, json: async () => ({}) }) });
    await send(); assert.equal(state.task, null); assert.match(state.messages.at(-1), /失败/); assert.equal(state.saving, false);
  }
});
test('observed results: valid success ends saving and records the returned task', async () => {
  const { state, send } = submit(); await send(); assert.equal(state.task.result.roi, 4); assert.equal(state.saving, false);
});
test('observed results: switched account discards a response already in flight', async () => {
  let resolve;
  const { state, send } = submit({ fetch: () => new Promise(done => { resolve = done; }) });
  const pending = send(); state.token = 'merchant-b-session'; resolve({ status: 200, ok: true, json: async () => ({ task: { result: { roi: 4 } } }) });
  await pending; assert.equal(state.task, null); assert.equal(state.saving, false);
});
test('data connection: delayed previous-session status cannot update the current account', async () => {
  const tree = ts.createSourceFile('page.tsx', read('../src/app/data/page.tsx'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let handler;
  function visit(node) { if (ts.isCallExpression(node) && node.expression.getText(tree) === 'useCallback' && node.arguments[0]?.getText(tree).includes('async (token: string)')) handler = node.arguments[0].getText(tree); ts.forEachChild(node, visit); }
  visit(tree); assert.ok(handler);
  let resolve; let token = 'merchant-a-session'; let updated = false;
  const load = vm.runInNewContext(compile(`const handler=${handler}; handler;`), { AbortSignal, API_BASE_URL: 'https://example.invalid', sessionStorage: { getItem: () => token }, fetch: () => new Promise(done => { resolve = done; }), rememberShopifyConnection: () => { updated = true; } });
  const pending = load(token); token = 'merchant-b-session'; resolve({ status: 200, ok: true, json: async () => ({ connection: { summary: {} } }) });
  await pending; assert.equal(updated, false);
});
