import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {auditSequence,readAudit,recordAudit,assertAudit} from '../src/server-audit.mjs';
import {probeArgs,probeUsage,runNativeProbe,PROBE_CAP} from '../src/server-inference.mjs';
import {responseShape,auditShape,errorCategory} from '../src/server-inference-diagnostics.mjs';
const model='opencode/test-free',ref={providerID:'opencode',id:'test-free'},seq=auditSequence('backend');
test('probe requires explicit external consent and a free native model',()=>{
 for(const args of [[],[model],[model,'--auto'],['opencode/paid','--confirm-external-inference'],[model,'--confirm-external-inference','extra']])assert.throws(()=>probeArgs(args));
 assert.equal(probeArgs([model,'--confirm-external-inference']),model);
});
test('audit is ordered, bounded and denies duplicate or unexpected dispatch',()=>{
 const d=fs.mkdtempSync(path.join(os.tmpdir(),'potato-audit-test-')),file=path.join(d,'audit');
 try{
  fs.writeFileSync(file,'',{mode:0o600});
  for(const e of seq)recordAudit(file,'backend',e);
  assertAudit(readAudit(file),'backend',5);
  assert.throws(()=>recordAudit(file,'backend',seq[4]),/DENIED/);
  assert.throws(()=>assertAudit(readAudit(file),'backend',5));
  assert.throws(()=>recordAudit(file,'backend',seq[1]),/DENIED/);
 }finally{fs.rmSync(d,{recursive:true,force:true});}
});
test('usage rejects unknown cost, nonzero cost, invalid or excessive token count',()=>{
 const info={tokens:{input:10,output:5},cost:0};
 assert.deepEqual(probeUsage(info),{input_tokens:10,output_tokens:5,cost_usd:0});
 for(const bad of [{...info,cost:undefined},{...info,cost:.01},{...info,tokens:{input:1,output:0}},{...info,tokens:{input:1,output:PROBE_CAP+1}},{...info,tokens:{input:-1,output:1}}])assert.throws(()=>probeUsage(bad));
});
function fake({badPlan=false,badCost=false,badTool=false,badAudit=false,badFinal=false,timeout=false,badProposal=false,preflight=false,variant=undefined}={}){
 const calls=[],audit=['ready'];let closed=0,interrupts=0,role,sessionID;
 const server={directory:'/private',readAudit:()=>[...audit],close:async()=>{closed++;return badFinal?[...audit,'violation']:[...audit];},client:{
  session:{create:async x=>{role=x.agent;sessionID=role;return {id:role};},prompt:async()=>{calls.push(role);audit.push('model:'+role,'http:'+role);if(badAudit)audit.push('violation');if(timeout)throw Error('private provider text');},interrupt:async()=>{interrupts++;}},
  experimental:{session:{wait:async()=>{}}},
  message:{list:async x=>x.cursor?{data:[]}:{cursor:{next:'next'},data:[{type:'user'},{type:'assistant',agent:role,model:{...ref,variant},finish:'stop',time:{completed:1},tokens:{input:10,output:5},cost:badCost?1:0,content:[{type:badTool?'tool':'text',text:JSON.stringify(role==='valera-ceo'?{owner:badPlan?'qa':'backend',reason:'test'}:{edits:[{path:'probe.txt',content:badProposal?'wrong':'potato-probe-ok\n'}],summary:'test'})}]}]}}
 }};
 return {calls,counts:()=>({closed,interrupts}),opts:{model,launch:async()=>server,awaitPolicy:async()=>{if(preflight)throw Error('preflight');}}};
}
test('two separate sessions pass only after assignment, inert proposal, usage and final audit',async()=>{
 const f=fake(),r=await runNativeProbe(f.opts);
 assert.equal(r.status,'PASS');assert.deepEqual(f.calls,['valera-ceo','backend']);
 assert.equal(r.admitted_http_hooks,2);assert.equal(r.runtime_admission,false);assert.equal(r.billing_verified,false);
 assert.deepEqual(r.usage,{input_tokens:20,output_tokens:10,cost_usd:0});assert.equal(f.counts().closed,1);
});
test('preflight and any first-stage failure prevent specialist dispatch',async()=>{
 for(const options of [{preflight:true},{badPlan:true},{badCost:true},{badTool:true},{badAudit:true},{timeout:true}]){
  const f=fake(options),r=await runNativeProbe(f.opts);
  assert.equal(r.status,'HOLD');assert.equal(f.calls.length,options.preflight?0:1);
  assert.equal(r.external_inference,options.preflight?false:'unknown');assert.equal(f.counts().closed,1);
  assert.ok(!JSON.stringify(r).includes('private provider text'));
 }
});
test('wrong proposal or late policy violation never passes',async()=>{
 for(const options of [{badFinal:true},{badProposal:true}]){
  const f=fake(options),r=await runNativeProbe(f.opts);
  assert.equal(r.status,'HOLD');assert.equal(f.calls.length,2);assert.equal(f.counts().closed,1);
 }
});

