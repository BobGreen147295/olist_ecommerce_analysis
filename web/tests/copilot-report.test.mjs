import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const read = path => fs.readFileSync(new URL(path, import.meta.url), 'utf8');
const flatten = node => Array.isArray(node) ? node.flatMap(flatten) : node?.props ? [node, ...flatten(node.props.children)] : [];

function mount(locale = 'zh', configured = true) {
  const state = [], ref = { current: null }, calls = [];
  let cursor = 0;
  const exports = {};
  const jsx = (type, props) => ({ type, props });
  const code = ts.transpileModule(read('../src/components/CopilotPanel.tsx'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(code, { exports, AbortSignal,
    process: { env: configured ? { NEXT_PUBLIC_REVENUEOPS_API_URL: 'https://example.invalid' } : {} },
    sessionStorage: { getItem: () => 'synthetic-token' },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, status: 200, json: async () => ({ answer: 'Synthetic checked totals', mode: 'data' }) };
    },
    require(name) {
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
      if (name === 'react') return { useEffect() {}, useRef: () => ref, useState(value) {
        const i = cursor++;
        if (!(i in state)) state[i] = value;
        return [state[i], next => { state[i] = typeof next === 'function' ? next(state[i]) : next; }];
      } };
      if (name === './I18n') return { useI18n: () => ({ locale }) };
      return { ArrowUp: 'svg', X: 'svg' };
    },
  });
  const render = () => { cursor = 0; return flatten(exports.CopilotPanel({ open: true, onClose() {} })); };
  return { render, calls, state };
}

for (const locale of ['zh', 'en']) {
  test(`${locale}: report shortcut submits the exact server-recognised query with session auth`, async () => {
    const app = mount(locale);
    const button = app.render().find(node => node.type === 'button' && /不用模型|No model/.test(node.props.children));
    assert.ok(button);
    button.props.onClick();
    await app.render().find(node => node.type === 'form').props.onSubmit({ preventDefault() {} });
    assert.equal(app.calls.length, 1);
    assert.equal(app.calls[0].options.headers.Authorization, 'Bearer synthetic-token');
    const query = JSON.parse(app.calls[0].options.body).message;
    assert.ok(read('../../src/agent/order_trend_report.py').includes(`"${query}"`));
    const output = app.render();
    assert.ok(output.some(node => node.props.role === 'status' && /未调用模型|No model call/.test(JSON.stringify(node.props.children))));
    assert.ok(output.some(node => node.props.className === 'copilot-disclaimer' && /不消耗|No model call or AI quota/.test(node.props.children)));
  });
}

test('unconfigured demo does not offer a real-data report shortcut', () => {
  const output = mount('zh', false).render();
  assert.ok(!output.some(node => node.type === 'button' && /不用模型|No model/.test(node.props.children)));
});

test('initial panel never claims that a live model has already answered', () => {
  const output = mount().render();
  const status = output.find(node => node.props.role === 'status');
  assert.match(JSON.stringify(status.props.children), /尚未执行分析/);
  assert.doesNotMatch(JSON.stringify(status.props.children), /服务端 Agent/);
});

test('mobile sidebar closes when the Co-pilot entry opens the chat', () => {
  const state = [];
  let cursor = 0;
  const exports = {};
  const jsx = (type, props) => ({ type, props });
  const source = read('../src/components/AppShell.tsx') + '\nexports.renderShell = AppShellContent;';
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  vm.runInNewContext(code, { exports, require(name) {
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
    if (name === 'react') return { useState(value) {
      const i = cursor++;
      if (!(i in state)) state[i] = value;
      return [state[i], value => { state[i] = value; }];
    } };
    if (name === 'next/navigation') return { usePathname: () => '/data' };
    if (name === './I18n') return { useI18n: () => ({ locale: 'zh-CN', t: key => key }) };
    return new Proxy({}, { get: (_, key) => String(key) });
  } });
  const render = () => { cursor = 0; return flatten(exports.renderShell({ children: 'Synthetic page' })); };
  render().find(node => node.props.className === 'mobile-nav-open').props.onClick();
  assert.equal(state[1], true);
  render().find(node => node.props.className === 'agent-card').props.onClick();
  assert.equal(state[0], true);
  assert.equal(state[1], false);
});
