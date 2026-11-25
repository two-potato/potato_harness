import test from 'node:test';
import assert from 'node:assert/strict';
import {NATIVE_FIXTURE_MODEL,runNativeRuntimeFixture,runNativeRuntimeOffline,runNativeRuntimeCandidate} from '../src/server-inference.mjs';
import {launchNativeFixture,awaitNativeFixture} from '../src/native-runtime-fixture.mjs';
import {OBJECTIVE} from '../src/trial-fixture.mjs';
const request={role:'backend',model:NATIVE_FIXTURE_MODEL,prompt:'synthetic scoped source',coordination:{objective:OBJECTIVE,scope:['calculation.py']},output_token_allowance:4096};
const opts={launch:launchNativeFixture,awaitPolicy:awaitNativeFixture};
test('native runtime fixture uses shared R1 flow and returns a scoped proposal only',async()=>{
 const events=[];
 const result=await runNativeRuntimeFixture(request,{...opts,onPhase:e=>events.push(e)});
 assert.deepEqual(result,{edits:[{path:'calculation.py',content:'def subtotal(unit_cents, quantity):\n    return unit_cents * quantity\n'}],summary:'synthetic native runtime proposal',usage:{input_tokens:20,output_tokens:20,cost_usd:0}});
 assert.deepEqual(events.filter(e=>e.status==='ok').map(e=>e.phase),['server','valera','specialist','cleanup']);
});
test('native runtime fixture cannot accept a real model or arbitrary scope, role or objective',async()=>{
 for(const patch of [{model:'opencode/beam-free'},{role:'architect'},{coordination:{...request.coordination,scope:['other.py']}},{coordination:{...request.coordination,objective:'other task'}},{output_token_allowance:0},{provider_budget:{cost_usd:1}}]){
  let launched=false;
  await assert.rejects(()=>runNativeRuntimeFixture({...request,...patch},{...opts,launch:async()=>{launched=true;throw Error('unexpected');}}));
  assert.equal(launched,false);
 }
});
test('rate limit, unknown usage, invalid assignment and audit violations stop after Valera',async()=>{
 for(const fault of ['rate_limit','unknown_cost','assignment','audit']){
  const calls=[],events=[];
  const launch=options=>launchNativeFixture(options,{fault,onPrompt:role=>calls.push(role)});
  await assert.rejects(()=>runNativeRuntimeFixture(request,{...opts,launch,onPhase:e=>events.push(e)}),/NATIVE_FIXTURE_HOLD/);
  assert.deepEqual(calls,['valera-ceo']);
  assert.ok(events.some(e=>e.phase==='valera'&&e.status==='error'));
  if(fault==='rate_limit')assert.ok(events.some(e=>e.reason_code==='RATE_LIMIT'));
  assert.ok(events.some(e=>e.phase==='cleanup'&&e.status==='ok'));
  assert.ok(!JSON.stringify(events).includes('PRIVATE_PROVIDER_TEXT'));
 }
});
test('late audit violation or unscoped specialist result does not return a proposal',async()=>{
 for(const fault of ['final_audit','scope']){
  const calls=[];
  await assert.rejects(()=>runNativeRuntimeFixture(request,{...opts,launch:o=>launchNativeFixture(o,{fault,onPrompt:r=>calls.push(r)})}),/NATIVE_FIXTURE_HOLD/);
  assert.deepEqual(calls,['valera-ceo','backend']);
 }
});