test('failed response diagnostics distinguish usage, assistant contract and audit without leaking content',async()=>{
 for(const [options,check] of [[{badCost:true},'usage'],[{badTool:true},'assistant_contract'],[{badAudit:true},'audit_after_response'],[{timeout:true},'dispatch']]){
  const f=fake(options),r=await runNativeProbe(f.opts);
  assert.equal(r.status,'HOLD');assert.equal(r.diagnostics.failure.check,check);
  assert.equal(r.diagnostics.audit.http_hooks,1);
  assert.equal(r.external_inference,'unknown');assert.equal(f.calls.length,1);
  assert.ok(!JSON.stringify(r).includes('private provider text'));
 }
});
test('diagnostic projection never emits raw provider data or unknown event labels',()=>{
 const secret='DO_NOT_LEAK_PRIVATE_TEXT';
 const d=responseShape([{type:secret},{type:'assistant',agent:secret,model:{id:secret},finish:secret,content:[{type:secret,text:secret}],error:{message:secret,status:429},cost:secret}], 'valera-ceo',ref);
 assert.equal(d.counts.other,1);assert.equal(d.assistant.error,'RATE_LIMIT');
 assert.equal(d.assistant.finish,'ABSENT_OR_OTHER');assert.equal(d.assistant.parts_valid,false);
 assert.ok(!JSON.stringify(d).includes(secret));
 assert.deepEqual(auditShape(['ready',secret],'backend'),{ready:true,model_hooks:0,http_hooks:0,violation:false,violation_reason:null,valid_prefix:false});
 assert.equal(errorCategory(Error(secret)),'REJECTED');
});

test('no-assistant idle error and named denial are projected without provider text',()=>{
 const secret='PRIVATE_PROVIDER_MESSAGE';
 const d=responseShape([{type:'user'},{type:'idle',outcome:'failed',error:{type:'provider.no-route',message:secret}}],'valera-ceo',ref);
 assert.equal(d.counts.assistant,0);
 assert.deepEqual(d.idle,{outcome:'failed',error:'NO_ROUTE'});
 assert.deepEqual(auditShape(['ready','violation:resolve_model'],'backend'),{ready:true,model_hooks:0,http_hooks:0,violation:true,violation_reason:'resolve_model',valid_prefix:false});
 assert.ok(!JSON.stringify(d).includes(secret));
});
test('audit preserves first specific violation and never echoes unknown input',()=>{
 const d=fs.mkdtempSync(path.join(os.tmpdir(),'potato-audit-reason-')),file=path.join(d,'audit');
 try{
  fs.writeFileSync(file,'',{mode:0o600});
  recordAudit(file,'backend','ready');recordAudit(file,'backend','violation:resolve_role');
  recordAudit(file,'backend','violation:retry');
  assert.throws(()=>recordAudit(file,'backend','PRIVATE_LABEL'),/DENIED/);
  assert.deepEqual(readAudit(file),['ready','violation:resolve_role']);
  assert.throws(()=>assertAudit(readAudit(file),'backend',1));
 }finally{fs.rmSync(d,{recursive:true,force:true});}
});
test('offline runner cannot proceed to specialist even with a successful fake response',async()=>{
 const f=fake(),r=await runNativeProbe({...f.opts,offline:true});
 assert.equal(r.status,'HOLD');assert.equal(r.external_inference,false);
 assert.equal(r.offline_diagnostic,true);assert.deepEqual(f.calls,['valera-ceo']);
});

test('identity denial labels are preserved in the audit without arbitrary strings',()=>{
 const d=fs.mkdtempSync(path.join(os.tmpdir(),'potato-audit-identity-')),file=path.join(d,'audit');
 try{
  for(const code of ['resolve_provider_mismatch','resolve_id_qualified','resolve_variant_null','resolve_variant_empty','resolve_variant_default','resolve_variant_named','resolve_variant_type']){
   fs.writeFileSync(file,'',{mode:0o600});recordAudit(file,'backend','ready');recordAudit(file,'backend','violation:'+code);
   const a=auditShape(readAudit(file),'backend');
   assert.equal(a.violation_reason,code);assert.equal(a.valid_prefix,false);
   assert.throws(()=>assertAudit(readAudit(file),'backend',1));
  }
 }finally{fs.rmSync(d,{recursive:true,force:true});}
});

test('native response admits exact default variant but rejects all other explicit variants',async()=>{
 const good=fake({variant:'default'}),passed=await runNativeProbe(good.opts);
 assert.equal(passed.status,'PASS');assert.deepEqual(good.calls,['valera-ceo','backend']);
 assert.equal(passed.diagnostics.response.assistant.variant_absent,false);
 assert.equal(passed.diagnostics.response.assistant.variant_base,true);
 for(const variant of [null,'','Default','default ','high',0]){
  const bad=fake({variant}),r=await runNativeProbe(bad.opts);
  assert.equal(r.status,'HOLD');assert.equal(r.diagnostics.failure.check,'variant');
  assert.equal(r.diagnostics.response.assistant.variant_base,false);assert.deepEqual(bad.calls,['valera-ceo']);
 }
});
