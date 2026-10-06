import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function setup({ token = 'synthetic-token', previous = token, status = 200, failure = false, switchDuringRequest = false } = {}) {
  const source = fs.readFileSync(new URL('../src/components/CopilotPanel.tsx', import.meta.url), 'utf8');
  const tree = ts.createSourceFile('panel.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let handler;
  function visit(node) {
    if (ts.isFunctionDeclaration(node) && node.name?.text === 'send') handler = node.getText(tree);
    ts.forEachChild(node, visit);
  }
  visit(tree);
  assert.ok(handler);
  const state = { token, messages: [{ role: 'assistant', content: 'previous-account-answer' }], calls: [], loading: false };
  const context = {
    draft: 'sales trend', isLoading: false, API_BASE_URL: 'https://example.invalid', messages: state.messages,
    english: false, tx: (zh) => zh, sessionToken: { current: previous },
    sessionStorage: { getItem: () => state.token, removeItem: () => { state.token = null; } },
    setMessages: (update) => { state.messages = update(state.messages); }, setDraft: () => {},
    setAgentMode: () => {}, setIsLoading: (value) => { state.loading = value; },
    fetch: async (url, options) => {
      state.calls.push({ url, options });
      if (switchDuringRequest) state.token = 'different-session';
      if (failure) throw new Error('unavailable');
      return { status, ok: status === 200, json: async () => ({ answer: 'new-answer' }) };
    },
  };
  const javascript = ts.transpileModule(`const send = ${handler}; send;`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  return { state, send: vm.runInNewContext(javascript, context) };
}

test('not signed in: no request and no previous-session answer', async () => {
  const { state, send } = setup({ token: null, previous: 'old-session' });
  await send({ preventDefault() {} });
  assert.equal(state.calls.length, 0);
  assert.match(state.messages.at(-1).content, /请先/);
  assert.ok(!state.messages.some((item) => item.content === 'previous-account-answer'));
});

test('authenticated request carries bearer and new session cannot reuse history', async () => {
  const { state, send } = setup({ previous: 'old-session' });
  await send({ preventDefault() {} });
  assert.equal(state.calls[0].options.headers.Authorization, 'Bearer synthetic-token');
  assert.deepEqual(JSON.parse(state.calls[0].options.body).history, []);
  assert.equal(state.messages.at(-1).content, 'new-answer');
  assert.equal(state.loading, false);
});

test('401 clears expired session; 429 is explained without demo reasoning', async () => {
  for (const status of [401, 429]) {
    const { state, send } = setup({ status });
    await send({ preventDefault() {} });
    assert.match(state.messages.at(-1).content, status === 401 ? /登录已失效/ : /调用已达上限/);
    assert.equal(state.token, status === 401 ? null : 'synthetic-token');
    assert.equal(state.loading, false);
  }
});

test('failure does not substitute synthetic advice for real-account response', async () => {
  const { state, send } = setup({ failure: true });
  await send({ preventDefault() {} });
  assert.match(state.messages.at(-1).content, /没有生成经营结论/);
  assert.equal(state.loading, false);
});

test('account changed during request: old response never appears', async () => {
  const { state, send } = setup({ switchDuringRequest: true });
  await send({ preventDefault() {} });
  assert.ok(!state.messages.some((item) => item.content === 'new-answer'));
  assert.equal(state.loading, false);
});