test('offline runtime requires network guard and never returns a proposal',async()=>{
 const live={...request,model:'opencode/beam-free'};
 const calls=[];
 const launch=async options=>{
  assert.equal(options.offline,true);assert.equal(options.audit,true);
  const audit=['ready'];let role;
  return {directory:'/offline',readAudit:()=>[...audit],close:async()=>[...audit],
   client:{session:{create:async x=>{role=x.agent;return {id:role};},prompt:async()=>{calls.push(role);audit.push('violation:offline_stop');},interrupt:async()=>{}},
    experimental:{session:{wait:async()=>{}}},
    message:{list:async x=>x.cursor?{data:[]}:{cursor:{next:'tail'},data:[{type:'user'},{type:'idle',outcome:'failed'}]}}}};
 };
 const opts={launch,awaitPolicy:async()=>{},verifyNetwork:()=>{throw Error('OFFLINE_NETWORK_REQUIRED');}};
 await assert.rejects(()=>runNativeRuntimeOffline(live,opts),/OFFLINE_NETWORK_REQUIRED/);
 assert.deepEqual(calls,[]);
 for(const model of [NATIVE_FIXTURE_MODEL,'opencode/paid'])await assert.rejects(()=>runNativeRuntimeOffline({...live,model},{...opts,verifyNetwork:()=>{}}));
 const events=[];
 await assert.rejects(()=>runNativeRuntimeOffline(live,{...opts,verifyNetwork:()=>{},onPhase:e=>events.push(e)}),/NATIVE_OFFLINE_BOUNDARY/);
 assert.deepEqual(calls,['valera-ceo']);
 assert.deepEqual(events.at(-1),{phase:'offline_boundary',status:'ok',elapsed_ms:0});
});
test('offline marker rejects unexpected HTTP, early denial and cleanup failure',async()=>{
 for(const fault of ['http','early','cleanup']){
  const events=[],audit=['ready'];
  const launch=async()=>({directory:'/offline',readAudit:()=>[...audit],close:async()=>{if(fault==='cleanup')throw Error('private');return [...audit];},
   client:{session:{create:async()=>({id:'one'}),prompt:async()=>{audit.push(fault==='early'?'violation:resolve_model':'violation:offline_stop');if(fault==='http')audit.push('http:valera-ceo');},interrupt:async()=>{}},experimental:{session:{wait:async()=>{}}},
    message:{list:async x=>x.cursor?{data:[]}:{cursor:{next:'tail'},data:[{type:'user'},{type:'idle',outcome:'failed'}]}}}});
  await assert.rejects(()=>runNativeRuntimeOffline({...request,model:'opencode/beam-free'},{launch,awaitPolicy:async()=>{},verifyNetwork:()=>{},onPhase:e=>events.push(e)}),/NATIVE_OFFLINE_HOLD/);
  assert.ok(!events.some(e=>e.phase==='offline_boundary'));
 }
});

test('native runtime modes reject transport overrides and malformed contract before launch',async()=>{
 const runners=[
  [runNativeRuntimeFixture,request,{}],
  [runNativeRuntimeOffline,{...request,model:'opencode/beam-free'},{verifyNetwork:()=>{}}]
 ];
 for(const [run,input,extra] of runners){
  for(const patch of [
   {baseURL:'https://private.invalid'},{apiKey:'secret'},{provider_budget:{tokens:100,cost_usd:0}},
   {provider:'other'},{fallback:'opencode/other-free'},{retry:true},{tools:['shell']},
   {permissions:[{action:'*',effect:'allow'}]},{live:true},{mode:'native-free'},
   {coordination:{...input.coordination,provider:'other'}},
   {bridge_timeout_ms:4000},{bridge_timeout_ms:120001},{bridge_timeout_ms:null},
   {projectDir:123},{output_token_allowance:4097}
  ]){
   let calls=0;
   await assert.rejects(()=>run({...input,...patch},{...extra,launch:async()=>{calls++;throw Error('unexpected launch');},awaitPolicy:async()=>{}}));
   assert.equal(calls,0);
  }
 }
});
test('native fixture accepts host request fields without forwarding workspace or selecting a transport',async()=>{
 const calls=[];
 const result=await runNativeRuntimeFixture({...request,projectDir:'/private/host-only',bridge_timeout_ms:9000},{
  launch:options=>{calls.push(options);return launchNativeFixture(options);},awaitPolicy:awaitNativeFixture
 });
 assert.deepEqual(calls,[{model:NATIVE_FIXTURE_MODEL,worker:'backend',maxOutput:2048,audit:true,offline:false}]);
 assert.equal(result.usage.cost_usd,0);
});

