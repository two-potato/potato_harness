// Standalone two-stage synthetic task. No runtime admission or artifact publication.
import {deny,readBoundedMessages,parseAssistant,combine,validateRequest} from './contracts.mjs';
import {validateAssignment} from './assignment.mjs';
import {combineModelUsage} from './bridge_accounting.mjs';
import {bridgeBudget,withTimeout} from './bridge_limits.mjs';
import {assertAudit} from './server-audit.mjs';
import {modelRef,isNativeBaseVariant} from './server-policy.mjs';
import {errorCategory,responseShape,auditShape} from './server-inference-diagnostics.mjs';
import {OBJECTIVE} from './trial-fixture.mjs';

export const PROBE_CAP=1024;
const probeWorker='backend',probeScope=['probe.txt'],probeObjective='Propose the fixed synthetic replacement of probe.txt with potato-probe-ok followed by a newline. No real file exists.';
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
// The common flow has no transport of its own. Only the fixed manual probe
// and the explicitly synthetic runtime fixture can invoke it.
async function nativeFlow({model,launch,awaitPolicy,budget=bridgeBudget(90000),offline=false,task,onPhase=()=>{}}){
 const {worker,scope,objective,prompt,cap,synthetic,checkProposal}=task;
 let observedPhase=null,started=0;
 const begin=name=>{observedPhase=name;started=performance.now();onPhase({phase:name,status:'start',elapsed_ms:0});};
 const end=(status,detail={})=>{if(observedPhase)onPhase({phase:observedPhase,status,elapsed_ms:Math.max(0,Math.round(performance.now()-started)),...detail});observedPhase=null;};
 const reasonCode=category=>({RATE_LIMIT:'RATE_LIMIT',QUOTA:'FREE_QUOTA',FREE_LIMIT:'FREE_QUOTA',AUTH:'AUTH',DEADLINE:'DEADLINE',PROVIDER_UNAVAILABLE:'PROVIDER_UNAVAILABLE',INVALID_JSON:'INVALID_JSON'}[category]??'RESPONSE_REJECTED');
 const reasonStep=check=>({create:'session',session_id:'session',dispatch:'prompt',wait:'prompt',assignment_contract:'assignment'}[check]??'response');
 let server,sessionID,attempts=0,phase='startup',reason='NONE',result,finalAudit;
 let check='launch',failure=null,response=null,cleanupFailed=false;
 const stages=[],ids=new Set();
 try{
  begin('server');
  const ref=modelRef(model);
  server=await launch({model,worker,maxOutput:cap,audit:true,offline});
  phase='preflight';check='policy';
  await budget.stage(()=>awaitPolicy(server));
  check='audit';assertAudit(server.readAudit(),worker,1);end('ok');
  const call=async(role,text,count)=>{
   begin(role==='valera-ceo'?'valera':'specialist');
   phase=role+'_session';check='create';response=null;
   const session=await budget.stage(()=>server.client.session.create({location:{directory:server.directory},agent:role,model:ref,permissions:deny(),title:'Potato bounded synthetic proposal'}));
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
   check='usage';const usage=probeUsage(answer.info,cap);
   check='audit_after_response';assertAudit(server.readAudit(),worker,count);
   sessionID=undefined;
   return {answer,usage};
  };
  const plan=await call('valera-ceo',JSON.stringify({objective,scope,approved_owner:worker,instructions:'Return only JSON with owner and reason. No tools. This is an inert test, not a real assignment.'}),3);
  if(offline){phase='offline_end';check='offline_boundary';throw Error('OFFLINE_UNEXPECTED_RESPONSE');}
  phase='assignment';check='assignment_contract';
  validateAssignment(plan.answer.value,worker);
  stages.push({role:'valera-ceo',usage:plan.usage});end('ok');
  const proposal=await call(worker,prompt,5);
  phase='proposal';check='proposal_contract';
  const combined=combine(plan.answer,proposal.answer,worker,scope);
  checkProposal(combined);
  stages.push({role:worker,usage:proposal.usage});
  result=combined;end('ok');
 }catch(error){
  reason=phase.toUpperCase()+'_HOLD';
  failure={check,category:errorCategory(error)};
  end('error',observedPhase==='valera'||observedPhase==='specialist'?{step:reasonStep(check),reason_code:reasonCode(failure.category)}:{});
 }finally{
  begin('cleanup');
  if(sessionID&&server)try{await withTimeout(()=>server.client.session.interrupt({sessionID,resume:false}),1000);}catch{cleanupFailed=true;if(reason==='NONE')reason='CLEANUP_HOLD';}
  if(server)try{finalAudit=await server.close();}catch{cleanupFailed=true;if(reason==='NONE')reason='CLEANUP_HOLD';}
  end(cleanupFailed?'error':'ok');
 }
 if(result&&reason==='NONE')try{assertAudit(finalAudit,worker,5);}catch{reason='FINAL_AUDIT_HOLD';failure={check:'final_audit',category:'REJECTED'};}
 const pass=!!result&&reason==='NONE';
 const report={status:pass?'PASS':'HOLD',layer:'native-cli-server-inference-probe',reason:pass?'NONE':reason,
  external_inference:offline||synthetic?false:pass?true:attempts?'unknown':false,attempted_prompts:attempts,confirmed_stages:stages,
  ...(pass?{usage:result.usage,admitted_http_hooks:2,admitted_model_hooks:2}:{}),
  ...(offline?{offline_diagnostic:true}:{}),
  diagnostics:{failure,response,audit:auditShape(finalAudit,worker),cleanup_failed:cleanupFailed},
  billing_verified:false,console_api:false,runtime_admission:false};
 return {report,proposal:pass?result:undefined};
}

