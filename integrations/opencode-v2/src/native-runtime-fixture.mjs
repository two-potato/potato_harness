// In-process native client contract fixture. No SDK, subprocess, HTTP or network.
import {nativeConfig,modelRef,serverPolicy,POLICY_ID,isFreeModel} from './server-policy.mjs';
import {ROLES} from './profile.mjs';
import {assertAudit} from './server-audit.mjs';
import {NATIVE_FIXTURE_MODEL} from './server-inference.mjs';
export async function launchNativeFixture({model,worker,maxOutput,audit,offline},{fault,onPrompt=()=>{}}={}){
 if(model!==NATIVE_FIXTURE_MODEL||worker!=='backend'||audit!==true||offline!==false)throw Error('NATIVE_FIXTURE_ONLY');
 const ref=modelRef(model),config=nativeConfig(model,maxOutput,'/synthetic-policy'),events=[],hooks={},sessions=new Map();
 let closed=false;
 const register=(name,fn)=>{hooks[name]=fn;return {dispose:async()=>{delete hooks[name];}};};
 const ctx={agent:{transform:f=>register('agent',f)},model:{transform:f=>register('model',f)},tool:{transform:f=>register('tools',f)},permission:{hook:(n,f)=>register(n,f)},session:{hook:(n,f)=>register(n,f)}};
 const dispose=await serverPolicy({id:POLICY_ID,roles:ROLES,definitions:config.agents,ref,maxOutput,worker,freeCheck:isFreeModel,record:e=>events.push(e)}).setup(ctx);
 const lookup=id=>{if(closed||!sessions.has(id))throw Error('FIXTURE_SESSION');return sessions.get(id);};
 return {directory:'/synthetic-native-client',readAudit:()=>[...events],
  close:async()=>{if(closed)throw Error('FIXTURE_DOUBLE_CLOSE');closed=true;await dispose();return fault==='final_audit'?[...events,'violation:retry']:[...events];},
  client:{session:{
   create:async x=>{
    if(closed||x.model.providerID!==ref.providerID||x.model.id!==ref.id||x.location.directory!=='/synthetic-native-client'||JSON.stringify(x.permissions)!=='[{"action":"*","resource":"*","effect":"deny"}]')throw Error('FIXTURE_SESSION_CONFIG');
    const id='fixture-'+sessions.size;sessions.set(id,{agent:x.agent,prompted:false});return {id};
   },
   prompt:async({sessionID,text})=>{
    const session=lookup(sessionID);if(session.prompted||typeof text!=='string')throw Error('FIXTURE_PROMPT');
    session.prompted=true;onPrompt(session.agent);
    const e={sessionID,agent:session.agent,kind:'primary',model:{...ref,variant:'default'}};
    hooks['experimental.model.resolve'](e);hooks['model.request'](e);
    // A Web Request object only; never executed or passed to fetch.
    hooks['http.request']({...e,request:new Request('https://potato-native-fixture.invalid/v1/chat/completions',{method:'POST',headers:{'content-type':'application/json'},body:'{}'})});
    const first=session.agent==='valera-ceo';
    const error=first&&fault==='rate_limit'?{type:'provider.rate-limit',message:'PRIVATE_PROVIDER_TEXT'}:undefined;
    if(error||first&&fault==='audit')hooks.retry({});
    const value=first?{owner:fault==='assignment'?'qa':'backend',reason:'synthetic routing'}:
     {edits:[{path:fault==='scope'?'outside.py':'calculation.py',content:'def subtotal(unit_cents, quantity):\n    return unit_cents * quantity\n'}],summary:'synthetic native runtime proposal'};
    session.messages=[{type:'user'},{type:'assistant',agent:session.agent,model:{...ref,variant:'default'},finish:error?'error':'stop',time:{completed:1},tokens:{input:10,output:10},cost:first&&fault==='unknown_cost'?undefined:0,error,content:error?[]:[{type:'text',text:JSON.stringify(value)}]}];
   },
   interrupt:async({sessionID})=>{lookup(sessionID);}
  },experimental:{session:{wait:async({sessionID})=>{if(!lookup(sessionID).messages)throw Error('FIXTURE_NOT_READY');}}},
  message:{list:async({sessionID,cursor})=>{const session=lookup(sessionID);return cursor?{data:[]}:{data:session.messages,cursor:{next:'fixture-tail'}};}}}};
}
export async function awaitNativeFixture(server){assertAudit(server.readAudit(),'backend',1);}
