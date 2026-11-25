import {test} from 'node:test';
import assert from 'node:assert/strict';
import {modelRef,isFreeModel,nativeConfig,serverPolicy,pluginSource,verifyServerSnapshot,POLICY_ID,nativeHttpViolation} from '../src/server-policy.mjs';
import {parseEndpoint,localFetch,awaitServerPolicy} from '../src/server-process.mjs';
import {ROLES} from '../src/profile.mjs';
const name='opencode/test-free',ref=modelRef(name),plugin='/private/policy',cap=64;
const config=nativeConfig(name,cap,plugin);
const target='https://potato-native-fixture.invalid/v1/chat/completions';
const wire=(url=target,init={})=>new Request(url,{method:'POST',headers:{'content-type':'application/json'},body:'{}',...init});
const model={...ref,enabled:true,status:'active',limit:{output:64},cost:[{input:0,output:0,cache:{read:0,write:0}}],capabilities:{tools:false},variants:[]};
const snapshot=()=>({plugins:{data:[{id:POLICY_ID,state:{status:'active'},source:{type:'local',path:plugin}}]},agents:{data:ROLES.map(id=>({...config.agents[id],id,model:ref}))},models:{data:[structuredClone(model)]}});
test('native free model admission requires a real zero-priced catalog entry',()=>{
 for(const id of ['opencode/test','openai/test-free','opencode/test-free#paid','opencode/../test-free'])assert.throws(()=>modelRef(id));
 assert.equal(isFreeModel(model,ref),true);
 for(const cost of [[],[{input:0,output:1,cache:{read:0,write:0}}],[{input:0,output:0,cache:{read:0,write:1}}],[{input:0,output:0}]])assert.equal(isFreeModel({...model,cost},ref),false);
 assert.equal(config.providers,undefined);assert.equal(config.automations,false);assert.equal(config.compaction.auto,false);
 assert.ok(config.plugins.includes(plugin));assert.equal(config.permissions[0].effect,'deny');
});
test('admit only exact active local policy, deny-only roster and free catalog',async()=>{
 assert.equal(verifyServerSnapshot(snapshot(),config,ref,cap,plugin),true);
 for(const change of [s=>s.plugins.data[0].state.status='failed',s=>s.plugins.data.push({id:'unknown',source:{type:'package'},state:{status:'active'}}),s=>s.agents.data[0].permissions[0].effect='allow',s=>s.models.data[0].cost=[],s=>s.models.data[0].variants.push({id:'paid'}),s=>s.models.data.push({...model,id:'other'})]){
  const s=snapshot();change(s);assert.equal(verifyServerSnapshot(s,config,ref,cap,plugin),false);
 }
 let t=0;
 const s=snapshot();s.plugins.data=[];
 await assert.rejects(awaitServerPolicy({client:{plugin:{list:async()=>s.plugins},agent:{list:async()=>s.agents},model:{list:async()=>s.models}},directory:'/tmp',config,ref,plugin,maxOutput:cap},{now:()=>t,pause:async()=>{t+=10},timeout:30}),/NOT_READY/);
});
test('native CLI merged deny rules are admitted for all nine roles',()=>{
 const deny={action:'*',resource:'*',effect:'deny'};
 const browser={action:'browser',resource:'*',effect:'deny'};
 const skill={action:'skill',resource:'browser',effect:'deny'};
 for(const rules of [[deny,deny,deny,browser,skill],[skill,browser,deny],[deny,deny],[deny]]){
  const s=snapshot();
  for(const a of s.agents.data)a.permissions=structuredClone(rules);
  assert.equal(verifyServerSnapshot(s,config,ref,cap,plugin),true);
 }
});
test('merged permissions fail closed for missing wildcard, non-deny or unknown rules',()=>{
 const deny={action:'*',resource:'*',effect:'deny'};
 const browser={action:'browser',resource:'*',effect:'deny'};
 const skill={action:'skill',resource:'browser',effect:'deny'};
 const invalid=[null,undefined,{},[],[browser,skill],[null],[deny,null],
  [deny,{action:'*',effect:'deny'}],[deny,{...deny,unexpected:true}],
  [deny,{...deny,resource:123}],[deny,{...deny,action:''}],
  [deny,,deny],[deny,{action:'unknown',resource:'*',effect:'deny'}],
  [deny,{...skill,resource:'shell'}],[deny,{...browser,resource:'specific'}]];
 for(const effect of ['allow','ask','unknown']){
  for(const rule of [deny,browser,skill]){
   invalid.push([{...rule,effect},deny],[deny,{...rule,effect}]);
  }
 }
 for(const rules of invalid){
  const s=snapshot();s.agents.data[ROLES.length-1].permissions=rules;
  assert.equal(verifyServerSnapshot(s,config,ref,cap,plugin),false);
 }
});
test('generated policy is self-contained and denies tools, retries, extra calls and wrong model',async()=>{
 const source=pluginSource(config,ref,cap,'backend');
 const imported=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
 assert.equal(imported.default.id,POLICY_ID);
 const hooks={},register=(name,fn)=>{hooks[name]=fn;return {dispose:async()=>{}};};
 const ctx={agent:{transform:f=>register('agent',f)},model:{transform:f=>register('model',f)},tool:{transform:f=>register('tools',f)},permission:{hook:(n,f)=>register(n,f)},session:{hook:(n,f)=>register(n,f)}};
 const cleanup=await imported.default.setup(ctx);
 const catalog=[structuredClone(model),{...structuredClone(model),id:'paid',cost:[{input:1,output:1,cache:{read:0,write:0}}]}];
 const removed=[];
 hooks.model({list:()=>catalog,remove:(p,id)=>removed.push(id),update:(p,id,f)=>f(catalog.find(m=>m.id===id)),get:()=>catalog[0],default:{set(){}}});
 assert.deepEqual(removed,['paid']);assert.equal(catalog[0].cost[0].input,0);
 const retry={decision:{retry:true}};hooks.retry(retry);assert.deepEqual(retry.decision,{retry:false});
 const p={effect:'allow'};hooks.evaluate(p);assert.equal(p.effect,'deny');
 const tools={tools:{shell:{}},options:{maxTokens:512}};hooks.context(tools);assert.deepEqual(tools.tools,{});assert.equal(tools.options.maxTokens,64);
 const a={model:ref,sessionID:'one',agent:'valera-ceo',kind:'primary'};hooks['experimental.model.resolve'](a);
 hooks['model.request'](a);hooks['http.request']({...a,request:wire()});
 assert.throws(()=>hooks['http.request'](a),/DENIED/);
 assert.throws(()=>hooks['model.request']({...a,kind:'title'}),/DENIED/);
 const repeated={...a};hooks['experimental.model.resolve'](repeated);assert.equal(repeated.model.providerID,'potato-denied');
 const b={model:ref,sessionID:'two',agent:'backend',kind:'primary'};hooks['experimental.model.resolve'](b);hooks['model.request'](b);hooks['http.request']({...b,request:wire()});
 const extra={...b,sessionID:'three'};hooks['experimental.model.resolve'](extra);assert.equal(extra.model.providerID,'potato-denied');
 await cleanup();
});
test('local client transport does not follow redirects or disclose auth to another origin',async()=>{
 const endpoint=parseEndpoint('{"url":"http://127.0.0.1:4096"}');
 for(const line of ['{"url":"http://0.0.0.0:4096"}','{"url":"https://127.0.0.1:4096"}','{"url":"http://127.0.0.1:4096/path"}','{"url":"http://evil.test:4096"}'])assert.throws(()=>parseEndpoint(line));
 let calls=0;
 const fetch=localFetch(endpoint,'test-password',undefined,async req=>{calls++;assert.equal(req.redirect,'error');assert.equal(req.headers.get('authorization'),'Basic '+Buffer.from('opencode:test-password').toString('base64'));return new Response('{}');});
 await fetch(endpoint+'/health');await assert.rejects(fetch('http://evil.test/'));assert.equal(calls,1);
});

