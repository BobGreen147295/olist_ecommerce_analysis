import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function setup(overrides = {}) {
  const source = fs.readFileSync(new URL('../src/app/data/page.tsx', import.meta.url), 'utf8');
  const tree = ts.createSourceFile('page.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let handler;
  function visit(node) {
    if (ts.isFunctionDeclaration(node) && node.name?.text === 'loginForConnection') handler = node.getText(tree);
    ts.forEachChild(node, visit);
  }
  visit(tree);
  assert.ok(handler, 'actual page login handler exists');
  const state = { error: '', busy: [], token: '', password: 'synthetic-password', stored: null };
  const context = {
    isLoggingIn: false, API_BASE_URL: 'https://example.invalid', username: 'synthetic-user', password: state.password,
    tx: (zh) => zh,
    setConnectionError: (value) => { state.error = value; },
    setIsLoggingIn: (value) => { state.busy.push(value); },
    setAccessToken: (value) => { state.token = value; },
    setPassword: (value) => { state.password = value; },
    sessionStorage: { setItem: (key, value) => { state.stored = { key, value }; } },
    fetch: async () => ({ ok: true, json: async () => ({ access_token: 'synthetic-token' }) }),
    loadShopifyConnection: async () => {}, ...overrides,
  };
  return { state, login: vm.runInNewContext(`(${handler})`, context) };
}

test('successful sign-in stores session, clears password and ends loading', async () => {
  const { state, login } = setup();
  await login();
  assert.deepEqual(state.stored, { key: 'revenueops_access_token', value: 'synthetic-token' });
  assert.equal(state.token, 'synthetic-token');
  assert.equal(state.password, '');
  assert.deepEqual(state.busy, [true, false]);
  assert.equal(state.error, '');
});
test('network and storage failures are visible and release loading', async () => {
  for (const overrides of [
    { fetch: async () => { throw new Error('network'); } },
    { sessionStorage: { setItem: () => { throw new Error('storage'); } } },
  ]) {
    const { state, login } = setup(overrides);
    await login();
    assert.match(state.error, /无法完成登录/);
    assert.equal(state.token, '');
    assert.deepEqual(state.busy, [true, false]);
  }
});
test('rejected credentials never create a session', async () => {
  const { state, login } = setup({ fetch: async () => ({ ok: false, json: async () => ({ error: 'Invalid credentials' }) }) });
  await login();
  assert.equal(state.error, 'Invalid credentials');
  assert.equal(state.stored, null);
  assert.deepEqual(state.busy, [true, false]);
});
test('store-status failure does not discard a successful login', async () => {
  const { state, login } = setup({ loadShopifyConnection: async () => { throw new Error('status unavailable'); } });
  await login();
  assert.equal(state.token, 'synthetic-token');
  assert.match(state.error, /已登录/);
  assert.deepEqual(state.busy, [true, false]);
});
test('missing configuration and busy state do not send requests', async () => {
  for (const overrides of [{ API_BASE_URL: undefined }, { isLoggingIn: true }]) {
    const { state, login } = setup({ ...overrides, fetch: () => assert.fail('unexpected request') });
    await login();
    assert.equal(state.stored, null);
    assert.equal(state.busy.length, 0);
  }
});
