// Standalone two-stage synthetic task. No runtime admission or artifact publication.
import {deny,readBoundedMessages,parseAssistant,combine} from './contracts.mjs';
import {validateAssignment} from './assignment.mjs';
import {combineModelUsage} from './bridge_accounting.mjs';
import {bridgeBudget,withTimeout} from './bridge_limits.mjs';
import {assertAudit} from './server-audit.mjs';
import {modelRef,isNativeBaseVariant} from './server-policy.mjs';
import {errorCategory,responseShape,auditShape} from './server-inference-diagnostics.mjs';

export const PROBE_CAP=1024;
const worker='backend',scope=['probe.txt'],objective='Propose the fixed synthetic replacement of probe.txt with potato-probe-ok followed by a newline. No real file exists.';
const zero={tokens:{input:0,output:0},cost:0};
export function probeArgs(args){
 if(args.length!==2||args[1]!=='--confirm-external-inference')throw Error('EXPLICIT_CONFIRMATION_REQUIRED');
 modelRef(args[0]);return args[0];
}
export function probeUsage(info,cap=PROBE_CAP){
 const u=combineModelUsage(info,zero);
 if(u.cost_usd!==0||u.input_tokens<1||u.output_tokens<1||u.output_tokens>cap)throw Error('USAGE_NOT_ZERO_OR_BOUNDED');
 return u;
}
export async function runNativeProbe({model,launch,awaitPolicy,budget=bridgeBudget(90000),offline=false}){
 let server,sessionID,attempts=0,phase='startup',reason='NONE',result,finalAudit;
 let check='launch',failure=null,response=null,cleanupFailed=false;
 const stages=[],ids=new Set();
 try{
  const ref=modelRef(model);
  server=await launch({model,worker,maxOutput:PROBE_CAP,audit:true,offline});
  phase='preflight';check='policy';
  await budget.stage(()=>awaitPolicy(server));
  check='audit';assertAudit(server.readAudit(),worker,1);
  const call=async(role,text,count)=>{
   phase=role+'_session';check='create';response=null;
   const session=await budget.stage(()=>server.client.session.create({location:{directory:server.directory},agent:role,model:ref,permissions:deny(),title:'Potato synthetic probe'}));
   check='session_id';
   if(typeof session?.id!=='string'||!session.id||ids.has(session.id))throw Error('INVALID_SESSION');
   sessionID=session.id;ids.add(sessionID);
   check='audit_before_prompt';assertAudit(server.readAudit(),worker,count-2);
   phase=role+'_prompt';check='dispatch';
   attempts++;
   await budget.stage(()=>server.client.session.prompt({sessionID,text}));
   check='wait';await budget.stage(()=>server.client.experimental.session.wait({sessionID}));
   phase=role+'_response';check='message_page';
   const page=await budget.stage(()=>readBoundedMessages(input=>server.client.message.list(input),sessionID));
   response=responseShape(page.data,role,ref);check='user_count';
   if(page.data.filter(x=>x?.type==='user').length!==1)throw Error('UNEXPECTED_USER_MESSAGES');
   check='assistant_contract';const answer=parseAssistant(page.data,role,ref);
   check='variant';if(!isNativeBaseVariant(answer.info.model.variant))throw Error('UNEXPECTED_VARIANT');
   check='usage';const usage=probeUsage(answer.info);
   check='audit_after_response';assertAudit(server.readAudit(),worker,count);
   sessionID=undefined;
   return {answer,usage};
  };
  const plan=await call('valera-ceo',JSON.stringify({objective,scope,approved_owner:worker,instructions:'Return only JSON with owner and reason. No tools. This is an inert test, not a real assignment.'}),3);
  if(offline){phase='offline_end';check='offline_boundary';throw Error('OFFLINE_UNEXPECTED_RESPONSE');}
  phase='assignment';check='assignment_contract';
  validateAssignment(plan.answer.value,worker);
  stages.push({role:'valera-ceo',usage:plan.usage});
  const proposal=await call(worker,'Synthetic test only. No actual file exists. Propose the fixed edit to probe.txt with content potato-probe-ok followed by a newline. Return only JSON {"edits":[{"path":"probe.txt","content":"potato-probe-ok\\n"}],"summary":"short explanation"}. No tools.',5);
  phase='proposal';check='proposal_contract';
  const combined=combine(plan.answer,proposal.answer,worker,scope);
  if(combined.edits.length!==1||combined.edits[0].content!=='potato-probe-ok\n'||!combined.summary.trim())throw Error('UNEXPECTED_PROBE_PROPOSAL');
  stages.push({role:worker,usage:proposal.usage});
  result={usage:combined.usage};
 }catch(error){
  reason=phase.toUpperCase()+'_HOLD';
  failure={check,category:errorCategory(error)};
 }finally{
  if(sessionID&&server)try{await withTimeout(()=>server.client.session.interrupt({sessionID,resume:false}),1000);}catch{cleanupFailed=true;if(reason==='NONE')reason='CLEANUP_HOLD';}
  if(server)try{finalAudit=await server.close();}catch{cleanupFailed=true;if(reason==='NONE')reason='CLEANUP_HOLD';}
 }
 if(result&&reason==='NONE')try{assertAudit(finalAudit,worker,5);}catch{reason='FINAL_AUDIT_HOLD';failure={check:'final_audit',category:'REJECTED'};}
 const pass=!!result&&reason==='NONE';
 return {status:pass?'PASS':'HOLD',layer:'native-cli-server-inference-probe',reason:pass?'NONE':reason,
  external_inference:offline?false:pass?true:attempts?'unknown':false,attempted_prompts:attempts,confirmed_stages:stages,
  ...(pass?{usage:result.usage,admitted_http_hooks:2,admitted_model_hooks:2}:{}),
  ...(offline?{offline_diagnostic:true}:{}),
  diagnostics:{failure,response,audit:auditShape(finalAudit,worker),cleanup_failed:cleanupFailed},
  billing_verified:false,console_api:false,runtime_admission:false};
}