test('policy records exact denial reason and offline boundary before HTTP admission',async()=>{
 const hooks={},events=[],register=(name,fn)=>{hooks[name]=fn;return {dispose:async()=>{}};};
 const ctx={agent:{transform:f=>register('agent',f)},model:{transform:f=>register('model',f)},tool:{transform:f=>register('tools',f)},permission:{hook:(n,f)=>register(n,f)},session:{hook:(n,f)=>register(n,f)}};
 const cleanup=await serverPolicy({id:POLICY_ID,roles:ROLES,definitions:config.agents,ref,maxOutput:cap,worker:'backend',freeCheck:isFreeModel,record:e=>events.push(e),offline:true}).setup(ctx);
 const wrong={model:{...ref,variant:'other'},sessionID:'bad',agent:'valera-ceo',kind:'primary'};
 hooks['experimental.model.resolve'](wrong);assert.equal(wrong.model.providerID,'potato-denied');
 assert.equal(events.at(-1),'violation:resolve_variant_named');
 const missing={model:ref,agent:'valera-ceo',kind:'primary'};
 hooks['experimental.model.resolve'](missing);assert.equal(events.at(-1),'violation:resolve_session');
 const a={model:ref,sessionID:'one',agent:'valera-ceo',kind:'primary'};
 hooks['experimental.model.resolve'](a);
 assert.throws(()=>hooks['model.request'](a),/OFFLINE_MODEL_REQUEST_DENIED/);
 assert.equal(events.at(-1),'violation:offline_stop');
 assert.throws(()=>hooks['http.request'](a),/HTTP_REQUEST_DENIED/);
 assert.equal(events.at(-1),'violation:offline_http');
 assert.ok(!events.includes('model:valera-ceo')&&!events.includes('http:valera-ceo'));
 await cleanup();
});

