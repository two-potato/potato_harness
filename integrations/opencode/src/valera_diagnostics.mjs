// Advisory diagnostic categories only. Never emit SDK error messages or model text.
import {BridgeDeadlineError} from './bridge_limits.mjs';
import {ProviderRetryError} from './provider_retry.mjs';
const STEPS=new Set(['coordination','session','prompt','close','response','json','assignment']);
export function valeraFailure(step,error){
 step=STEPS.has(step)?step:'unknown';
 let reason_code='STEP_FAILED';
 if(error instanceof ProviderRetryError)reason_code=error.code;
 else if(error instanceof BridgeDeadlineError)reason_code='DEADLINE';
 else if(error?.name==='AbortError'||error?.name==='TimeoutError')reason_code='ABORTED';
 else if(step==='json')reason_code='INVALID_JSON';
 else if(step==='assignment')reason_code='INVALID_ASSIGNMENT';
 else if(step==='prompt'||step==='response'){
  const code=error?.data?.statusCode??error?.statusCode??error?.status;
  if(code===401||code===403)reason_code='AUTH';
  else if(code===429)reason_code='RATE_LIMIT';
  else if(typeof code==='number'&&code>=500&&code<=599)reason_code='PROVIDER_UNAVAILABLE';
  else if(step==='response')reason_code='RESPONSE_REJECTED';
 }
 return {step,reason_code};
}
