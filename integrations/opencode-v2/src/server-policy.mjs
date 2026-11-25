// Policy for a dedicated official OpenCode CLI server, not the operator's existing server.
import {candidateConfig} from './contracts.mjs';
import {ROLES} from './profile.mjs';
import {auditSequence,auditViolation,readAudit,recordAudit} from './server-audit.mjs';

export const POLICY_ID='potato-harness-native-server';
export function modelRef(name){
 if(typeof name!=='string'||!/^opencode\/[a-z0-9][a-z0-9.-]{0,126}-free$/.test(name))throw Error('FREE_MODEL_REQUIRED');
 return {providerID:'opencode',id:name.slice(9)};
}
// This function is also embedded into the self-contained server plugin.
export function isFreeModel(m,ref){
 return m?.providerID===ref.providerID&&m.id===ref.id&&m.enabled===true&&
  m.status!=='deprecated'&&Array.isArray(m.cost)&&m.cost.length>0&&
  m.cost.every(c=>c?.input===0&&c.output===0&&c.cache?.read===0&&c.cache?.write===0)&&
  Number.isSafeInteger(m.limit?.output)&&m.limit.output>0;
}
export function nativeConfig(model,maxOutput,plugin){
 const ref=modelRef(model);
 if(!Number.isSafeInteger(maxOutput)||maxOutput<1||maxOutput>2048)throw Error('INVALID_OUTPUT_CAP');
 const config=candidateConfig(maxOutput,{requestModel:model,modelRef:ref});
 // Retain the native OpenCode provider; never override price, URL, API key, or client identity.
 delete config.providers;
 config.plugins=[...config.plugins,plugin];
 config.policies=[
  {action:'tool.use',resource:'*',effect:'deny'},
  {action:'mcp.use',resource:'*',effect:'deny'},
  {action:'websearch.use',resource:'*',effect:'deny'}
 ];
 return config;
}
// Self-contained: the CLI loads this from a private generated directory.
export function serverPolicy({id,roles,definitions,ref,maxOutput,worker,freeCheck,record=()=>{},offline=false}){
 const deny=()=>[{action:'*',resource:'*',effect:'deny'}];
 // Diagnostic labels are fixed; never include an observed identifier or variant.
 const mismatch=m=>{
  if(!m||typeof m!=='object'||Array.isArray(m))return 'resolve_model_shape';
  if(m.providerID!==ref.providerID)return typeof m.providerID!=='string'?'resolve_provider_missing_or_type':'resolve_provider_mismatch';
  if(m.id!==ref.id)return typeof m.id!=='string'?'resolve_id_missing_or_type':
   m.id===ref.providerID+'/'+ref.id?'resolve_id_qualified':'resolve_id_mismatch';
  if(m.variant!==undefined)return m.variant===null?'resolve_variant_null':
   m.variant===''?'resolve_variant_empty':m.variant==='default'?'resolve_variant_default':
   typeof m.variant==='string'?'resolve_variant_named':'resolve_variant_type';
  return null;
 };
 const same=m=>mismatch(m)===null;
 const resolved=new Map(),sent=new Set(),http=new Set();
 let admitted=0;
 const allowed=(event)=>same(event.model)&&resolved.has(event.sessionID)&&resolved.get(event.sessionID)===event.agent&&event.kind==='primary';
 return {id,async setup(ctx){
  const registrations=[];
  registrations.push(await ctx.agent.transform(editor=>{
   for(const agent of editor.list())if(!roles.includes(agent.id))editor.remove(agent.id);
   editor.default('valera-ceo');
   for(const role of roles)editor.update(role,a=>{
    const d=definitions[role];
    a.permissions=deny();a.steps=1;a.model={...ref};a.system=d.system;a.description=d.description;a.mode=d.mode;
   });
  }));
  registrations.push(await ctx.model.transform(editor=>{
   for(const m of editor.list()){
    if(!freeCheck(m,ref)){editor.remove(m.providerID,m.id);continue;}
    editor.update(m.providerID,m.id,d=>{
     d.capabilities={...d.capabilities,tools:false};d.variants=[];
     d.limit={...d.limit,output:Math.min(d.limit.output,maxOutput)};
    });
   }
   if(editor.get(ref.providerID,ref.id))editor.default.set(ref.providerID,ref.id);
  }));
  registrations.push(await ctx.tool.transform(editor=>{for(const t of editor.list())editor.remove(t.id);}));
  registrations.push(await ctx.permission.hook('evaluate',e=>{e.effect='deny';record('violation:permission');}));
  registrations.push(await ctx.session.hook('title',e=>{e.result='Potato bounded proposal';}));
  registrations.push(await ctx.session.hook('retry',e=>{e.decision={retry:false};record('violation:retry');}));
  registrations.push(await ctx.session.hook('experimental.model.resolve',e=>{
   // Resolution for the title can precede the title hook. Any title HTTP request
   // is still rejected by the model.request/http.request guards below.
   if(e.kind==='title'&&same(e.model))return;
   const role=admitted===0?'valera-ceo':admitted===1?worker:null;
   const failure=e.kind!=='primary'?'resolve_kind':mismatch(e.model)??(
    typeof e.sessionID!=='string'||!e.sessionID?'resolve_session':
    role===null||e.agent!==role?'resolve_role':resolved.has(e.sessionID)?'resolve_duplicate':null);
   if(failure){
    e.model={providerID:'potato-denied',id:'denied'};record('violation:'+failure);return;
   }
   admitted++;resolved.set(e.sessionID,e.agent);
  }));
  registrations.push(await ctx.session.hook('context',e=>{
   e.tools={};e.options.maxTokens=Math.min(maxOutput,e.options.maxTokens??maxOutput);
  }));
  registrations.push(await ctx.session.hook('model.request',e=>{
   if(!allowed(e)||sent.has(e.sessionID)){record('violation:'+(allowed(e)?'model_duplicate':'model_scope'));throw Error('MODEL_REQUEST_DENIED');}
   if(offline){record('violation:offline_stop');throw Error('OFFLINE_MODEL_REQUEST_DENIED');}
   record('model:'+e.agent);sent.add(e.sessionID);
  }));
  registrations.push(await ctx.session.hook('http.request',e=>{
   if(!allowed(e)||!sent.has(e.sessionID)||http.has(e.sessionID)||offline){record('violation:'+(offline?'offline_http':http.has(e.sessionID)?'http_duplicate':'http_scope'));throw Error('HTTP_REQUEST_DENIED');}
   record('http:'+e.agent);http.add(e.sessionID);
  }));
  registrations.push(await ctx.session.hook('experimental.ws.handshake',()=>{record('violation:websocket');throw Error('WEBSOCKET_DENIED');}));
  record('ready');
  return async()=>{for(const reg of registrations.reverse())await reg.dispose();};
 }};
}
export function pluginSource(config,ref,maxOutput,worker,auditFile,offline=false){
 if(!ROLES.includes(worker)||worker==='valera-ceo')throw Error('INVALID_WORKER');
 const data=JSON.stringify({id:POLICY_ID,roles:ROLES,definitions:config.agents,ref,maxOutput,worker,offline});
 const audit=auditFile===undefined?'':"import fs from 'node:fs';\n"+auditSequence.toString()+'\n'+auditViolation.toString()+'\n'+readAudit.toString()+'\n'+recordAudit.toString()+'\n';
 const record=auditFile===undefined?'':',record:event=>recordAudit('+JSON.stringify(auditFile)+','+JSON.stringify(worker)+',event)';
 return audit+'const isFreeModel='+isFreeModel.toString()+';\nconst serverPolicy='+serverPolicy.toString()+';\nexport default serverPolicy({...'+data+',freeCheck:isFreeModel'+record+'});\n';
}
// The native CLI can merge duplicate wildcard denies and browser restrictions.
// Accept only observed deny-only shapes; unknown rules fail closed.
function verifyDenyPermissions(rules){
 if(!Array.isArray(rules)||rules.length===0)return false;
 let wildcard=false;
 for(const r of rules){
  if(!r||typeof r!=='object'||Array.isArray(r)||
     Object.keys(r).sort().join(',')!=='action,effect,resource'||r.effect!=='deny')return false;
  if(r.action==='*'&&r.resource==='*'){wildcard=true;continue;}
  if(r.action==='browser'&&r.resource==='*')continue;
  if(r.action==='skill'&&r.resource==='browser')continue;
  return false;
 }
 return wildcard;
}
export function verifyServerSnapshot({plugins,agents,models},config,ref,maxOutput,plugin){
 const entries=plugins?.data,roster=agents?.data,catalog=models?.data;
 if(!Array.isArray(entries)||!entries.some(p=>p.id===POLICY_ID&&p.state?.status==='active'&&p.source?.type==='local'&&p.source.path===plugin)||
    entries.some(p=>p.state?.status==='active'&&p.source?.type!=='builtin'&&p.id!==POLICY_ID))return false;
 if(!Array.isArray(roster)||roster.length!==ROLES.length||new Set(roster.map(a=>a.id)).size!==ROLES.length||
    !ROLES.every(r=>roster.some(a=>a.id===r)))return false;
 if(!roster.every(a=>a.model?.providerID===ref.providerID&&a.model?.id===ref.id&&a.model.variant===undefined&&
    a.steps===1&&a.mode===config.agents[a.id].mode&&a.system===config.agents[a.id].system&&
    verifyDenyPermissions(a.permissions)))return false;
 const active=Array.isArray(catalog)?catalog.filter(m=>m.enabled):[];
 return active.length===1&&isFreeModel(active[0],ref)&&active[0].limit.output<=maxOutput&&
  active[0].capabilities?.tools===false&&Array.isArray(active[0].variants)&&active[0].variants.length===0;
}
