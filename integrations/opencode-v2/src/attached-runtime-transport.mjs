// Trusted host transport for one attached Location. This module does not grant
// live admission. It never launches, restarts or shuts down OpenCode.
// A future admitted worker must bind its own verified profile and audit reader.
import {attachedFetch,ATTACHED_ENDPOINT} from './attached-server-probe.mjs';
import {attachedModelRef,verifyAttachedSnapshot} from './attached-policy-profile.mjs';
import {assertAudit} from './server-audit.mjs';
import {withTimeout} from './bridge_limits.mjs';

export async function connectAttachedTransport({directory,model,password,clientFactory,
 profile,readAudit,verifyProfile,send}){
 if(typeof password!=='string'||!password||typeof clientFactory!=='function'||
    typeof readAudit!=='function'||typeof verifyProfile!=='function'||
    typeof directory!=='string'||!directory.startsWith('/')||directory.includes('\0'))
  throw Error('ATTACHED_HOST_BINDING_REQUIRED');
 const ref=attachedModelRef(model);
 if(ref.providerID!=='openrouter'||profile?.ref?.providerID!==ref.providerID||profile?.ref?.id!==ref.id)
  throw Error('ATTACHED_MODEL_MISMATCH');
 const controller=new AbortController(),location={directory};
 const raw=clientFactory({baseUrl:ATTACHED_ENDPOINT,fetch:attachedFetch({password,signal:controller.signal,send})});
 const sessions=new Map(),roles=['valera-ceo','backend'];
 let closed=false,closing=false,creating=false,pendingCreate=false,nextRole=0,ready=false;
 const usable=()=>{if(closed||closing||!ready)throw Error('ATTACHED_TRANSPORT_NOT_READY');};
 const owned=id=>{usable();const s=sessions.get(id);if(!s)throw Error('ATTACHED_SESSION_NOT_OWNED');return s;};
 const snapshot=async()=>{
  await verifyProfile();
  const health=await withTimeout(()=>raw.server.info(),5000);
  if(health?.version!=='2.4.1')throw Error('SERVER_VERSION_MISMATCH');
  const [plugins,agents,models]=await withTimeout(()=>Promise.all([
   raw.plugin.list({location}),raw.agent.list({location}),raw.model.list({location})
  ]),15000);
  if(!verifyAttachedSnapshot({plugins,agents,models},profile))throw Error('ATTACHED_POLICY_MISMATCH');
 };
 try{
  await snapshot();assertAudit(readAudit(),'backend',1);ready=true;
 }catch(e){controller.abort();throw e;}
 const client={
  session:{
   async create(input){
    usable();
    const role=roles[nextRole];
    if(creating||!role||input?.agent!==role||
       input.location?.directory!==directory||input.model?.providerID!==ref.providerID||
       input.model?.id!==ref.id||input.model.variant!==undefined||
       JSON.stringify(input.permissions)!=='[{"action":"*","resource":"*","effect":"deny"}]')
     throw Error('ATTACHED_SESSION_BOUNDARY');
    creating=true;
    try{
     await snapshot();usable();
     pendingCreate=true; // failure may mean an unobserved server session
     const s=await raw.session.create({location,agent:role,model:ref,
      permissions:[{action:'*',resource:'*',effect:'deny'}],title:'Potato bounded proposal'});
     if(typeof s?.id!=='string'||!s.id||sessions.has(s.id))throw Error('ATTACHED_SESSION_ID');
     sessions.set(s.id,{role,prompted:false,waited:false});
     pendingCreate=false;nextRole++;
     if(closing||closed)throw Error('ATTACHED_TRANSPORT_CLOSING');
     return {id:s.id};
    }finally{creating=false;}
   },
   async prompt({sessionID,text}){
    const s=owned(sessionID);
    if(s.prompted||typeof text!=='string'||!text||Buffer.byteLength(text)>262144)
     throw Error('ATTACHED_PROMPT_BOUNDARY');
    if(s.role==='backend'&&![...sessions.values()].some(x=>x.role==='valera-ceo'&&x.waited))
     throw Error('ATTACHED_VALERA_NOT_IDLE');
    s.prompted=true; // do not permit retry even if delivery is uncertain
    return raw.session.prompt({sessionID,text});
   },
   async interrupt({sessionID,resume}){
    owned(sessionID);if(resume!==false)throw Error('ATTACHED_RESUME_DENIED');
    return raw.session.interrupt({sessionID,resume:false});
   }
  },
  experimental:{session:{async wait({sessionID}){
   const s=owned(sessionID);if(!s.prompted)throw Error('ATTACHED_NO_PROMPT');
   const r=await raw.experimental.session.wait({sessionID});s.waited=true;return r;
  }}},
  message:{async list({sessionID,order,limit,cursor}){
   const s=owned(sessionID);
   if(!s.waited||!Number.isSafeInteger(limit)||limit<1||limit>100||
      (order!==undefined&&order!=='asc')||(cursor!==undefined&&(typeof cursor!=='string'||cursor.length>4096)))
    throw Error('ATTACHED_MESSAGE_BOUNDARY');
   return raw.message.list({sessionID,limit,...(order?{order}:{}),...(cursor?{cursor}:{})});
  }}
 };
 return {client,directory,readAudit,
  async close(){
   if(closed||closing)throw Error('ATTACHED_DOUBLE_CLOSE');
   closing=true;let failed=pendingCreate||creating;
   // Keep the audit and Location on disk. Do not delete sessions or erase
   // provider records; interrupt only sessions created by this binding.
   try{
    for(const [sessionID,s] of sessions){
     if(!s.waited)try{
      await withTimeout(()=>raw.session.interrupt({sessionID,resume:false}),1000);
      await withTimeout(()=>raw.experimental.session.wait({sessionID}),1000);
     }catch{failed=true;}
    }
    if(failed)throw Error('ATTACHED_CLEANUP_UNCERTAIN');
    return readAudit();
   }finally{closed=true;controller.abort();}
  }};
}
