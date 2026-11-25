import {test} from 'node:test';
import assert from 'node:assert/strict';
import {candidateConfig,validateRequest,parseAssistant,combine,FIXTURE_URL,readBoundedMessages} from '../src/contracts.mjs';
import {fixtureTransport,restrictivePlugin,awaitPolicy,safeRoster,awaitModel} from '../src/policy.mjs';
const request={role:'backend',model:'fixture/test',prompt:'repair',coordination:{objective:'repair',scope:['a.py']},output_token_allowance:128};
test('v2 is explicitly fixture-only; all nine roles preserved; deny by default',()=>{
 assert.equal(validateRequest(request),64);
 assert.throws(()=>validateRequest({...request,model:'opencode/mimo-v2.6-flash-free'}),/FIXTURE_ONLY/);
 assert.throws(()=>validateRequest({...request,role:'valera-ceo'}));
 const c=candidateConfig(64);
 assert.equal(Object.keys(c.agents).length,9);
 assert.equal(c.default_agent,'valera-ceo');
 assert.equal(c.automations,false);assert.equal(c.compaction.auto,false);
 assert.deepEqual(c.plugins,['-opencode.provider.ollama','-opencode.provider.lmstudio','-opencode.provider.vllm']);
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
 const context={tools:{shell:{}},options:{}};callbacks.context(context);assert.deepEqual(context.tools,{});assert.equal(context.options.maxTokens,64);
 const smaller={tools:{},options:{maxTokens:8}};callbacks.context(smaller);assert.equal(smaller.options.maxTokens,8);
 await close();
});

test('async plugin initialization is bounded and unsafe roster never admits a model request',async()=>{
 const c=candidateConfig(64);
 const agents=Object.entries(c.agents).map(([id,a])=>({...a,id,model:{providerID:'fixture',id:'test'}}));
 assert.equal(safeRoster(agents),true);
 assert.equal(safeRoster([...agents,{id:'build'}]),false);
 assert.equal(safeRoster(agents.map((a,i)=>i? a:{...a,permissions:[{effect:'allow'}]})),false);
 let now=0,reads=0;const observe={ready:false};
 await awaitPolicy(async()=>{reads++;if(reads===3)observe.ready=true;return {data:reads===1?[]:agents};},observe,{now:()=>now,pause:async()=>{now+=10;},timeout:100});
 assert.equal(reads,3);
 await assert.rejects(awaitPolicy(async()=>({data:agents.slice(1)}),observe,{now:()=>now,pause:async()=>{now+=10;},timeout:30}),/V2_PLUGIN_NOT_ACTIVE/);
});

test('fixture model readiness waits for the configured bounded capability',async()=>{
 let n=0,time=0;const model={id:'test',providerID:'fixture',enabled:true,limit:{output:64},capabilities:{tools:false}};
 await awaitModel(async()=>({data:[++n===1?{...model,limit:{output:128}}:model]}),64,{now:()=>time,pause:async()=>{time+=10;},timeout:50});
 assert.equal(n,2);
 await assert.rejects(awaitModel(async()=>({data:[{...model,capabilities:{tools:true}}]}),64,{now:()=>time,pause:async()=>{time+=10;},timeout:30}),/V2_MODEL_NOT_READY/);
});

test('v2 terminal cursors do not imply another page; verify bounded transcript is complete',async()=>{
 const queries=[];const first={data:[{type:'user'},{type:'assistant'}],cursor:{previous:'p',next:'n'}};
 const page=await readBoundedMessages(async input=>{queries.push(input);return input.cursor?{data:[],cursor:{}}:first;},'session');
 assert.equal(page,first);assert.deepEqual(queries,[{sessionID:'session',order:'asc',limit:100},{sessionID:'session',cursor:'n',limit:1}]);
 await assert.rejects(readBoundedMessages(async input=>input.cursor?{data:[{type:'assistant'}]}:first,'session'),/UNEXPECTED_MESSAGE_PAGINATION/);
 await assert.rejects(readBoundedMessages(async()=>({data:first.data,cursor:{}}),'session'),/MISSING_MESSAGE_CURSOR/);
});

test('unexpected startup traffic permanently closes model admission',async()=>{
 let calls=0;
 const t=fixtureTransport(()=>{calls++;return new Response('ok');},64);
 await assert.rejects(t.fetch('https://external.example/health'));
 assert.throws(()=>t.begin('valera'),/INVALID_FIXTURE_STAGE/);
 assert.equal(calls,0);
 const closed=fixtureTransport(()=>{calls++;return new Response('ok');},64);
 closed.close();
 assert.throws(()=>closed.begin('valera'),/INVALID_FIXTURE_STAGE/);
 assert.equal(calls,0);
});

test('native v2 rejects coordinator, oversized input and unbounded allowance before SDK calls',()=>{
 assert.throws(()=>validateRequest({...request,role:'valera-ceo'}));
 assert.throws(()=>validateRequest({...request,prompt:'x'.repeat(262145)}));
 for(const n of [undefined,null,0,1,4097,Infinity])assert.throws(()=>validateRequest({...request,output_token_allowance:n}));
});
