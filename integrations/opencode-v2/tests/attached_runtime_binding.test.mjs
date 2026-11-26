import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {createAttachedStageLedger,ATTACHED_TRIAL_MODEL as model} from '../src/attached-stage-ledger.mjs';
import {runBoundAttachedRuntime} from '../src/attached-runtime-binding.mjs';
import {buildProfile} from '../src/attached-policy-profile.mjs';
import {POLICY_ID} from '../src/server-policy.mjs';
import {ROLES} from '../src/profile.mjs';
import {OBJECTIVE} from '../src/trial-fixture.mjs';
const usage={input_tokens:10,output_tokens:5,cost_usd:0};
const request={model,role:'backend',prompt:'synthetic source',coordination:{objective:OBJECTIVE,scope:['calculation.py']},output_token_allowance:2048,token_allowance:100,bridge_timeout_ms:10000};
function fixture(t,fault){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'potato-attached-stage-')),file=path.join(root,'ledger.sqlite');
 const ledger=createAttachedStageLedger(new DatabaseSync(file));
 t.after(()=>{ledger.close();fs.rmSync(root,{recursive:true,force:true});});
 const directory='/fixture',profile=buildProfile(directory,model),calls=[],audit=['ready'],sessions=new Map();
 const snapshot={plugins:{data:[{id:POLICY_ID,source:{type:'local',path:profile.plugin},state:{status:'active'}}]},
  agents:{data:ROLES.map(id=>({...profile.config.agents[id],id,model:profile.ref}))},
  models:{data:[{...profile.ref,enabled:true,cost:[{input:0,output:0,cache:{read:0,write:0}}],
    limit:{output:1024},capabilities:{tools:false},variants:[]}]}};
 const raw={server:{info:async()=>({version:'2.4.1'})},
  ...Object.fromEntries([['plugin','plugins'],['agent','agents'],['model','models']].map(([k,v])=>[k,{list:async()=>snapshot[v]}])),
  session:{create:async x=>{const id='s'+sessions.size;sessions.set(id,x.agent);return {id};},
   prompt:async({sessionID})=>{
    const role=sessions.get(sessionID);calls.push(role);
    const saved=ledger.status().stages.find(s=>s.role===role);
    assert.equal(saved.state,'DISPATCHING');
    if(fault===role)throw Error('PRIVATE_ERROR');
    audit.push('model:'+role,'http:'+role);
   },interrupt:async()=>{}},
  experimental:{session:{wait:async()=>{}}},
  message:{list:async({sessionID,cursor})=>{
   if(cursor)return {data:[]};
   const role=sessions.get(sessionID),value=role==='valera-ceo'?{owner:'backend',reason:'synthetic plan'}:
     {edits:[{path:'calculation.py',content:'replacement'}],summary:'synthetic edit'};
   return {cursor:{next:'end'},data:[{type:'user'},{type:'assistant',agent:role,model:profile.ref,finish:'stop',
    time:{completed:1},tokens:{input:10,output:5},cost:0,content:[{type:'text',text:JSON.stringify(value)}]},
    {type:'idle',outcome:'succeeded'}]};
  }}};
 const transport={directory,model,password:'fixture',profile,readAudit:()=>[...audit],
  verifyProfile:async()=>{},clientFactory:()=>raw};
 return {ledger,file,calls,transport};
}
test('bound runtime uses real composition with injected server and durable per-stage reservations',async t=>{
 const f=fixture(t);
 const result=await runBoundAttachedRuntime(request,{...f,admit:async scope=>{
  assert.equal(scope.model,model);assert.equal(scope.output_limit,1024);return true;
 }});
 assert.deepEqual(f.calls,['valera-ceo','backend']);
 assert.equal(result.usage.output_tokens,10);
 assert.equal(f.ledger.status().attempt.state,'VALIDATED');
 await assert.rejects(()=>runBoundAttachedRuntime(request,{...f,admit:async()=>true}),/ATTACHED_SLOT_ALREADY_USED/);
 assert.equal(f.calls.length,2);
});
test('no admission or invalid bounds prevents reservation and server calls',async t=>{
 const f=fixture(t);
 for(const admit of [undefined,async()=>false,async()=>({approved:true})])
  await assert.rejects(()=>runBoundAttachedRuntime(request,{...f,admit}));
 for(const output_token_allowance of [2,1024,2047,4096])
  await assert.rejects(()=>runBoundAttachedRuntime({...request,output_token_allowance},{...f,admit:async()=>true}));
 assert.equal(f.ledger.status().attempt,null);assert.deepEqual(f.calls,[]);
});
test('uncertain backend keeps first stage and blocks replay after reopening',async t=>{
 const f=fixture(t,'backend');
 await assert.rejects(()=>runBoundAttachedRuntime(request,{...f,admit:async()=>true}),/ATTACHED_RUNTIME_OUTCOME_UNKNOWN/);
 const reopened=createAttachedStageLedger(new DatabaseSync(f.file));
 try{
  const s=reopened.status();
  assert.equal(s.attempt.state,'UNKNOWN');assert.equal(s.stages[0].state,'VALIDATED');
  assert.equal(s.stages[1].state,'DISPATCHING');assert.equal(s.stages[1].cost_usd,null);
  assert.throws(()=>reopened.reserve(model,100,1024,'0'.repeat(64)));
 }finally{reopened.close();}
});
test('first-stage error never sends specialist; restart retains unknown slot',async t=>{
 const f=fixture(t,'valera-ceo');
 await assert.rejects(()=>runBoundAttachedRuntime(request,{...f,admit:async()=>true}),/ATTACHED_RUNTIME_OUTCOME_UNKNOWN/);
 assert.deepEqual(f.calls,['valera-ceo']);assert.equal(f.ledger.status().attempt.state,'UNKNOWN');
 assert.equal(f.ledger.status().stages.length,1);
});
test('stage journal rejects bad sequence, unknown usage and cumulative overflow',t=>{
 const f=fixture(t),l=f.ledger;l.reserve(model,20,1024,'0'.repeat(64));
 assert.throws(()=>l.beforePrompt('backend'));l.beforePrompt('valera-ceo');
 assert.throws(()=>l.beforePrompt('valera-ceo'));
 assert.throws(()=>l.validatedStage('valera-ceo',{...usage,cost_usd:null}));
 l.validatedStage('valera-ceo',usage);l.beforePrompt('backend');
 assert.throws(()=>l.validatedStage('backend',usage));
 assert.equal(l.finish({usage:{input_tokens:20,output_tokens:10,cost_usd:0}}),'UNKNOWN');
});
