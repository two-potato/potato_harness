import test from 'node:test';
import assert from 'node:assert/strict';
import {attachedWireRequest} from '../src/attached-wire-policy.mjs';
import {pluginSource} from '../src/server-policy.mjs';
import {buildProfile} from '../src/attached-policy-profile.mjs';
const id='nvidia/nemotron-3-ultra-550b-a55b:free',ref={providerID:'openrouter',id};
const url='https://openrouter.ai/api/v1/chat/completions';
const body={model:id,messages:[{role:'system',content:'synthetic role'},{role:'user',content:'synthetic task'}],
 stream:true,max_completion_tokens:1024,usage:{include:true}};
function req(value=body,endpoint=url,headers={}){
 return new Request(endpoint,{method:'POST',headers:{'content-type':'application/json',
  authorization:'Bearer fixture-secret',...headers},body:JSON.stringify(value)});
}
test('attached wire guard pins endpoint, model, zero requested prices and no fallback',async()=>{
 const original=req(),result=await attachedWireRequest(original,ref,1024);
 assert.equal(result.url,url);assert.equal(result.redirect,'error');
 assert.equal(result.headers.get('authorization'),'Bearer fixture-secret');
 assert.equal(original.bodyUsed,false);
 const v=await result.json();
 assert.deepEqual(v.provider,{allow_fallbacks:false,max_price:{prompt:0,completion:0,request:0,image:0}});
 assert.equal(v.model,id);assert.equal(v.max_completion_tokens,1024);
 assert.deepEqual(v.messages,body.messages);
});
test('guard rejects paid/alternate models, routing or plugins, unknown fields and non-text input',async()=>{
 for(const patch of [
  {model:id.replace(':free','')},{model:'openrouter/free'},{models:[id]},
  {provider:{allow_fallbacks:true}},{provider:{max_price:{prompt:1}}},{provider:{order:['other']}},
  {plugins:[{id:'web'}]},{tools:[{type:'function'}]},{tool_choice:'auto'},{preset:'paid'},
  {transforms:['middle-out']},{max_completion_tokens:1025},{max_tokens:1024},{stream:false},
  {messages:[{role:'user',content:[{type:'image_url',image_url:{url:'https://other.invalid'}}]}]},
  {messages:[{role:'tool',content:'tool data'}]},{messages:[{role:'user',content:'x'.repeat(262145)}]},
  {reasoning:{max_tokens:1025}},{unknown:true}
 ])await assert.rejects(()=>attachedWireRequest(req({...body,...patch}),ref,1024),/ATTACHED_WIRE_DENIED/);
 for(const endpoint of ['https://other.invalid/api/v1/chat/completions',url+'?route=x',
  'http://openrouter.ai/api/v1/chat/completions','https://openrouter.ai/api/v1/responses'])
  await assert.rejects(()=>attachedWireRequest(req(body,endpoint),ref,1024));
 await assert.rejects(()=>attachedWireRequest(req(body,url,{'x-unknown-routing':'x'}),ref,1024));
 await assert.rejects(()=>attachedWireRequest(req(),{providerID:'other',id},1024));
});
test('generated attached plugin enforces guard before recording or forwarding HTTP hook',async()=>{
 const p=buildProfile('/fixture','openrouter/'+id);
 const src=pluginSource(p.config,p.ref,1024,'backend',undefined,false,attachedWireRequest);
 const plugin=(await import('data:text/javascript;base64,'+Buffer.from(src).toString('base64'))).default;
 const hooks={},reg=(name,fn)=>{hooks[name]=fn;return {dispose:async()=>{}};};
 const close=await plugin.setup({agent:{transform:f=>reg('agent',f)},model:{transform:f=>reg('model',f)},
  tool:{transform:f=>reg('tool',f)},permission:{hook:reg},session:{hook:reg}});
 const e={kind:'primary',agent:'valera-ceo',sessionID:'s',model:ref};
 hooks['experimental.model.resolve'](e);hooks['model.request'](e);
 await assert.rejects(()=>hooks['http.request']({...e,request:req({...body,model:'paid'})}),/HTTP_REQUEST_DENIED/);
 const wire={...e,request:req()};await hooks['http.request'](wire);
 assert.equal((await wire.request.json()).provider.max_price.prompt,0);
 assert.throws(()=>hooks['http.request']({...e,request:req()}),/HTTP_REQUEST_DENIED/);
 await close();
});
