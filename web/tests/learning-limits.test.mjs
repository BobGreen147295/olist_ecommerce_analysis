import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as React from 'react';
import * as jsxRuntime from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';

function renderResult(locale, warnings) {
  const source = fs.readFileSync(new URL('../src/app/learning/page.tsx', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  const task = { task_id: 'synthetic', status: 'completed', result: {
    conversion_uplift_pp: 0, incremental_orders: 0, incremental_revenue: 0, roi: null,
    currency: 'USD', attribution_window_days: 7, revenue_net_of_refunds: true, warnings,
  } };
  let stateIndex = 0;
  const exports = {};
  const hooks = { useCallback: (fn) => fn, useEffect: () => {}, useState: (initial) => {
    const value = stateIndex === 0 ? task : stateIndex === 1 ? 'ready' : initial;
    stateIndex += 1;
    return [value, () => {}];
  } };
  const require = (name) => {
    if (name === 'react') return hooks;
    if (name === 'react/jsx-runtime') return jsxRuntime;
    if (name === '@/components/I18n') return { useI18n: () => ({ locale, t: (key) => key }) };
    if (name === '@/components/Ui') return { PageHeading: () => null, StatusBadge: ({ children }) => React.createElement('span', {}, children) };
    if (name === 'next/link') return ({ children, href }) => React.createElement('a', { href }, children);
    if (name.endsWith('.css')) return {};
    throw new Error(`Unexpected dependency: ${name}`);
  };
  vm.runInNewContext(code, { exports, require, process: { env: {} } });
  return renderToStaticMarkup(React.createElement(exports.default));
}

test('completed small-sample results visibly show the warning in both languages', () => {
  assert.match(renderResult('zh', ['synthetic warning']), /至少一组少于 30 人/);
  assert.match(renderResult('en', ['synthetic warning']), /At least one group has fewer than 30 people/);
});

test('normal results retain ROI limitations without claiming a small sample', () => {
  const html = renderResult('en', []);
  assert.match(html, /Revenue ROI is not profit ROI/);
  assert.doesNotMatch(html, /At least one group has fewer than 30 people/);
});
