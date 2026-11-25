// Experimental v2 adapter. Only an in-memory synthetic HTTP fixture is admitted.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {bridgeBudget,withTimeout} from '../../opencode/src/bridge_limits.mjs';
import {validateAssignment} from '../../opencode/src/contracts.mjs';
import {validateRequest,candidateConfig,MODEL_REF,deny,parseAssistant,combine} from './contracts.mjs';
import {fixtureTransport,restrictivePlugin,awaitPolicy} from './policy.mjs';

export async function runCandidate(request,{OpenCode,respond,observe={retries:0,ready:false}}){
 const maxOutput=validateRequest(request);
 const budget=bridgeBudget(request.bridge_timeout_ms??75000);
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'potato-v2-'));
 const transport=fixtureTransport(respond,maxOutput);
 let sdk,sessionID;
 try{
  sdk=await budget.stage(()=>OpenCode.create({
   config:{directory,project:false,claude:false,content:JSON.stringify(candidateConfig(maxOutput))},
   instructions:{claude:false},database:{path:':memory:'},models:{fetch:false},
   fs:{filewatcher:false,fff:false},fetch:transport.fetch,
   plugins:[restrictivePlugin(observe,maxOutput)]
  }));
  const call=async(role,phase,text)=>{
   const session=await budget.stage(()=>sdk.sessions.create({location:{directory},agent:role,model:MODEL_REF,permissions:deny(),title:'Potato fixture'}));
   sessionID=session.id;
   // The location's agent/tool registries must initialize the plugin before dispatch.
   await budget.stage(()=>awaitPolicy(()=>sdk.agent.list({location:{directory}}),observe));
   transport.begin(phase);
   await budget.stage(()=>sdk.sessions.prompt({sessionID,text}));
   await budget.stage(()=>sdk.experimental.session.wait({sessionID}));
   const page=await budget.stage(()=>sdk.message.list({sessionID,limit:100}));
   transport.end();
   if(page.cursor?.next||page.cursor?.previous)throw Error('UNEXPECTED_MESSAGE_PAGINATION');
   const answer=parseAssistant(page.data,role);
   sessionID=undefined;
   return answer;
  };
  const plan=await call('valera-ceo','valera',JSON.stringify({objective:request.coordination.objective,scope:request.coordination.scope,approved_owner:request.role,instructions:'Return only JSON with owner and reason. No tools.'}));
  validateAssignment(plan.value,request.role);
  const answer=await call(request.role,'specialist',request.prompt+'\nReturn only JSON {"edits":[{"path":"relative/file","content":"complete new text"}],"summary":"short explanation"}. No tools.');
  if(transport.violated)throw Error('FIXTURE_REQUEST_BOUNDARY');
  return combine(plan,answer,request.role,request.coordination.scope);
 }finally{
  if(sdk){
   if(sessionID)try{await withTimeout(()=>sdk.sessions.interrupt({sessionID,resume:false}),1000);}catch{}
   try{await withTimeout(()=>sdk.close(),2000);}catch{throw Error('V2_CLOSE_FAILED');}
  }
  fs.rmSync(directory,{recursive:true,force:true});
 }
}
