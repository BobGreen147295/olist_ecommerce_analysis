// Manual UI QA only: localhost, synthetic data, no production API or database.
import http from 'node:http';
const start = new Date(Date.now() - 30 * 86_400_000).toISOString();
const tasks = [
  {task_id:'qa-running',title:'合成测试：观察中的再激活',status:'confirmed',source_diagnosis:{source:'consented_reactivation_aggregate'},attribution_window_days:14,channel:'email',budget:20,market:'US',locale:'en',execution:{mode:'manual_handoff',status:'in_progress',started_at:new Date().toISOString()}},
  {task_id:'qa-old',title:'合成测试：已结束的旧任务',status:'completed',source_diagnosis:{source:'consented_reactivation_aggregate'},attribution_window_days:14,execution:{mode:'manual_handoff',status:'result_recorded',started_at:start},result:{conversion_uplift_pp:10,incremental_orders:10,incremental_revenue:1000,roi:4,currency:'USD',attribution_window_days:14,revenue_net_of_refunds:true}},
  {task_id:'qa-diagnostic',title:'合成测试：订单金额变化诊断',status:'draft',source_diagnosis:{source:'shopify_aggregate',evidence:{previous_net_sales:700,recent_net_sales:420},provenance:{currency:'USD',observed_start:'2026-01-01',observed_end:'2026-01-14'}}},
];
http.createServer((request,response)=>{
  response.setHeader('Access-Control-Allow-Origin','http://127.0.0.1:3008');
  response.setHeader('Access-Control-Allow-Headers','Authorization,Content-Type');
  response.setHeader('Access-Control-Allow-Methods','GET,POST,OPTIONS');
  response.setHeader('Content-Type','application/json');
  if(request.method==='OPTIONS'){response.writeHead(204);response.end();return;}
  const pathname = new URL(request.url,'http://127.0.0.1').pathname;
  let body=''; request.on('data',chunk=>{body+=chunk;});
  request.on('end',()=>{
    let payload;
    try{payload=JSON.parse(body||'{}');}catch{response.writeHead(400);response.end('{}');return;}
    const task=tasks.find(item=>pathname.includes(item.task_id));
    let data={};
    if(pathname==='/v1/auth/login') data={access_token:'synthetic-qa-session-only'};
    else if(pathname==='/v1/tasks') data={tasks};
    else if(pathname==='/v1/integrations/shopify/status') data={connection:null};
    else if(pathname==='/v1/opportunities/reactivation') data={signal:null};
    else if(pathname.endsWith('/diagnostic-review')&&task){
      task.diagnostic_review={decision:payload.decision,reviewed_at:new Date().toISOString(),next_action:'clarify_definition'};
      data={task};
    }
    response.end(JSON.stringify(data));
  });
}).listen(5018,'127.0.0.1',()=>console.log('Synthetic UI fixture on http://127.0.0.1:5018'));
