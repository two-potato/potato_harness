import test from 'node:test';
import assert from 'node:assert/strict';
import {NATIVE_FIXTURE_MODEL,runNativeRuntimeFixture,runNativeRuntimeOffline} from '../src/server-inference.mjs';
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