test('native resolution distinguishes identity fields without admitting alternate model references',async()=>{
 const hooks={},events=[],register=(name,fn)=>{hooks[name]=fn;return {dispose:async()=>{}};};
 const ctx={agent:{transform:f=>register('agent',f)},model:{transform:f=>register('model',f)},tool:{transform:f=>register('tools',f)},permission:{hook:(n,f)=>register(n,f)},session:{hook:(n,f)=>register(n,f)}};
 const cleanup=await serverPolicy({id:POLICY_ID,roles:ROLES,definitions:config.agents,ref,maxOutput:cap,worker:'backend',freeCheck:isFreeModel,record:e=>events.push(e),offline:true}).setup(ctx);
 for(const [m,code] of [
  [null,'model_shape'],[[], 'model_shape'],
  [{id:ref.id},'provider_missing_or_type'],
  [{...ref,providerID:'private-other-provider'},'provider_mismatch'],
  [{providerID:ref.providerID},'id_missing_or_type'],
  [{...ref,id:ref.providerID+'/'+ref.id},'id_qualified'],
  [{...ref,id:'private-other-model'},'id_mismatch'],
  [{...ref,variant:null},'variant_null'],[{...ref,variant:''},'variant_empty'],
  [{...ref,variant:'private-variant'},'variant_named'],
  [{...ref,variant:0},'variant_type']
 ]){
  const e={model:m,sessionID:'one',agent:'valera-ceo',kind:'primary'};
  hooks['experimental.model.resolve'](e);
  assert.deepEqual(e.model,{providerID:'potato-denied',id:'denied'});
  assert.equal(events.at(-1),'violation:resolve_'+code);
 }
 const valid={model:{...ref},sessionID:'one',agent:'valera-ceo',kind:'primary'};
 hooks['experimental.model.resolve'](valid);
 assert.deepEqual(valid.model,ref);
 assert.throws(()=>hooks['model.request'](valid),/OFFLINE_MODEL_REQUEST_DENIED/);
 assert.equal(events.at(-1),'violation:offline_stop');
 assert.ok(!JSON.stringify(events).includes('private-'));
 await cleanup();
});

test('generated native policy admits only absent or exact default variant across all request hooks',async()=>{
 // The generated module exports a stateful policy. Use a distinct module URL
 // so Node's module cache cannot reuse the earlier test's admitted sessions.
 const imported=await import('data:text/javascript;base64,'+Buffer.from(pluginSource(config,ref,cap,'backend')).toString('base64')+'#native-base-variant');
 const hooks={},register=(name,fn)=>{hooks[name]=fn;return {dispose:async()=>{}};};
 const ctx={agent:{transform:f=>register('agent',f)},model:{transform:f=>register('model',f)},tool:{transform:f=>register('tools',f)},permission:{hook:(n,f)=>register(n,f)},session:{hook:(n,f)=>register(n,f)}};
 const cleanup=await imported.default.setup(ctx);
 const a={model:{...ref,variant:'default'},sessionID:'one',agent:'valera-ceo',kind:'primary'};
 const b={model:{...ref},sessionID:'two',agent:'backend',kind:'primary'};
 for(const e of [a,b]){
  hooks['experimental.model.resolve'](e);assert.equal(e.model.id,ref.id);assert.equal(e.model.providerID,ref.providerID);
  for(const variant of [null,'','Default','default ', 'high',0])assert.throws(()=>hooks['model.request']({...e,model:{...ref,variant}}),/DENIED/);
  hooks['model.request'](e);
  for(const variant of [null,'','Default','default ', 'high',0])assert.throws(()=>hooks['http.request']({...e,model:{...ref,variant}}),/DENIED/);
  hooks['http.request']({...e,request:wire()});assert.throws(()=>hooks['http.request'](e),/DENIED/);
 }
 await cleanup();
});

