import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectAttachedServer,attachedFetch,ATTACHED_ENDPOINT} from '../src/attached-server-probe.mjs';
const model={providerID:'openrouter',id:'nvidia/nemotron-fixture:free',enabled:true,status:'active',
 limit:{output:1024},cost:[{input:0,output:0,cache:{read:0,write:0}}]};
function setup(models=[model],version='2.4.1'){
 const calls=[];
 const options={directory:'/private',clientFactory:opts=>{
  assert.equal(opts.baseUrl,ATTACHED_ENDPOINT);
  return {server:{info:async()=>{calls.push('info');return {version};}},
   model:{list:async x=>{calls.push('list');assert.deepEqual(x,{location:{directory:'/private'}});return {data:models};}}};
 }};
 return {calls,options};
}
test('attached probe reads only version and catalog, never admits runtime',async()=>{
 const {calls,options}=setup();
 const r=await inspectAttachedServer(options);
 assert.deepEqual(calls,['info','list']);assert.equal(r.status,'PASS');
 assert.deepEqual(r.candidates,[{model:'openrouter/nvidia/nemotron-fixture:free',enabled:true,zero_catalog_price:true}]);
 assert.equal(r.runtime_admission,false);assert.equal(r.policy_verified,false);assert.equal(r.attempted_prompts,0);
});
test('version mismatch stops before catalog request',async()=>{
 const {calls,options}=setup([model],'2.4.0');
 const r=await inspectAttachedServer(options);
 assert.equal(r.reason,'SERVER_VERSION_MISMATCH');assert.deepEqual(calls,['info']);
});
test('missing, disabled, paid or wrong provider models do not pass',async()=>{
 for(const models of [[],[{...model,enabled:false}],[{...model,cost:[]}],
  [{...model,cost:[{input:0,output:0,cache:{read:0,write:1}}]}],
  [{...model,id:'nvidia/nemotron-paid'}],[{...model,providerID:'opencode'}]]){
  const r=await inspectAttachedServer(setup(models).options);assert.equal(r.status,'HOLD');
 }
});
test('duplicate model identity is ambiguous',async()=>{
 const r=await inspectAttachedServer(setup([model,model]).options);
 assert.equal(r.reason,'CATALOG_AMBIGUOUS');
});
test('errors never expose provider text or credentials',async()=>{
 const r=await inspectAttachedServer({directory:'/tmp',clientFactory:()=>{throw Error('PRIVATE_KEY');}});
 assert.equal(r.status,'HOLD');assert.ok(!JSON.stringify(r).includes('PRIVATE_KEY'));
});
test('transport confines credentials to exact loopback origin and disallows redirects',async()=>{
 let calls=0;
 const send=async req=>{calls++;assert.equal(req.redirect,'error');assert.equal(req.headers.get('Authorization'),'Basic '+Buffer.from('opencode:secret').toString('base64'));return new Response('{}');};
 const fetch=attachedFetch({password:'secret',send});
 for(const url of ['http://127.0.0.1:4097/info','http://localhost:4096/info','https://127.0.0.1:4096/info','http://example.invalid','http://user:pass@127.0.0.1:4096/info'])await assert.rejects(fetch(url));
 assert.equal(calls,0);await fetch(ATTACHED_ENDPOINT+'/info');assert.equal(calls,1);
 const anonymous=attachedFetch({send:async req=>{assert.equal(req.headers.has('Authorization'),false);return new Response('{}');}});
 await anonymous(ATTACHED_ENDPOINT+'/info',{headers:{Authorization:'secret'}});
});

test('catalog includes explicit free IDs from both known providers, not only Nemotron',async()=>{
 const models=[model,{...model,id:'google/gemma-4-31b-it:free'},
  {...model,providerID:'opencode',id:'deepseek-v4.1-flash-free'},
  {...model,id:'openrouter/free'},{...model,id:'nvidia/nemotron-paid'}];
 const r=await inspectAttachedServer(setup(models).options);
 assert.equal(r.status,'PASS');
 assert.deepEqual(r.candidates.map(m=>m.model),[
  'openrouter/nvidia/nemotron-fixture:free','openrouter/google/gemma-4-31b-it:free','opencode/deepseek-v4.1-flash-free']);
 assert.deepEqual(r.catalog_counts,{total:5,opencode:1,openrouter:4,other:0});
 assert.equal(r.runtime_admission,false);
});
test('qualified IDs are advisory, never silently accepted as canonical',async()=>{
 const r=await inspectAttachedServer(setup([{...model,id:'openrouter/nvidia/nemotron-fixture:free'}]).options);
 assert.equal(r.status,'HOLD');
 assert.deepEqual(r.candidates,[{model:'openrouter/nvidia/nemotron-fixture:free',enabled:true,zero_catalog_price:true,identity_shape:'qualified'}]);
 assert.equal(r.reason,'FREE_MODEL_NOT_VERIFIED');
});
test('mixed raw and qualified representations of same model are ambiguous',async()=>{
 const r=await inspectAttachedServer(setup([model,{...model,id:'openrouter/'+model.id}]).options);
 assert.equal(r.reason,'CATALOG_AMBIGUOUS');
});
test('unrecognized providers expose bounded counts, no raw records',async()=>{
 const r=await inspectAttachedServer(setup([{...model,providerID:'SECRET_PROVIDER',secret:'PRIVATE_DATA'}]).options);
 assert.equal(r.status,'HOLD');
 assert.deepEqual(r.catalog_counts,{total:1,opencode:0,openrouter:0,other:1});
 assert.deepEqual(r.candidates,[]);
 assert.ok(!JSON.stringify(r).includes('SECRET_PROVIDER'));
 assert.ok(!JSON.stringify(r).includes('PRIVATE_DATA'));
});
test('free-labelled candidates with incomplete pricing remain unverified',async()=>{
 const r=await inspectAttachedServer(setup([{...model,cost:[{input:0,output:0}]}]).options);
 assert.equal(r.status,'HOLD');
 assert.equal(r.candidates[0].zero_catalog_price,false);
 assert.equal(r.reason,'FREE_MODEL_NOT_VERIFIED');
});
