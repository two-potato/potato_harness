// Composition of the actual attached session transport with the existing
// two-stage runtime flow. Trusted host admission is a required integration
// seam, not a boolean from a worker request. No CLI invokes this module.
import {createHash} from 'node:crypto';
import {ATTACHED_TRIAL_MODEL} from './attached-stage-ledger.mjs';
import {connectAttachedTransport} from './attached-runtime-transport.mjs';
import {runAttachedRuntimeCandidate} from './server-inference.mjs';

export async function runBoundAttachedRuntime(request,{transport,ledger,admit,onPhase}={}){
 if(typeof admit!=='function'||!ledger||!transport||request?.model!==ATTACHED_TRIAL_MODEL||
    transport.model!==ATTACHED_TRIAL_MODEL||!Number.isSafeInteger(request.token_allowance)||
    request.token_allowance<2||request.token_allowance>100000||
    !Number.isSafeInteger(request.output_token_allowance)||request.output_token_allowance<2||
    request.output_token_allowance!==2048||!Number.isSafeInteger(request.bridge_timeout_ms)||
    request.bridge_timeout_ms<=4000||request.bridge_timeout_ms>120000)
  throw Error('ATTACHED_RUNTIME_BINDING_INVALID');
 // The bound profile caps each stage at 1024. Admission must authorize this
 // exact scoped trial and attest external enforcement outside this module.
 request=structuredClone(request);
 const cap=1024;
 const scope=Object.freeze({model:ATTACHED_TRIAL_MODEL,roles:Object.freeze(['valera-ceo','backend']),
  directory:transport.directory,token_limit:request.token_allowance,output_limit:cap,
  bridge_timeout_ms:request.bridge_timeout_ms,
  request_sha256:createHash('sha256').update(JSON.stringify(request)).digest('hex')});
 if(await admit(scope)!==true)throw Error('ATTACHED_ADMISSION_REQUIRED');
 ledger.reserve(scope.model,scope.token_limit,scope.output_limit,scope.request_sha256);
 let result;
 try{
  result=await runAttachedRuntimeCandidate(request,{
   expectedModel:scope.model,onPhase,
   launch:async options=>{
    if(options.model!==scope.model||options.worker!=='backend'||options.maxOutput!==cap||
       options.audit!==true||options.offline!==false)throw Error('ATTACHED_LAUNCH_SCOPE');
    if(typeof transport.prepare==='function')await transport.prepare();
    return connectAttachedTransport(transport);
   },
   // connectAttachedTransport has already validated profile/snapshot/audit,
   // and revalidates the policy before each session.
   awaitPolicy:async()=>{},
   beforePrompt:role=>ledger.beforePrompt(role),
   onValidatedStage:(role,usage)=>ledger.validatedStage(role,usage)
  });
 }catch{
  ledger.finish(null);
  throw Error('ATTACHED_RUNTIME_OUTCOME_UNKNOWN');
 }
 if(ledger.finish(result)!=='VALIDATED')throw Error('ATTACHED_RUNTIME_OUTCOME_UNKNOWN');
 return result;
}
