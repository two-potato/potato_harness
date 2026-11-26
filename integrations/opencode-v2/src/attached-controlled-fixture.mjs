// Controlled transport only. No OpenCode SDK or network forwarding.
// Uses the actual attached composition after consuming the host handoff.
import fs from 'node:fs';
import path from 'node:path';
import {Database} from 'bun:sqlite';
import {ROLES} from './profile.mjs';
import {consumeAttachedHandoff} from './attached-handoff.mjs';
import {buildProfile} from './attached-policy-profile.mjs';
import {POLICY_ID} from './server-policy.mjs';
import {runBoundAttachedRuntime} from './attached-runtime-binding.mjs';
import {createAttachedStageLedger,ATTACHED_TRIAL_MODEL as model} from './attached-stage-ledger.mjs';

export async function runAttachedControlledFixture(envelope,{onPhase,home}){
 const request=consumeAttachedHandoff(envelope,'attached-free-fixture');
 const directory=path.join(home,'fixture-location'),profile=buildProfile(directory,model);
 const ledgerFile=path.join(envelope.state,'attached-controlled-ledger.sqlite3');
 fs.closeSync(fs.openSync(ledgerFile,'wx',0o600));
 const ledger=createAttachedStageLedger(new Database(ledgerFile));
 const audit=['ready'],sessions=new Map();
 const snapshot={plugins:{data:[{id:POLICY_ID,source:{type:'local',path:profile.plugin},state:{status:'active'}}]},
  agents:{data:ROLES.map(id=>({...profile.config.agents[id],id,model:profile.ref}))},
  models:{data:[{...profile.ref,enabled:true,cost:[{input:0,output:0,cache:{read:0,write:0}}],
   limit:{output:1024},capabilities:{tools:false},variants:[]}]}};
 const raw={server:{info:async()=>({version:'2.4.1'})},
  ...Object.fromEntries([['plugin','plugins'],['agent','agents'],['model','models']].map(([k,v])=>[k,{list:async()=>snapshot[v]}])),
  session:{create:async x=>{const id='s'+sessions.size;sessions.set(id,x.agent);return {id};},
   prompt:async({sessionID})=>{
    const role=sessions.get(sessionID);
    if(ledger.status().stages.find(s=>s.role===role)?.state!=='DISPATCHING')throw Error('UNRESERVED_STAGE');
    audit.push('model:'+role,'http:'+role);
   },interrupt:async()=>{}},
  experimental:{session:{wait:async()=>{}}},
  message:{list:async({sessionID,cursor})=>{
   if(cursor)return {data:[]};
   const role=sessions.get(sessionID),value=role==='valera-ceo'?{owner:'backend',reason:'controlled assignment'}:
    {edits:[{path:'calculation.py',content:'def subtotal(unit_cents, quantity):\n    return unit_cents * quantity\n'}],summary:'controlled proposal'};
   return {cursor:{next:'end'},data:[{type:'user'},{type:'assistant',agent:role,model:profile.ref,finish:'stop',
    time:{completed:1},tokens:{input:10,output:5},cost:0,content:[{type:'text',text:JSON.stringify(value)}]},
    {type:'idle',outcome:'succeeded'}]};
  }}};
 try{
  return await runBoundAttachedRuntime(request,{ledger,onPhase,admit:async()=>true,
   transport:{directory,model,password:'controlled-fixture',profile,readAudit:()=>[...audit],
    verifyProfile:async()=>{},clientFactory:()=>raw,send:async()=>{throw Error('NO_NETWORK');}}});
 }finally{ledger.close();}
}
