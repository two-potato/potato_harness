// Embedded v2 SDK with one bounded inert proposal per stage.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {bridgeBudget,withTimeout} from './bridge_limits.mjs';
import {validateAssignment} from './assignment.mjs';
import {valeraFailure} from './valera_diagnostics.mjs';
import {validateRequest,candidateConfig,FIXTURE_PROFILE,CONSOLE_PROFILE,deny,parseAssistant,combine,readBoundedMessages} from './contracts.mjs';
import {fixtureTransport,restrictivePlugin,awaitPolicy,awaitModel} from './policy.mjs';
import {consoleResponder} from './console.mjs';

export const runCandidate=(request,options)=>runAdapter(request,{...options,profile:FIXTURE_PROFILE});
export function runConsole(request,{OpenCode,key,send,observe,onPhase}){
 const abort=new AbortController();
 const responder=consoleResponder(key,{signal:abort.signal,send,budget:request.provider_budget});
 return runAdapter(request,{OpenCode,observe,onPhase,profile:CONSOLE_PROFILE,respond:responder.respond,billing:responder.usage,abort});
}
async function runAdapter(request,{OpenCode,respond,observe={retries:0,ready:false},profile,onPhase=()=>{},billing,abort=new AbortController()}){
 const maxOutput=validateRequest(request,profile),modelRef=profile.modelRef;
 const budget=bridgeBudget(request.bridge_timeout_ms??75000);
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'potato-v2-'));
 let transportError;
 const transport=fixtureTransport(async(...args)=>{try{return await respond(...args);}catch(e){transportError=e;throw e;}},maxOutput,modelRef);
 let sdk,sessionID,phase=null,started=0,step='unknown',primaryError,result;
 const begin=p=>{phase=p;started=performance.now();onPhase({phase,status:'start',elapsed_ms:0});};
 const end=(status,detail={})=>{if(phase)onPhase({phase,status,elapsed_ms:Math.max(0,Math.round(performance.now()-started)),...detail});phase=null;};
 try{
  begin('server');
  sdk=await budget.stage(()=>OpenCode.create({
   config:{directory,project:false,claude:false,content:JSON.stringify(candidateConfig(maxOutput,profile))},
   instructions:{claude:false},database:{path:':memory:'},models:{fetch:false,snapshot:false},
   fs:{filewatcher:false,fff:false},fetch:transport.fetch,
   plugins:[restrictivePlugin(observe,maxOutput,profile)]
  }));
  end('ok');
  const call=async(role,name,text)=>{
   begin(name);step='session';
   const session=await budget.stage(()=>sdk.sessions.create({location:{directory},agent:role,model:modelRef,permissions:deny(),title:'Potato bounded proposal'}));
   sessionID=session.id;
   await budget.stage(()=>awaitPolicy(()=>sdk.agent.list({location:{directory}}),observe,{modelRef}));
   await budget.stage(()=>awaitModel(()=>sdk.model.list({location:{directory}}),maxOutput,{modelRef}));
   transport.begin(name);step='prompt';
   await budget.stage(()=>sdk.sessions.prompt({sessionID,text}));
   await budget.stage(()=>sdk.experimental.session.wait({sessionID}));
   if(transportError)throw transportError;
   step='response';
   const page=await budget.stage(()=>readBoundedMessages(input=>sdk.message.list(input),sessionID));
   transport.end();
   const answer=parseAssistant(page.data,role,modelRef);
   sessionID=undefined;
   return answer;
  };
  const plan=await call('valera-ceo','valera',JSON.stringify({objective:request.coordination.objective,scope:request.coordination.scope,approved_owner:request.role,instructions:'Return only JSON with owner and reason. No tools.'}));
  step='assignment';validateAssignment(plan.value,request.role);end('ok');
  const answer=await call(request.role,'specialist',request.prompt+'\nReturn only JSON {"edits":[{"path":"relative/file","content":"complete new text"}],"summary":"short explanation"}. No tools.');
  if(transport.violated)throw Error('FIXTURE_REQUEST_BOUNDARY');
  step='assignment';result=combine(plan,answer,request.role,request.coordination.scope);end('ok');
  begin('usage');if(billing)result.usage=billing();end('ok');
 }catch(e){
  primaryError=transportError??e;
  end('error',phase==='valera'||phase==='specialist'?valeraFailure(step,primaryError):{});
 }finally{
  transport.close();abort.abort();begin('cleanup');
  let cleanupError=false;
  if(sdk){
   if(sessionID)try{await withTimeout(()=>sdk.sessions.interrupt({sessionID,resume:false}),1000);}catch{cleanupError=true;}
   try{await withTimeout(()=>sdk.close(),2000);}catch{cleanupError=true;}
  }
  try{fs.rmSync(directory,{recursive:true,force:true});}catch{cleanupError=true;}
  end(cleanupError?'error':'ok');
  if(cleanupError&&!primaryError)primaryError=Error('V2_CLOSE_FAILED');
 }
 if(primaryError)throw primaryError;
 return result;
}
