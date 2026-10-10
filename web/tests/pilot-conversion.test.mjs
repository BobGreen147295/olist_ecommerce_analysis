import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), 'utf8');
const compile = (source) => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const jsx = (type, props) => ({ type, props });
function nodes(root) {
  if (Array.isArray(root)) return root.flatMap(nodes);
  return root?.props ? [root, ...nodes(root.props.children)] : [];
}

test('public pilot, sample report and privacy omit demo identity; admin stays protected', () => {
  for (const pathname of ['/pilot', '/pilot/sample-report', '/privacy', '/pilot/applications']) {
    const pageModule = { exports: {} };
    vm.runInNewContext(compile(read('../src/components/AppShell.tsx')) + ';module.exports.renderShell=AppShellContent;', {
      module: pageModule, exports: pageModule.exports,
      require(name) {
        if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
        if (name === 'react') return { useState: (value) => [value, () => {}] };
        if (name === 'next/navigation') return { usePathname: () => pathname };
        if (name === 'next/link') return { default: 'a' };
        if (name === './I18n') return { useI18n: () => ({ t: (key) => key }) };
        return {};
      },
    });
    const output = pageModule.exports.renderShell({ children: 'Public content' });
    if (pathname === '/pilot/applications') {
      assert.match(JSON.stringify(output), /Northstar Commerce/);
    } else {
      assert.doesNotMatch(JSON.stringify(output), /Northstar|Nora Kim|workspace-switcher|copilot-panel/);
      assert.ok(nodes(output).some((node) => node.props.href === '/pilot#apply'));
    }
  }
});

function form(api, fetch) {
  const pageModule = { exports: {} };
  const changes = [];
  let index = 0;
  vm.runInNewContext(compile(read('../src/app/pilot/PilotApplicationForm.tsx')), {
    module: pageModule, exports: pageModule.exports,
    process: { env: { NEXT_PUBLIC_REVENUEOPS_API_URL: api, NEXT_PUBLIC_REVENUEOPS_CONTACT_EMAIL: 'founder@example.com' } },
    FormData: class { entries() { return [['contact_email', 'operator@example.com']]; } }, fetch,
    require(name) {
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
      if (name === 'react') return { useState: (value) => { const key = index++; return [value, (next) => changes.push([key, next])]; } };
      if (name === 'next/link') return { default: 'a' };
      throw new Error(name);
    },
  });
  return { changes, output: nodes(pageModule.exports.PilotApplicationForm()) };
}

test('backup email is always visible without configured API and does not send', async () => {
  const { output, changes } = form(undefined, () => assert.fail('must not request unconfigured API'));
  const email = output.find((node) => node.type === 'a');
  assert.match(email.props.href, /^mailto:founder@example.com\?subject=/);
  assert.equal(email.props.children, 'founder@example.com');
  await output.find((node) => node.type === 'form').props.onSubmit({ preventDefault() {}, currentTarget: {} });
  assert.match(changes[0][1], /备用邮箱/);
});

test('network and rejected submissions retain form and point to backup email', async () => {
  for (const fetch of [async () => { throw new Error('offline'); }, async () => ({ ok: false, json: async () => ({}) })]) {
    const { output, changes } = form('https://example.invalid', fetch);
    await output.find((node) => node.type === 'form').props.onSubmit({ preventDefault() {}, currentTarget: { reset() { assert.fail('failed form must not reset'); } } });
    assert.ok(changes.some(([key, text]) => key === 0 && /备用邮箱/.test(text)));
    assert.deepEqual(changes.at(-1), [1, false]);
  }
});

test('home introduction and workspace both retain bottom application exits', () => {
  assert.match(read('../src/components/LeadInExperience.tsx'), /className="demo-conversion"[\s\S]*href="\/pilot#apply"/);
  assert.match(read('../src/app/page.tsx'), /className="card homepage-conversion"[\s\S]*href="\/pilot#apply"/);
});
