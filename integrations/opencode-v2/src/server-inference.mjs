// Standalone two-stage synthetic task. No runtime admission or artifact publication.
import {deny,readBoundedMessages,parseAssistant,combine,validateRequest} from './contracts.mjs';
import {validateAssignment} from './assignment.mjs';
import {combineModelUsage} from './bridge_accounting.mjs';
import {bridgeBudget,withTimeout} from './bridge_limits.mjs';
import {assertAudit} from './server-audit.mjs';
import {modelRef,isNativeBaseVariant} from './server-policy.mjs';
import {attachedModelRef} from './attached-policy-profile.mjs';
import {errorCategory,responseShape,auditShape} from './server-inference-diagnostics.mjs';
import {OBJECTIVE} from './trial-fixture.mjs';
import {requireOfflineNetwork} from './offline-network.mjs';

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
// The common flow has no transport of its own. The manual probe and runtime
// diagnostics bind their own launchers; the future candidate has no CLI binding.
async function nativeFlow({model,launch,awaitPolicy,budget=bridgeBudget(90000),offline=false,task,onPhase=()=>{},beforePrompt=()=>{},onValidatedStage=()=>{},resolveModelRef=modelRef}){
 const {worker,scope,objective,prompt,cap,synthetic,checkProposal,tokenAllowance,assignmentInstruction='Return only JSON with owner and reason. No tools. This is an inert test, not a real assignment.'}=task;
 let reportedTokens=0;
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
  const ref=resolveModelRef(model);
  server=await launch({model,worker,maxOutput:cap,audit:true,offline});
  phase='preflight';check='policy';
  await budget.stage(()=>awaitPolicy(server));
  check='audit';assertAudit(server.readAudit(),worker,1);end('ok');
  const call=async(role,text,count)=>{
   begin(role==='valera-ceo'?'valera':'specialist');
   phase=role+'_session';check='create';response=null;
   const session=await budget.stage(()=>server.client.session.create({location:{directory:server.directory},agent:role,model:ref,permissions:deny(),title:'Potato bounded proposal'}));
   check='session_id';
   if(typeof session?.id!=='string'||!session.id||ids.has(session.id))throw Error('INVALID_SESSION');
   sessionID=session.id;ids.add(sessionID);
   check='audit_before_prompt';assertAudit(server.readAudit(),worker,count-2);
   phase=role+'_prompt';check='dispatch';
   await budget.stage(()=>{
    beforePrompt(role); // Durable host reservation must commit before the prompt.
    attempts++;
    return server.client.session.prompt({sessionID,text});
   });
   check='wait';await budget.stage(()=>server.client.experimental.session.wait({sessionID}));
   phase=role+'_response';check='message_page';
   const page=await budget.stage(()=>readBoundedMessages(input=>server.client.message.list(input),sessionID));
   response=responseShape(page.data,role,ref);check='user_count';
   if(page.data.filter(x=>x?.type==='user').length!==1)throw Error('UNEXPECTED_USER_MESSAGES');
   // Native v2 can emit only an idle failure and no assistant. Never let
   // a conflicting failed/interrupted terminal event pass as a valid answer.
   if(response?.counts.idle&&(response.counts.idle!==1||response.idle?.outcome!=='succeeded'||response.idle.error!=='NONE')){
    check='idle_outcome';throw Error('UNSUCCESSFUL_IDLE');
   }
   check='assistant_contract';const answer=parseAssistant(page.data,role,ref);
   check='variant';if(!isNativeBaseVariant(answer.info.model.variant))throw Error('UNEXPECTED_VARIANT');
   check='usage';const usage=probeUsage(answer.info,cap);
   reportedTokens+=usage.input_tokens+usage.output_tokens;
   if(!Number.isSafeInteger(reportedTokens)||(tokenAllowance!==undefined&&reportedTokens>tokenAllowance))throw Error('NATIVE_TOKEN_BUDGET_EXCEEDED');
   check='audit_after_response';assertAudit(server.readAudit(),worker,count);
   sessionID=undefined;
   return {answer,usage};
  };
  const plan=await call('valera-ceo',JSON.stringify({objective,scope,approved_owner:worker,instructions:assignmentInstruction}),3);
  if(offline){phase='offline_end';check='offline_boundary';throw Error('OFFLINE_UNEXPECTED_RESPONSE');}
  phase='assignment';check='assignment_contract';
  validateAssignment(plan.answer.value,worker);
  // Two positive usage counters are required for the next stage. This is a
  // reported-usage gate, not a pre-dispatch guarantee of actual wire tokens.
  if(tokenAllowance!==undefined&&tokenAllowance-reportedTokens<2){check='usage';throw Error('NATIVE_TOKEN_BUDGET_EXHAUSTED');}
  onValidatedStage('valera-ceo',plan.usage);
  stages.push({role:'valera-ceo',usage:plan.usage});end('ok');
  const proposal=await call(worker,prompt,5);
  phase='proposal';check='proposal_contract';
  const combined=combine(plan.answer,proposal.answer,worker,scope);
  checkProposal(combined);
  onValidatedStage(worker,proposal.usage);
  stages.push({role:worker,usage:proposal.usage});
  result=combined;end('ok');
 }catch(error){
  reason=phase.toUpperCase()+'_HOLD';
  const terminalCategory=check==='idle_outcome'&&response?.idle?.error;
  failure={check,category:terminalCategory&&terminalCategory!=='NONE'?terminalCategory:errorCategory(error)};
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
// A trusted host request is data, never transport configuration or activation.
// Both native runtime diagnostics share the same closed, bounded contract.
function prepareNativeRuntime(request,mode){
 if(!['fixture','offline','candidate','attached-candidate'].includes(mode))throw Error('NATIVE_RUNTIME_MODE');
 const fields=['role','model','prompt','coordination','output_token_allowance','projectDir','bridge_timeout_ms','token_allowance'];
 if(!request||typeof request!=='object'||Array.isArray(request)||
    Object.keys(request).some(key=>!fields.includes(key))||
    ('projectDir' in request&&(typeof request.projectDir!=='string'||!request.projectDir.startsWith('/')||request.projectDir.includes('\0')))||
    !request.coordination||Object.keys(request.coordination).sort().join(',')!=='objective,scope'||
    request.role!=='backend'||request.coordination.objective!==OBJECTIVE||
    JSON.stringify(request.coordination.scope)!=='["calculation.py"]')throw Error('NATIVE_RUNTIME_CONTRACT');
 const model=request.model,ref=mode==='attached-candidate'?attachedModelRef(model):modelRef(model);
 if(mode==='attached-candidate'&&ref.providerID!=='openrouter')throw Error('ATTACHED_OPENROUTER_REQUIRED');
 if(mode==='fixture'?model!==NATIVE_FIXTURE_MODEL:model===NATIVE_FIXTURE_MODEL)throw Error('NATIVE_RUNTIME_MODE_MODEL');
 const cap=validateRequest(request,{requestModel:model,modelRef:ref});
 if(['candidate','attached-candidate'].includes(mode)&&(!('bridge_timeout_ms' in request)||!('token_allowance' in request)))throw Error('NATIVE_CANDIDATE_HOST_BOUNDS_REQUIRED');
 const budget=bridgeBudget('bridge_timeout_ms' in request?request.bridge_timeout_ms:75000);
 const tokenAllowance=request.token_allowance;
 if('token_allowance' in request&&(!Number.isSafeInteger(tokenAllowance)||tokenAllowance<2))throw Error('NATIVE_TOKEN_ALLOWANCE');
 return {model,cap,budget,tokenAllowance};
}
// Shared proposal contract; the trusted launch binding is never supplied by
// JSON or an agent. The candidate export below is deliberately not wired to
// the runtime CLI. A successful injected test is not external admission.
async function runtimeProposal(request,prepared,{launch,awaitPolicy,onPhase,beforePrompt,onValidatedStage},mode){
 if(typeof launch!=='function'||typeof awaitPolicy!=='function')throw Error('NATIVE_HOST_BINDING_REQUIRED');
 const {model,cap,budget,tokenAllowance}=prepared;
 const attached=mode==='attached-candidate';
 const {report,proposal}=await nativeFlow({model,launch,awaitPolicy,onPhase,budget,
  ...(attached?{resolveModelRef:attachedModelRef,beforePrompt,onValidatedStage}:{}),
  task:{worker:request.role,scope:request.coordination.scope,objective:request.coordination.objective,
   prompt:request.prompt+'\nReturn only JSON {"edits":[{"path":"relative/file","content":"complete new text"}],"summary":"short explanation"}. No tools.',
   cap,tokenAllowance,synthetic:mode==='fixture',
   ...(['candidate','attached-candidate'].includes(mode)?{assignmentInstruction:'Return only JSON with owner and reason. Coordinate only. No tools or source inspection.'}:{}),
   checkProposal:p=>{if(!p.summary.trim())throw Error('INVALID_PROPOSAL');}}});
 if(report.status!=='PASS'||!proposal)throw Error(mode==='fixture'?'NATIVE_FIXTURE_HOLD':'NATIVE_CANDIDATE_HOLD');
 return proposal;
}
export async function runNativeRuntimeFixture(request,bindings){
 return runtimeProposal(request,prepareNativeRuntime(request,'fixture'),bindings,'fixture');
}
// Future candidate contract, exercised only with injected synthetic transport.
// expectedModel is a trusted host consistency check, not an authorization token.
// No production launcher, worker mode, configuration or consent flag is added.
export async function runNativeRuntimeCandidate(request,bindings){
 const prepared=prepareNativeRuntime(request,'candidate');
 if(prepared.model!==bindings?.expectedModel)throw Error('NATIVE_CANDIDATE_MODEL_MISMATCH');
 return runtimeProposal(request,prepared,bindings,'candidate');
}

// Separate attached-provider contract; only a trusted host can bind transport,
// admission and durable dispatch callbacks. There is no CLI/runtime registration.
export async function runAttachedRuntimeCandidate(request,bindings){
 const prepared=prepareNativeRuntime(request,'attached-candidate');
 if(prepared.model!==bindings?.expectedModel)throw Error('ATTACHED_CANDIDATE_MODEL_MISMATCH');
 if(typeof bindings?.beforePrompt!=='function'||typeof bindings?.onValidatedStage!=='function')
  throw Error('ATTACHED_DURABLE_STAGE_BINDING_REQUIRED');
 return runtimeProposal(request,prepared,bindings,'attached-candidate');
}

// Real CLI with the offline guard. Never return a proposal to the runtime.
export async function runNativeRuntimeOffline(request,{launch,awaitPolicy,onPhase=()=>{},verifyNetwork=requireOfflineNetwork}){
 verifyNetwork();
 const {model,cap,budget,tokenAllowance}=prepareNativeRuntime(request,'offline');
 const {report}=await nativeFlow({model,launch,awaitPolicy,onPhase,offline:true,budget,
  task:{worker:request.role,scope:request.coordination.scope,objective:request.coordination.objective,
   prompt:'Offline diagnostic only; no specialist dispatch permitted.',cap,tokenAllowance,synthetic:false,
   checkProposal:()=>{throw Error('OFFLINE_PROPOSAL_DENIED');}}});
 const d=report.diagnostics,a=d?.audit;
 if(report.status==='HOLD'&&report.offline_diagnostic===true&&report.external_inference===false&&
    report.attempted_prompts===1&&report.confirmed_stages.length===0&&d.cleanup_failed===false&&
    d.response?.counts?.user===1&&d.response.counts.assistant===0&&a?.ready===true&&
    a.model_hooks===0&&a.http_hooks===0&&a.violation===true&&a.violation_reason==='offline_stop'){
  verifyNetwork();
  onPhase({phase:'offline_boundary',status:'ok',elapsed_ms:0});
  throw Error('NATIVE_OFFLINE_BOUNDARY');
 }
 throw Error('NATIVE_OFFLINE_HOLD');
}
