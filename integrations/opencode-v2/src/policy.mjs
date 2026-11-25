import {FIXTURE_URL,MODEL_REF,deny,candidateConfig} from './contracts.mjs';
import {ROLES} from '../../opencode/src/profile.mjs';

// Never forward to the network. One synthetic HTTP response per authorized stage.
export function fixtureTransport(respond,maxOutput){
 let phase=null,calls=0,violation=false,reason='NONE',blockedHost='none',blockedPhase='none';
 const fail=code=>{violation=true;if(reason==='NONE')reason=code;throw Error(code);};
 return {
  begin(next){if(phase!==null||!['valera','specialist'].includes(next))throw Error('INVALID_FIXTURE_STAGE');phase=next;calls=0;},
  end(){const n=calls;phase=null;if(violation||n!==1)throw Error('FIXTURE_REQUEST_BOUNDARY: '+reason+'; calls='+n+'; blocked_host='+blockedHost+'; blocked_phase='+blockedPhase);},
  get violated(){return violation;},
  async fetch(input,init){
   const req=new Request(input,init);
   if(req.url!==FIXTURE_URL){const u=new URL(req.url);if(reason==='NONE'){blockedHost=/^[a-z0-9.-]{1,128}$/.test(u.hostname)?u.hostname:'other';blockedPhase=phase??'startup';}fail(u.origin==='https://potato-fixture.invalid'?'FIXTURE_WRONG_PATH':u.hostname==='opencode.ai'?'BLOCKED_CONSOLE':u.hostname==='models.dev'?'BLOCKED_CATALOG':'BLOCKED_OTHER_ORIGIN');}
   if(req.method!=='POST')fail('FIXTURE_METHOD');
   if(!phase)fail('FIXTURE_BEFORE_ADMISSION');
   if(calls!==0)fail('FIXTURE_DUPLICATE');
   calls++;
   const body=await req.json();
   const cap=body.max_tokens??body.max_completion_tokens;
   if(!Number.isSafeInteger(cap)||cap<1||cap>maxOutput||body.model!==MODEL_REF.id||!Array.isArray(body.messages)||(body.tools!==undefined&&(!Array.isArray(body.tools)||body.tools.length!==0))){
    fail(!Number.isSafeInteger(cap)||cap<1||cap>maxOutput?'FIXTURE_OUTPUT_CAP':body.model!==MODEL_REF.id?'FIXTURE_MODEL':!Array.isArray(body.messages)?'FIXTURE_MESSAGES':'FIXTURE_TOOLS');
   }
   return respond(phase,body);
  }
 };
}
// SDK starts location plugins asynchronously. Wait for the actual transformed
// roster, not just for a setup callback or a default agent name.
export function safeRoster(agents){
 if(!Array.isArray(agents)||agents.length!==ROLES.length)return false;
 const ids=new Set(agents.map(a=>a?.id));
 return ROLES.every(role=>ids.has(role))&&agents.every(a=>
  a.model?.providerID===MODEL_REF.providerID&&a.model?.id===MODEL_REF.id&&
  a.steps===1&&a.mode===(a.id==='valera-ceo'?'primary':'subagent')&&
  Array.isArray(a.permissions)&&a.permissions.length>0&&a.permissions.every(r=>r.effect==='deny')&&
  typeof a.system==='string'&&a.system.length>0
 );
}
export async function awaitPolicy(read,observe,{now=()=>performance.now(),pause=()=>new Promise(r=>setTimeout(r,50)),timeout=10000}={}){
 const deadline=now()+timeout;
 do{
  const agents=await read();
  if(observe.ready&&safeRoster(agents?.data))return;
  await pause();
 }while(now()<deadline);
 throw Error('V2_PLUGIN_NOT_ACTIVE');
}
export async function awaitModel(read,maxOutput,{now=()=>performance.now(),pause=()=>new Promise(r=>setTimeout(r,50)),timeout=10000}={}){
 const deadline=now()+timeout;
 do{
  const result=await read();
  if(result?.data?.some(m=>m.providerID===MODEL_REF.providerID&&m.id===MODEL_REF.id&&m.enabled===true&&m.limit?.output===maxOutput&&m.capabilities?.tools===false))return;
  await pause();
 }while(now()<deadline);
 throw Error('V2_MODEL_NOT_READY');
}
export function restrictivePlugin(observed,maxOutput){
 const definitions=candidateConfig(maxOutput).agents;
 return {id:'potato-harness-v2-candidate',async setup(ctx){
  const registrations=[];
  registrations.push(await ctx.agent.transform(editor=>{
   for(const agent of editor.list())if(!ROLES.includes(agent.id))editor.remove(agent.id);
   editor.default('valera-ceo');
   for(const role of ROLES)editor.update(role,a=>{
    const definition=definitions[role];
    a.permissions=deny();a.steps=1;a.model={...MODEL_REF};
    a.system=definition.system;a.description=definition.description;a.mode=definition.mode;
   });
  }));
  registrations.push(await ctx.tool.transform(editor=>{for(const tool of editor.list())editor.remove(tool.id);}));
  registrations.push(await ctx.permission.hook('evaluate',event=>{event.effect='deny';}));
  registrations.push(await ctx.session.hook('context',event=>{
   event.tools={};event.options.maxTokens=Math.min(maxOutput,event.options.maxTokens??maxOutput);
  }));
  registrations.push(await ctx.session.hook('title',event=>{event.result='Potato bounded fixture';}));
  registrations.push(await ctx.session.hook('retry',event=>{
   event.decision={retry:false};observed.retries++;
  }));
  observed.ready=true;
  return async()=>{for(const registration of registrations.reverse())await registration.dispose();};
 }};
}
