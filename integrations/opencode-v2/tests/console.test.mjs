import {test} from 'node:test';
import assert from 'node:assert/strict';
import {consoleResponder,consoleUsage,CONSOLE_URL,CONSOLE_MODEL} from '../src/console.mjs';
const usage={cost:0.002,opencode:{billing_source:'balance',tokens:{input:10,output:7,reasoning:2,cache_read:3,cache_write_5m:1,cache_write_1h:0}}};
const event=u=>'data: '+JSON.stringify({choices:[],usage:u})+'\n\ndata: [DONE]\n\n';
test('console billing counts reasoning once and never fabricates zero cost',()=>{
 assert.deepEqual(consoleUsage(event(usage)),{input_tokens:14,output_tokens:7,cost_usd:.002});
 for(const u of [{...usage,cost:undefined},{...usage,cost:null},{...usage,opencode:{...usage.opencode,billing_source:'byok'}},{...usage,opencode:{...usage.opencode,estimated:true}}])assert.equal(consoleUsage(event(u)).cost_usd,null);
 assert.throws(()=>consoleUsage(event({...usage,opencode:{...usage.opencode,tokens:{input:10,output:7}}})));
 assert.throws(()=>consoleUsage(event(usage).replace('data: [DONE]','')));
 assert.throws(()=>consoleUsage('data: '+JSON.stringify({usage})+'\n\n'+event(usage)));
});
test('only fixed Console endpoint receives key and scoped streamed payload; no redirects or retries',async()=>{
 const controller=new AbortController();let calls=0;
 const t=consoleResponder('key-not-for-logs',{signal:controller.signal,send:async(url,init)=>{
  calls++;assert.equal(url,CONSOLE_URL);assert.equal(init.redirect,'error');assert.equal(init.headers.Authorization,'Bearer key-not-for-logs');
  const body=JSON.parse(init.body);assert.equal(body.model,CONSOLE_MODEL);assert.equal(body.stream_options.include_usage,true);
  assert.equal(body.tools,undefined);assert.equal(body.extra,undefined);
  return new Response(event(usage),{headers:{'Content-Type':'text/event-stream'}});
 }});
 const body={model:CONSOLE_MODEL,messages:[{role:'user',content:'fixture'}],max_tokens:64,stream:true,extra:'not forwarded'};
 await t.respond('valera',body);assert.equal(calls,1);await assert.rejects(t.respond('valera',body));assert.equal(calls,1);
 await t.respond('specialist',body);assert.deepEqual(t.usage(),{input_tokens:28,output_tokens:14,cost_usd:.004});
 controller.abort();await assert.rejects(t.respond('specialist',body));
});
test('HTTP failures are classified without echoing upstream body; no next stage',async()=>{
 for(const [status,code] of [[401,'AUTH'],[403,'AUTH'],[429,'RATE_LIMIT'],[503,'PROVIDER_UNAVAILABLE']]){
  let calls=0;const t=consoleResponder('key',{send:async()=>{calls++;return new Response('PRIVATE',{status});}});
  await assert.rejects(t.respond('valera',{model:CONSOLE_MODEL,messages:[{role:'user',content:'x'}],max_tokens:64,stream:true}),e=>e.code===code&&!e.message.includes('PRIVATE'));
  await assert.rejects(t.respond('specialist',{}));assert.equal(calls,1);
 }
});