export async function runNativeProbe(options){
 const {report}=await nativeFlow({...options,task:{worker:probeWorker,scope:probeScope,objective:probeObjective,
  prompt:'Synthetic test only. No actual file exists. Propose the fixed edit to probe.txt with content potato-probe-ok followed by a newline. Return only JSON {"edits":[{"path":"probe.txt","content":"potato-probe-ok\\n"}],"summary":"short explanation"}. No tools.',cap:PROBE_CAP,synthetic:false,checkProposal:p=>{
   if(p.edits.length!==1||p.edits[0].content!=='potato-probe-ok\n'||!p.summary.trim())throw Error('UNEXPECTED_PROBE_PROPOSAL');
  }}});
 return report;
}
export const NATIVE_FIXTURE_MODEL='opencode/potato-runtime-fixture-free';
// Not a live adapter. The model identifier is synthetic, and the host worker
// supplies only the in-process fixture client. No live CLI launch is wired.
export async function runNativeRuntimeFixture(request,{launch,awaitPolicy,onPhase}){
 if(request?.model!==NATIVE_FIXTURE_MODEL||request.role!=='backend'||request.coordination?.objective!==OBJECTIVE||
    JSON.stringify(request.coordination?.scope)!=='["calculation.py"]'||'provider_budget' in request)throw Error('NATIVE_FIXTURE_TRIAL_ONLY');
 const cap=validateRequest(request,{requestModel:NATIVE_FIXTURE_MODEL,modelRef:modelRef(NATIVE_FIXTURE_MODEL)});
 const {report,proposal}=await nativeFlow({model:NATIVE_FIXTURE_MODEL,launch,awaitPolicy,onPhase,budget:bridgeBudget(75000),
  task:{worker:request.role,scope:request.coordination.scope,objective:request.coordination.objective,
   prompt:request.prompt+'\nReturn only JSON {"edits":[{"path":"relative/file","content":"complete new text"}],"summary":"short explanation"}. No tools.',
   cap,synthetic:true,checkProposal:p=>{if(!p.summary.trim())throw Error('INVALID_PROPOSAL');}}});
 if(report.status!=='PASS'||!proposal)throw Error('NATIVE_FIXTURE_HOLD');
 return proposal;
}
