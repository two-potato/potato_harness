import {test} from 'node:test';
import assert from 'node:assert/strict';
import {bridgeBudget} from '../src/bridge_limits.mjs';
import {guardedPrompt,retryReason,ProviderRetryError} from '../src/provider_retry.mjs';
import {valeraFailure} from '../src/valera_diagnostics.mjs';
test('retry categories are fixed; no provider text leaves the classifier',()=>{
 for(const [status,code] of [
  [{type:'retry',action:{reason:'free_tier_limit',message:'PRIVATE'}},'FREE_QUOTA'],
  [{type:'retry',message:'Free usage exceeded, subscribe to Go'},'FREE_QUOTA'],
  [{type:'retry',message:'429 PRIVATE'},'RATE_LIMIT'],
  [{type:'retry',message:'503 PRIVATE'},'PROVIDER_UNAVAILABLE'],
  [{type:'retry',message:'PRIVATE'},'RETRY_BLOCKED'],
  [{type:'busy'},null],
 ])assert.equal(retryReason(status),code);
});
test('first observed retry aborts only the matching session; never redispatches',async()=>{
 let prompts=0,aborts=0,polls=0;
 const client={session:{
  prompt:()=>{prompts++;return new Promise(()=>{});},
  status:async()=>({data:++polls===1?{other:{type:'retry'},ours:{type:'busy'}}:{ours:{type:'retry',action:{reason:'free_tier_limit'}}}}),
  abort:async({path})=>{assert.equal(path.id,'ours');aborts++;return {data:true};},
 }};
 await assert.rejects(guardedPrompt(client,bridgeBudget(10000),'ours',{}, {pollMs:1}),error=>{
  assert.ok(error instanceof ProviderRetryError);
  assert.deepEqual(valeraFailure('prompt',error),{step:'prompt',reason_code:'FREE_QUOTA'});return true;
 });
 assert.equal(prompts,1);assert.equal(aborts,1);assert.equal(polls,2);
});
test('successful response is preserved and does not abort',async()=>{
 let aborts=0;
 const client={session:{prompt:async()=>({data:42}),status:async()=>({data:{ours:{type:'busy'}}}),abort:async()=>{aborts++;}}};
 assert.deepEqual(await guardedPrompt(client,bridgeBudget(10000),'ours',{}),{data:42});
 assert.equal(aborts,0);
});
test('status monitor failure stops the session and retains the original error even if abort fails',async()=>{
 let aborts=0;
 const client={session:{prompt:()=>new Promise(()=>{}),status:async()=>{throw Error('PRIVATE');},abort:async()=>{aborts++;throw Error('PRIVATE');}}};
 await assert.rejects(guardedPrompt(client,bridgeBudget(10000),'ours',{}),error=>error.code==='MONITOR_FAILED'&&!error.message.includes('PRIVATE'));
 assert.equal(aborts,1);
});