test('native idle-only provider errors preserve fixed category and stop without replay',async()=>{
 for(const [fault,category,roles] of [
  ['idle_rate','RATE_LIMIT',['valera-ceo']],
  ['idle_quota','FREE_QUOTA',['valera-ceo']],
  ['idle_auth','AUTH',['valera-ceo']],
  ['specialist_idle_rate','RATE_LIMIT',['valera-ceo','backend']],
  ['failed_idle_with_answer','RATE_LIMIT',['valera-ceo']],
  ['duplicate_idle','RESPONSE_REJECTED',['valera-ceo']],
  ['interrupted_idle','RESPONSE_REJECTED',['valera-ceo']]
 ]){
  const calls=[],events=[];
  await assert.rejects(()=>runNativeRuntimeFixture(request,{...opts,
   launch:o=>launchNativeFixture(o,{fault,onPrompt:r=>calls.push(r)}),onPhase:e=>events.push(e)}),/NATIVE_FIXTURE_HOLD/);
  assert.deepEqual(calls,roles);
  assert.ok(events.some(e=>e.phase===(roles.length===1?'valera':'specialist')&&e.status==='error'&&e.reason_code===category));
  assert.ok(events.some(e=>e.phase==='cleanup'&&e.status==='ok'));
  assert.ok(!JSON.stringify(events).includes('PRIVATE_PROVIDER_TEXT'));
 }
});
test('native cumulative reported usage prevents second dispatch or proposal when budget is exhausted',async()=>{
 for(const [limit,roles] of [[19,['valera-ceo']],[21,['valera-ceo']],[39,['valera-ceo','backend']]]){
  const calls=[];
  await assert.rejects(()=>runNativeRuntimeFixture({...request,token_allowance:limit},{
   ...opts,launch:o=>launchNativeFixture(o,{onPrompt:r=>calls.push(r)})
  }),/NATIVE_FIXTURE_HOLD/);
  assert.deepEqual(calls,roles);
 }
 const p=await runNativeRuntimeFixture({...request,token_allowance:40},opts);
 assert.deepEqual(p.usage,{input_tokens:20,output_tokens:20,cost_usd:0});
 for(const token_allowance of [0,1,-1,null,1.5,Number.MAX_SAFE_INTEGER+1]){
  await assert.rejects(()=>runNativeRuntimeFixture({...request,token_allowance},{...opts,launch:()=>{throw Error('unexpected launch');}}),/NATIVE_TOKEN_ALLOWANCE/);
 }
});

