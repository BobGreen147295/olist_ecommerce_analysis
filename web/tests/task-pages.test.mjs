import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const read = path => fs.readFileSync(new URL(path,import.meta.url),'utf8');
const compile = source => ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const helpers = {}; vm.runInNewContext(compile(read('../src/lib/task-workflow.ts')),{exports:helpers});
const jsx = (type,props) => ({type,props});
const flatten = node => Array.isArray(node)?node.flatMap(flatten):node?.props?[node,...flatten(node.props.children)]:[];
const tasks = ['new','old'].map((id,index)=>({task_id:id,title:`Synthetic ${id}`,status:index?'completed':'confirmed',source_diagnosis:{source:'consented_reactivation_aggregate'},attribution_window_days:14,execution:{mode:'manual_handoff',status:index?'result_recorded':'ready_for_export'}}));

function mount(path, query='', initialOverrides={}, server=false) {
  const state=[]; const effects=[]; let cursor=0;
  const pageModule={exports:{}};
  const context={exports:pageModule.exports,process:{env:{NEXT_PUBLIC_REVENUEOPS_API_URL:'https://example.invalid'}},
    sessionStorage:{getItem:()=> 'synthetic-token',removeItem(){}},localStorage:{removeItem(){}},URLSearchParams,AbortSignal,
    window:{location:{search:query,assign(){}},history:{replaceState(){}}},
    fetch:async()=>({status:200,ok:true,json:async()=>({tasks})}),
    require(name){
      if(name==='react/jsx-runtime')return {jsx,jsxs:jsx};
      if(name==='react')return {useCallback:fn=>fn,useEffect:fn=>effects.push(fn),useState(value){const i=cursor++;if(!(i in state))state[i]=i in initialOverrides?initialOverrides[i]:typeof value==='function'?value():value;return[state[i],next=>{state[i]=typeof next==='function'?next(state[i]):next;}];}};
      if(name==='@/components/I18n')return{useI18n:()=>({locale:'en',t:key=>key})};
      if(name==='@/lib/task-workflow')return helpers;
      if(name==='@/lib/demo-data')return {campaigns:[{id:'demo',name:'Demo',objective:'Synthetic',audience:'Synthetic',channel:'Email',budget:'$0',state:'Demo'}],opportunities:[]};
      if(name==='next/link')return{default:'a'};
      if(name.endsWith('.css'))return{default:{}};
      return{PageHeading:'h1',StatusBadge:'span',TaskPicker:'picker'};
    }};
  if (server) context.window = undefined;
  vm.runInNewContext(compile(read(path)),context);
  const render=()=>{cursor=0;effects.length=0;return flatten(pageModule.exports.default());};
  const output=render(); return{state,effects:effects.slice(),output,render,context};
}

for(const page of ['campaigns','learning']) {
  test(`${page}: task query opens the old task, not the newest`,async()=>{
    const app=mount(`../src/app/${page}/page.tsx`,'?task=old');app.effects[0]();await new Promise(resolve=>setImmediate(resolve));
    const selected=app.state[page==='campaigns'?2:0];assert.equal(selected.task_id,'old');
  });
  test(`${page}: multiple tasks without a query require explicit choice`,async()=>{
    const app=mount(`../src/app/${page}/page.tsx`);app.effects[0]();await new Promise(resolve=>setImmediate(resolve));
    const output=app.render();const picker=output.find(node=>node.type==='picker');assert.equal(picker.props.value,'');assert.equal(picker.props.tasks.length,2);
    picker.props.onChange('old');assert.equal(app.state[page==='campaigns'?2:0].task_id,'old');
  });
  test(`${page}: missing task never falls back to another account/task`,async()=>{
    const app=mount(`../src/app/${page}/page.tsx`,'?task=foreign');app.effects[0]();await new Promise(resolve=>setImmediate(resolve));
    assert.equal(app.state[page==='campaigns'?2:0],null);
  });
}