test('native HTTP checks protocol and shape without pinning an upstream route',async()=>{
 for(const url of [target,'https://another-fixture.invalid/v2/messages',
  'https://potato-native-fixture.invalid/changed/api/route','https://potato-native-fixture.invalid:8443/model']){
  const request=wire(url);
  assert.equal(nativeHttpViolation(request),null);
  assert.equal(request.url,url);assert.equal(request.method,'POST');
 }
 assert.equal(nativeHttpViolation(undefined),'http_request_shape');
 assert.equal(nativeHttpViolation(wire(target,{method:'GET',body:undefined})),'http_method');
 for(const url of ['http://potato-native-fixture.invalid/v1/chat/completions',
  'http://127.0.0.1:4096/model',target+'#fragment'])assert.equal(nativeHttpViolation(wire(url)),'http_destination');
 for(const init of [{headers:{'content-type':'text/plain'}},{body:undefined}])assert.equal(nativeHttpViolation(wire(target,init)),'http_payload');
 const used=wire();await used.text();assert.equal(nativeHttpViolation(used),'http_payload');
});
test('native HTTP hook denies invalid protocol and observed redirects without exposing URLs',async()=>{
 const hooks={},events=[],register=(name,fn)=>{hooks[name]=fn;return {dispose:async()=>{}};};
 const ctx={agent:{transform:f=>register('agent',f)},model:{transform:f=>register('model',f)},tool:{transform:f=>register('tools',f)},permission:{hook:(n,f)=>register(n,f)},session:{hook:(n,f)=>register(n,f)}};
 const cleanup=await serverPolicy({id:POLICY_ID,roles:ROLES,definitions:config.agents,ref,maxOutput:cap,worker:'backend',freeCheck:isFreeModel,record:e=>events.push(e)}).setup(ctx);
 const e={model:ref,sessionID:'one',agent:'valera-ceo',kind:'primary'};
 hooks['experimental.model.resolve'](e);hooks['model.request'](e);
 assert.throws(()=>hooks['http.request']({...e,request:wire('http://private.test/path')}),/DENIED/);
 assert.equal(events.at(-1),'violation:http_destination');assert.ok(!events.includes('http:valera-ceo'));
 hooks['http.request']({...e,request:wire()});
 hooks['http.response']({...e,response:new Response('{}',{status:200})});
 for(const status of [301,302,303,307,308]){
  assert.throws(()=>hooks['http.response']({...e,response:new Response(null,{status,headers:{location:'https://private.test'}})}),/DENIED/);
  assert.equal(events.at(-1),'violation:http_redirect');
 }
 assert.ok(!JSON.stringify(events).includes('private.test'));
 await cleanup();
});

test('native policy refuses OMO composition and duplicated policy identity',()=>{
 for(const extra of [
  {id:'oh-my-openagent',state:{status:'active'},source:{type:'package'}},
  {id:'oh-my-opencode',state:{status:'active'},source:{type:'local',path:'/other'}},
  {id:POLICY_ID,state:{status:'active'},source:{type:'package'}},
  {id:POLICY_ID,state:{status:'active'},source:{type:'builtin'}},
  {id:POLICY_ID,state:{status:'active'},source:{type:'local',path:plugin}},
  {id:POLICY_ID,state:{status:'failed'},source:{type:'local',path:'/other'}}
 ]){
  const s=snapshot();s.plugins.data.push(extra);
  assert.equal(verifyServerSnapshot(s,config,ref,cap,plugin),false);
 }
 const s=snapshot();s.plugins.data.push({id:'built-in-test',state:{status:'active'},source:{type:'builtin'}});
 assert.equal(verifyServerSnapshot(s,config,ref,cap,plugin),true);
});
