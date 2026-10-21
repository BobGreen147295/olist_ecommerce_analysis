import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function setup(fetch) {
  const source = fs.readFileSync(new URL('../src/app/data/page.tsx', import.meta.url), 'utf8');
  const tree = ts.createSourceFile('page.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const handlers = [];
  function visit(node) {
    if (ts.isFunctionDeclaration(node) && node.name?.text !== 'DataPage') handlers.push(node.getText(tree));
    ts.forEachChild(node, visit);
  }
  visit(tree);
  const state = { token: 'account-a', connection: { shop_domain: 'synthetic.myshopify.com' }, file: { name: 'safe.csv' } };
  const context = {
    API_BASE_URL: 'https://example.invalid', accessToken: state.token,
    username: 'synthetic', password: 'synthetic-password', registrationCode: 'synthetic-code',
    dataProcessingTermsAccepted: true, shopDomain: 'synthetic.myshopify.com',
    isLoggingIn: false, isSyncing: false, isCsvBusy: false,
    csvFile: state.file, csvPreview: { columns: ['id'] },
    csvMapping: { order_id: 'id', ordered_at: 'date', total_amount: 'total' },
    fetch, AbortSignal, FormData: class { append() {} },
    window: { confirm: () => true, location: { assign: () => assert.fail('unexpected redirect') } },
    sessionStorage: { getItem: () => state.token, removeItem: () => { state.token = ''; }, setItem: (_, token) => { state.token = token; } },
    tx: zh => zh,
    rememberShopifyConnection: value => { state.connection = value; },
    loadShopifyConnection: async () => {},
  };
  for (const [setter, field] of Object.entries({
    setConnectionError: 'error', setCsvMessage: 'message', setIsSyncing: 'syncBusy',
    setIsCsvBusy: 'csvBusy', setIsLoggingIn: 'loginBusy', setAccessToken: 'token',
    setShopifyConnection: 'connection', setCsvPreview: 'preview', setCsvFile: 'file',
    setCsvMapping: 'mapping', setSelected: 'selected', setPassword: 'password', setRegistrationCode: 'code',
  })) context[setter] = value => { state[field] = value; };
  vm.createContext(context);
  vm.runInContext(ts.transpile(handlers.join('\n'), { target: ts.ScriptTarget.ES2022 }), context);
  return { state, context };
}

for (const [name, busy, message] of [
  ['syncShopify', 'syncBusy', 'error'], ['previewCsv', 'csvBusy', 'message'],
  ['importCsv', 'csvBusy', 'message'], ['registerForConnection', 'loginBusy', 'error'],
  ['beginShopifyAuthorization', 'syncBusy', 'error'],
  ['deleteLocalShopifyData', 'syncBusy', 'error'], ['deleteImportedOrderData', 'csvBusy', 'message'],
]) {
  test(`${name}: rejected network is handled, busy released, inputs preserved`, async () => {
    const { state, context } = setup(async () => { throw new TypeError('network unavailable'); });
    await context[name]();
    assert.equal(state[busy], false);
    assert.match(state[message], /网络|未确认|重试/);
    assert.equal(state.file.name, 'safe.csv');
    assert.equal(state.token, 'account-a');
  });
  if (name === 'registerForConnection') continue;
  test(`${name}: old-account success or 401 cannot affect the new account`, async () => {
    for (const status of [200, 401]) {
      let release;
      const app = setup(() => new Promise(resolve => { release = resolve; }));
      const pending = app.context[name]();
      app.state.token = 'account-b';
      release({ status, ok: status === 200, json: async () => ({ connection: { shop_domain: 'account-a' }, source: {}, columns: ['id'] }) });
      await pending;
      assert.equal(app.state.token, 'account-b');
      assert.equal(app.state.connection.shop_domain, 'synthetic.myshopify.com');
      assert.equal(app.state.file.name, 'safe.csv');
    }
  });
}

test('expired sync clears both session and visible store data', async () => {
  const { state, context } = setup(async () => ({ status: 401, ok: false, json: async () => ({}) }));
  await context.syncShopify();
  assert.equal(state.token, '');
  assert.equal(state.connection, null);
  assert.equal(state.syncBusy, false);
});