test('learning: unstarted task visibly locks the submit control',()=>{
  const task=tasks[0];const app=mount('../src/app/learning/page.tsx','',{0:task,1:'ready'});
  const button=app.output.find(node=>node.type==='button'&&node.props.children==='Submit and calculate attribution');
  assert.equal(button.props.disabled,true);assert.match(JSON.stringify(app.output),/Result submission is locked/);
});
test('campaigns: a running task cannot be reconfirmed and links to its own results',()=>{
  const task={...tasks[0],execution:{mode:'manual_handoff',status:'in_progress',started_at:'2026-01-01T00:00:00Z'}};
  const app=mount('../src/app/campaigns/page.tsx','',{2:task,3:'ready'});
  assert.ok(!app.output.some(node=>node.props.children==='Reconfirm parameters'));
  assert.ok(app.output.some(node=>node.props.href==='/learning?task=new'));
  assert.equal(app.output.find(node=>node.type==='fieldset').props.disabled,true);
});
test('diagnostic feedback is structured and updates only the selected task',async()=>{
  const diagnostic={task_id:'diag',title:'Synthetic diagnostic',status:'draft',source_diagnosis:{source:'shopify_aggregate'}};
  // Opportunities: selected, approved, synced, dev-store, signals, reactivation,
  // draft message, tasks, review id, busy, feedback message, lifecycle state.
  const app=mount('../src/app/opportunities/page.tsx','',{7:[diagnostic],8:'diag'});
  let request;
  app.context.fetch=async(url,options)=>{request={url,options};return{ok:true,json:async()=>({task:{...diagnostic,diagnostic_review:{decision:'accepted'},status:'confirmed'}})};};
  await app.output.find(node=>node.props.children==='Accept signal; verify cause').props.onClick();
  assert.equal(request.url,'https://example.invalid/v1/tasks/diag/diagnostic-review');
  assert.deepEqual(JSON.parse(request.options.body),{decision:'accepted'});
  assert.equal(app.state[7][0].status,'confirmed');assert.equal(app.state[9],false);
});

for(const page of ['data','opportunities']) {
  test(`${page}: server and signed-in client have identical initial markup`,()=>{
    const path=`../src/app/${page}/page.tsx`;
    assert.equal(JSON.stringify(mount(path,'',{},true).output),JSON.stringify(mount(path).output));
  });
}

test('opportunities: service failure and malformed tasks are errors, not an empty queue', async()=>{
  for (const fetch of [async()=>{throw new Error('offline');},
    async()=>({ok:false,status:503,json:async()=>({})}),
    async()=>({ok:true,status:200,json:async()=>({})})]) {
    const app=mount('../src/app/opportunities/page.tsx');
    app.context.fetch=fetch; app.effects[0]();
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(app.state[11],'error');
  }
});

test('opportunities: 401 clears account data and does not look like an empty queue', async()=>{
  const app=mount('../src/app/opportunities/page.tsx');
  let token='synthetic-token';
  app.context.sessionStorage={getItem:()=>token,removeItem:()=>{token=null;}};
  app.context.fetch=async()=>({ok:false,status:401,json:async()=>({})});
  app.effects[0](); await new Promise(resolve=>setImmediate(resolve));
  assert.equal(token,null); assert.equal(app.state[11],'signed-out');
  assert.equal(app.state[7].length,0); assert.equal(app.state[4].length,0);
});

test('opportunities: draft creation network failures are recoverable without an automatic resend', async()=>{
  const signal={id:'net_sales_decline',title:'Synthetic',summary:'Synthetic',evidence:{}};
  const app=mount('../src/app/opportunities/page.tsx','',{4:[signal]});
  let calls=0;
  app.context.fetch=async()=>{calls++; throw new Error('offline');};
  await app.output.find(node=>node.props.children==='Create review draft').props.onClick();
  assert.equal(app.state[13],false); assert.match(app.state[6],/unconfirmed/); assert.equal(calls,1);
});
