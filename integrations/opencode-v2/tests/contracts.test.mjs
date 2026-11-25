import {test} from 'node:test';
import assert from 'node:assert/strict';
import {candidateConfig,validateRequest,parseAssistant,combine,FIXTURE_URL} from '../src/contracts.mjs';
import {fixtureTransport,restrictivePlugin} from '../src/policy.mjs';
const request={role:'backend',model:'fixture/test',prompt:'repair',coordination:{objective:'repair',scope:['a.py']},output_token_allowance:128};
test('v2 is explicitly fixture-only; all nine roles preserved; deny by default',()=>{
 assert.equal(validateRequest(request),64);
 assert.throws(()=>validateRequest({...request,model:'opencode/mimo-v2.6-flash-free'}),/FIXTURE_ONLY/);
 assert.throws(()=>validateRequest({...request,role:'valera-ceo'}));
 const c=candidateConfig(64);
 assert.equal(Object.keys(c.agents).length,9);
 assert.equal(c.default_agent,'valera-ceo');
 assert.equal(c.automations,false);assert.equal(c.compaction.auto,false);
 assert.ok(Object.values(c.agents).every(a=>a.steps===1&&a.permissions[0].effect==='deny'));
});
const assistant=(role,value,extra={})=>({type:'assistant',agent:role,model:{providerID:'fixture',id:'test'},finish:'stop',time:{completed:1},content:[{type:'text',text:JSON.stringify(value)}],tokens:{input:10,output:5,reasoning:1,cache:{read:2,write:0}},cost:0,...extra});
test('proposal contract rejects extra calls, tools, wrong owner and out-of-scope paths',()=>{
 const p=parseAssistant([assistant('valera-ceo',{owner:'backend',reason:'route'})],'valera-ceo');
 const q=parseAssistant([assistant('backend',{edits:[{path:'a.py',content:'x'}],summary:'fix'})],'backend');
 assert.deepEqual(combine(p,q,'backend',['a.py']).usage,{input_tokens:24,output_tokens:12,cost_usd:0});
 assert.throws(()=>combine(p,q,'backend',['b.py']));
 assert.throws(()=>parseAssistant([assistant('backend',{}),assistant('backend',{})],'backend'));
 assert.throws(()=>parseAssistant([assistant('backend',{}, {content:[{type:'tool'}]})],'backend'));
 assert.throws(()=>parseAssistant([assistant('backend',{}, {retry:{attempt:1}})],'backend'));
 const unknown={...q,info:{...q.info,cost:undefined}};
 assert.equal(combine(p,unknown,'backend',['a.py']).usage.cost_usd,null);
});
test('transport permits one bounded fixture request per phase and never calls external fetch',async()=>{
 let n=0;const t=fixtureTransport(()=>{n++;return new Response('ok');},64);
 const init={method:'POST',body:JSON.stringify({model:'test',max_tokens:64,messages:[{role:'user',content:'x'}]})};
 t.begin('valera');await t.fetch(FIXTURE_URL,init);t.end();
 t.begin('specialist');await t.fetch(FIXTURE_URL,init);
 await assert.rejects(t.fetch(FIXTURE_URL,init));assert.throws(()=>t.end());
 assert.equal(n,2);
 const x=fixtureTransport(()=>{throw Error('unexpected');},64);x.begin('valera');
 await assert.rejects(x.fetch('https://external.example/v1/chat/completions',init));assert.equal(x.violated,true);
});
test('retry hook denies retry before execution; permission and tool transforms deny',async()=>{
 const callbacks={};const observed={retries:0,ready:false};
 const reg=(key,fn)=>{callbacks[key]=fn;return Promise.resolve({dispose:async()=>{}});};
 const ctx={agent:{transform:fn=>reg('agent',fn)},tool:{transform:fn=>reg('tools',fn)},permission:{hook:(_,fn)=>reg('permission',fn)},session:{hook:(key,fn)=>reg(key,fn)}};
 const close=await restrictivePlugin(observed,64).setup(ctx);
 const retry={decision:{retry:true,delay:1000}};callbacks.retry(retry);
 assert.deepEqual(retry.decision,{retry:false});assert.equal(observed.retries,1);
 const permission={effect:'allow'};callbacks.permission(permission);assert.equal(permission.effect,'deny');
 const removed=[];callbacks.tools({list:()=>[{id:'shell'},{id:'read'}],remove:id=>removed.push(id)});assert.deepEqual(removed,['shell','read']);
 const context={tools:{shell:{}},options:{}};callbacks.context(context);assert.deepEqual(context.tools,{});assert.equal(context.options.maxOutputTokens,64);
 await close();
});
