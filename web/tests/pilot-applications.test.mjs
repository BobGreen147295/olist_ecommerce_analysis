import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

// Exercise the page's effect with synthetic responses, without a server or credentials.
function mount({ token = 'synthetic-token', api = 'https://example.invalid', fetch } = {}) {
  const state = [];
  let effect;
  const pageModule = { exports: {} };
  const source = fs.readFileSync(new URL('../src/app/pilot/applications/page.tsx', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  vm.runInNewContext(code, {
    module: pageModule, exports: pageModule.exports, AbortController, Error,
    process: { env: { NEXT_PUBLIC_REVENUEOPS_API_URL: api } },
    sessionStorage: { getItem: () => token }, fetch,
    require: (name) => {
      if (name === 'react') return {
        useEffect: (callback) => { effect = callback; },
        useState: (initial) => {
          const index = state.length;
          state.push(initial);
          return [initial, (value) => { state[index] = value; }];
        },
      };
      if (name === 'react/jsx-runtime') return { jsx: () => null, jsxs: () => null };
      if (name === 'next/link') return { default: () => null };
      throw new Error(`Unexpected import: ${name}`);
    },
  });
  pageModule.exports.default();
  return { state, cleanup: effect() };
}
const flush = () => new Promise((resolve) => setImmediate(resolve));
const response = (applications) => ({ ok: true, json: async () => ({ applications }) });

test('missing token or API never requests application data', async () => {
  for (const options of [{ token: null }, { api: null }]) {
    const page = mount({ ...options, fetch: () => assert.fail('unexpected request') });
    await flush();
    assert.match(page.state[1], /管理员账号登录/);
    page.cleanup();
  }
});
test('empty and populated responses display the appropriate state', async () => {
  for (const items of [[], [{ application_id: 'synthetic' }]]) {
    const page = mount({ fetch: async (_url, options) => {
      assert.equal(options.headers.Authorization, 'Bearer synthetic-token');
      return response(items);
    } });
    await flush();
    assert.equal(page.state[0].length, items.length);
    assert.equal(page.state[1], items.length ? '' : '目前还没有试点申请。');
    page.cleanup();
  }
});
test('API failure is shown without returning application data', async () => {
  const page = mount({ fetch: async () => ({ ok: false, json: async () => ({ error: 'Access denied' }) }) });
  await flush();
  assert.equal(page.state[1], 'Access denied');
  assert.equal(page.state[0].length, 0);
  page.cleanup();
});
test('unmount aborts and ignores late success or failure', async () => {
  for (const fails of [false, true]) {
    let finish;
    let signal;
    const page = mount({ fetch: (_url, options) => {
      signal = options.signal;
      return new Promise((resolve, reject) => { finish = () => fails ? reject(new Error('Late error')) : resolve(response([{ application_id: 'late' }])); });
    } });
    page.cleanup();
    assert.equal(signal.aborted, true);
    finish();
    await flush();
    assert.equal(page.state[0].length, 0);
    assert.equal(page.state[1], '正在读取申请…');
  }
});