const candidateRequest={...request,model:'opencode/deepseek-v4.1-flash-free',token_allowance:100,bridge_timeout_ms:9000};
function candidateTransport(fault){
 const calls=[],launches=[],prompts=[],audit=['ready'],sessions=new Map();
 const stats={closed:0};
 const launch=async options=>{
  launches.push(options);
  assert.equal(options.model,candidateRequest.model);
  assert.equal(options.worker,'backend');
  assert.equal(options.audit,true);assert.equal(options.offline,false);
  return {directory:'/synthetic-candidate',readAudit:()=>[...audit],
   close:async()=>{stats.closed++;if(fault==='cleanup')throw Error('PRIVATE_CLEANUP');return fault==='audit'?[...audit,'violation:retry']:[...audit];},
   client:{session:{
    create:async x=>{
     assert.deepEqual(x.location,{directory:'/synthetic-candidate'});
     assert.deepEqual(x.model,{providerID:'opencode',id:'deepseek-v4.1-flash-free'});
     assert.deepEqual(x.permissions,[{action:'*',resource:'*',effect:'deny'}]);
     const id='fake-'+sessions.size;sessions.set(id,x.agent);return {id};
    },
    prompt:async({sessionID,text})=>{const role=sessions.get(sessionID);calls.push(role);prompts.push(text);audit.push('model:'+role,'http:'+role);},
    interrupt:async()=>{}
   },experimental:{session:{wait:async()=>{}}},
   message:{list:async x=>{
    if(x.cursor)return {data:[]};
    const role=sessions.get(x.sessionID),first=role==='valera-ceo';
    const value=first?{owner:'backend',reason:'synthetic assignment'}:{edits:[{path:fault==='scope'?'outside.py':'calculation.py',content:'replacement'}],summary:'synthetic proposal'};
    const error=first&&fault==='rate'?{type:'provider.rate-limit',message:'PRIVATE_PROVIDER_TEXT'}:undefined;
    const data=error?[{type:'user'},{type:'idle',outcome:'failed',error}]:[
     {type:'user'},{type:'assistant',agent:role,model:{providerID:'opencode',id:first&&fault==='identity'?'other-free':'deepseek-v4.1-flash-free'},
      finish:'stop',time:{completed:1},tokens:{input:10,output:5},cost:first&&fault==='paid'?1:0,content:[{type:'text',text:JSON.stringify(value)}]},
     {type:'idle',outcome:'succeeded'}];
    return {data,cursor:{next:'tail'}};
   }}}};
 };
 return {launch,calls,prompts,launches,stats};
}
test('future native candidate exercises explicit model and two-stage proposal on injected transport only',async()=>{
 const f=candidateTransport(),events=[];
 const p=await runNativeRuntimeCandidate(candidateRequest,{expectedModel:candidateRequest.model,launch:f.launch,awaitPolicy:async()=>{},onPhase:e=>events.push(e)});
 assert.deepEqual(f.calls,['valera-ceo','backend']);
 assert.equal(f.stats.closed,1);
 assert.ok(!f.prompts[0].includes(candidateRequest.prompt));
 assert.ok(f.prompts[1].includes(candidateRequest.prompt));
 assert.deepEqual(p,{edits:[{path:'calculation.py',content:'replacement'}],summary:'synthetic proposal',usage:{input_tokens:20,output_tokens:10,cost_usd:0}});
 assert.deepEqual(events.filter(e=>e.status==='ok').map(e=>e.phase),['server','valera','specialist','cleanup']);
});
test('future candidate requires independent host model selection, reservation and deadline before launch',async()=>{
 const f=candidateTransport(),opts={expectedModel:candidateRequest.model,launch:f.launch,awaitPolicy:async()=>{}};
 for(const patch of [{model:NATIVE_FIXTURE_MODEL},{model:'opencode/beam-free'},{model:'opencode/paid'},
  {token_allowance:undefined},{bridge_timeout_ms:undefined},{token_allowance:0},{bridge_timeout_ms:4000},
  {live:true},{baseURL:'https://private.invalid'},{coordination:{...request.coordination,scope:['outside.py']}}]){
  await assert.rejects(()=>runNativeRuntimeCandidate({...candidateRequest,...patch},opts));
 }
 await assert.rejects(()=>runNativeRuntimeCandidate(candidateRequest,{...opts,expectedModel:undefined}));
 await assert.rejects(()=>runNativeRuntimeCandidate(candidateRequest,{...opts,awaitPolicy:undefined}));
 assert.equal(f.launches.length,0);
});
test('future candidate holds on first-stage rejection and late invalid result without replay',async()=>{
 for(const [fault,roles] of [['rate',['valera-ceo']],['paid',['valera-ceo']],['identity',['valera-ceo']],['scope',['valera-ceo','backend']],['cleanup',['valera-ceo','backend']],['audit',['valera-ceo','backend']]]){
  const f=candidateTransport(fault),events=[];
  await assert.rejects(()=>runNativeRuntimeCandidate(candidateRequest,{expectedModel:candidateRequest.model,launch:f.launch,awaitPolicy:async()=>{},onPhase:e=>events.push(e)}),/NATIVE_CANDIDATE_HOLD/);
  assert.deepEqual(f.calls,roles);assert.equal(f.stats.closed,1);
  assert.ok(!JSON.stringify(events).includes('PRIVATE_'));
  if(fault==='rate')assert.ok(events.some(e=>e.reason_code==='RATE_LIMIT'));
 }
});
