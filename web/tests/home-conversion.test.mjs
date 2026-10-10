import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = (path) => fs.readFileSync(new URL(path, import.meta.url), 'utf8');
const translations = source('../src/components/I18n.tsx');
const tree = ts.createSourceFile('I18n.tsx', translations, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let messages;
ts.forEachChild(tree, (node) => {
  if (!ts.isVariableStatement(node)) return;
  for (const declaration of node.declarationList.declarations) {
    if (declaration.name.getText(tree) === 'messages') {
      messages = vm.runInNewContext(`(${declaration.initializer.expression.getText(tree)})`);
    }
  }
});

function render(locale, onEnter) {
  const pageModule = { exports: {} };
  const element = (type, props) => ({ type, props });
  vm.runInNewContext(ts.transpileModule(source('../src/components/LeadInExperience.tsx'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, {
    module: pageModule, exports: pageModule.exports,
    window: { matchMedia: () => ({ matches: true }) },
    require(name) {
      if (name === 'react/jsx-runtime') return { jsx: element, jsxs: element };
      if (name === 'react') return { useState: (value) => [value, () => {}], useEffect: () => {} };
      if (name === 'next/link') return { default: 'a' };
      if (name === './I18n') return { useI18n: () => ({ locale, setLocale: () => {}, t: (key) => messages[locale][key] }) };
      if (name === '@phosphor-icons/react') return {};
      throw new Error(`Unexpected import ${name}`);
    },
  });
  const nodes = [];
  function visit(node) {
    if (Array.isArray(node)) return node.forEach(visit);
    if (!node?.props) return;
    nodes.push(node);
    visit(node.props.children);
  }
  visit(pageModule.exports.LeadInExperience({ onEnter }));
  return nodes;
}

for (const locale of ['zh-CN', 'en']) {
  test(`${locale}: first-screen application link and interactive demo are distinct`, () => {
    let entered = false;
    const nodes = render(locale, () => { entered = true; });
    const apply = nodes.find((node) => node.props.className === 'lead-in-cta');
    assert.equal(apply.props.href, '/pilot#apply');
    assert.equal(apply.props.children, messages[locale].applyStore);
    assert.equal(apply.props.onClick, undefined, 'application must not dismiss into the demo');
    assert.ok(nodes.some((node) => node.props.id === apply.props['aria-describedby']));
    const demo = nodes.find((node) => node.props.className === 'lead-in-demo');
    demo.props.onClick();
    assert.equal(entered, true, 'demo keeps existing reduced-motion entry');
  });
}

test('application route has a public form anchor and workspace retains its entry', () => {
  assert.match(source('../src/app/pilot/PilotApplicationForm.tsx'), /id="apply"/);
  assert.match(source('../src/app/pilot/page.tsx'), /<PilotApplicationForm\s*\/>/);
  assert.match(source('../src/app/page.tsx'), /href="\/pilot#apply"/);
});
