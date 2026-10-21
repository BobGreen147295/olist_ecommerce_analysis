import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function setup({ token = 'account-a', changedBefore = false, changedAfter = false, status = 200 } = {}) {
  const source = ts.createSourceFile('reviews.tsx', fs.readFileSync(new URL('../src/app/reviews/page.tsx', import.meta.url), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let request;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(source) === 'request' && ts.isCallExpression(node.initializer)) request = node.initializer.arguments[0].getText(source);
    ts.forEachChild(node, visit);
  }
  visit(source); assert.ok(request);
  const state = { token: changedBefore ? 'account-b' : token, calls: [], sessionChanged: undefined };
  const javascript = ts.transpileModule(`const request = ${request}; request;`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  const run = vm.runInNewContext(javascript, { session: token, api: 'https://merchant.example', sessionKey: 'revenueops_access_token', AbortSignal,
    sessionStorage: { getItem: () => state.token, removeItem: () => { state.token = null; } },
    onSessionChange: next => { state.sessionChanged = next; },
    fetch: async (url, options) => { state.calls.push({ url, options }); if (changedAfter) state.token = 'account-b'; return { status, ok: status === 200, json: async () => ({ reviews: ['private-account-a'], error: 'service unavailable' }) }; },
  });
  return { state, run };
}
test('review requests require the current session, forward only its bearer and never use a caller-selected account', async () => {
  const signedOut = setup({ token: null }); await assert.rejects(signedOut.run(''), /请先登录/); assert.equal(signedOut.state.calls.length, 0);
  const active = setup(); const result = await active.run('');
  assert.equal(active.state.calls[0].url, 'https://merchant.example/v1/commerce');
  assert.equal(active.state.calls[0].options.headers.Authorization, 'Bearer account-a');
  assert.equal(active.state.calls[0].options.headers['X-Commerce-Owner'], undefined);
  assert.equal(result.reviews[0], 'private-account-a');
});
test('account switching before or during a request discards the old private result', async () => {
  for (const option of [{ changedBefore: true }, { changedAfter: true }]) {
    const { state, run } = setup(option); await assert.rejects(run(''), /账户已切换/); assert.equal(state.sessionChanged, 'account-b');
    if (option.changedBefore) assert.equal(state.calls.length, 0);
  }
});
test('401 invalidates the session while a service failure preserves sign-in and exposes no substituted data', async () => {
  const expired = setup({ status: 401 }); await assert.rejects(expired.run(''), /登录已失效/); assert.equal(expired.state.token, null); assert.equal(expired.state.sessionChanged, null);
  const outage = setup({ status: 503 }); await assert.rejects(outage.run(''), /service unavailable/); assert.equal(outage.state.token, 'account-a'); assert.equal(outage.state.sessionChanged, undefined);
});
