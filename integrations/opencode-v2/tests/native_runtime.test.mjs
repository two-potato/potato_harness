import test from 'node:test';
import assert from 'node:assert/strict';
import {NATIVE_FIXTURE_MODEL,runNativeRuntimeFixture} from '../src/server-inference.mjs';
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
