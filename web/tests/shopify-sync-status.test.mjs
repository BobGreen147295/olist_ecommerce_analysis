import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const exports = {};
const jsx = (type, props) => ({ type, props });
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../src/components/ShopifySyncStatus.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText, { exports, require: () => ({ jsx, jsxs: jsx }) });
for (const english of [false, true]) {
  test(`${english ? 'en' : 'zh'}: last successful sync and stale/partial/unknown evidence are visible`, () => {
    const base = { last_synced_at: '2026-10-01T00:00:00Z', summary: {} };
    for (const [state, expected] of [['stale_data', /24/], ['development_store', /开发店|Development/], ['trend_required', /尚未同步|not been synced/], ['insufficient_data', /未通过|failed/], ['sync_required', /可信|trusted/], ['unknown', /尚未核实|unverified/]]) {
      const output = JSON.stringify(exports.ShopifySyncStatus({ english, connection: { ...base, opportunity_readiness: { state } } }));
      assert.match(output, expected);
      assert.ok(output.includes('2026-10-01T00:00:00.000Z'));
      assert.match(output, /不自动补同步|manual updates only/);
    }
    const partial = JSON.stringify(exports.ShopifySyncStatus({ english, connection: { ...base, summary: { order_trend: { truncated: true } } } }));
    assert.match(partial, /截断|truncated/);
    const noTime = JSON.stringify(exports.ShopifySyncStatus({ english, connection: { ...base, last_synced_at: 'invalid' } }));
    assert.match(noTime, /尚无可信记录|No trusted record/);
  });
}
