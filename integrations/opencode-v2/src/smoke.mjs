// Real embedded SDK, synthetic HTTP response only. No external keys or network fetch.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
const home=fs.mkdtempSync(path.join(os.tmpdir(),'potato-v2-home-'));
for(const key of Object.keys(process.env))if(!['PATH','LANG','TMPDIR'].includes(key))delete process.env[key];
Object.assign(process.env,{HOME:home,XDG_CONFIG_HOME:path.join(home,'config'),XDG_DATA_HOME:path.join(home,'data'),XDG_CACHE_HOME:path.join(home,'cache'),DO_NOT_TRACK:'1'});
process.chdir(home);
try{
 const {OpenCode}=await import('@opencode/sdk');
 const {runCandidate}=await import('./adapter.mjs');
 const request={role:'backend',model:'fixture/test',prompt:'Fix fixture source.',coordination:{objective:'Fix fixture',scope:['a.py']},output_token_allowance:128};
 const calls=[];
 const success=(phase,body)=>{
  calls.push(phase);
  const content=JSON.stringify(phase==='valera'?{owner:'backend',reason:'fixture routing'}:{edits:[{path:'a.py',content:'result = 42\n'}],summary:'fixture proposal'});
  const base={id:'fixture',created:1,model:'test'};
  if(body.stream){
   const chunk=(delta,finish_reason,usage)=>'data: '+JSON.stringify({...base,object:'chat.completion.chunk',choices:[{index:0,delta,finish_reason}],...(usage?{usage}:{})})+'\n\n';
   return new Response(chunk({role:'assistant',content},null)+chunk({},'stop',{prompt_tokens:10,completion_tokens:10,total_tokens:20})+'data: [DONE]\n\n',{headers:{'Content-Type':'text/event-stream'}});
  }
  return Response.json({...base,object:'chat.completion',choices:[{index:0,message:{role:'assistant',content},finish_reason:'stop'}],usage:{prompt_tokens:10,completion_tokens:10,total_tokens:20}});
 };
 const result=await runCandidate(request,{OpenCode,respond:success});
 assert.deepEqual(calls,['valera','specialist']);assert.equal(result.edits[0].path,'a.py');
 assert.ok(result.usage.input_tokens>0&&result.usage.output_tokens>0);
 for(const status of [401,429,503]){
  const rejected=[];const observe={ready:false,retries:0};
  await assert.rejects(runCandidate(request,{OpenCode,observe,respond:phase=>{rejected.push(phase);return Response.json({error:{message:'fixture rejected',type:'fixture_error',code:'fixture_error'}},{status,headers:{'Retry-After':'1'}});}}));
  assert.deepEqual(rejected,['valera']);
  assert.ok(observe.ready);
  if(status===429||status===503)assert.ok(observe.retries>0,'real SDK retry hook must be observed');
 }
 console.log(JSON.stringify({status:'PASS',layer:'real-v2-sdk-synthetic-http',external_inference:false,omo:false,provider_requests:5}));
}finally{fs.rmSync(home,{recursive:true,force:true});}
