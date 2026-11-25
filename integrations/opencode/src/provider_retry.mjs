// Monitor the pinned SDK's local session status. Never submit a second prompt.
// Polling observes retry backoff; it cannot guarantee that an upstream retry
// has not already started. A rejected/aborted prompt is still an unknown effect.
import {withTimeout} from './bridge_limits.mjs';

export const RETRY_CODES=new Set(['FREE_QUOTA','RATE_LIMIT','PROVIDER_UNAVAILABLE','RETRY_BLOCKED','MONITOR_FAILED']);
export class ProviderRetryError extends Error {
 constructor(code){
  super('Provider session stopped by host');
  this.code=RETRY_CODES.has(code)?code:'RETRY_BLOCKED';
 }
}
export function retryReason(status){
 if(status?.type!=='retry')return null;
 if(status.action?.reason==='free_tier_limit'||status.message==='Free usage exceeded, subscribe to Go')return 'FREE_QUOTA';
 if(status.action?.reason==='account_rate_limit')return 'RATE_LIMIT';
 const message=typeof status.message==='string'?status.message.slice(0,4096):'';
 if(/FreeUsageLimitError/i.test(message))return 'FREE_QUOTA';
 if(/\b429\b|rate.?limit|too many requests/i.test(message))return 'RATE_LIMIT';
 if(/\b(?:500|502|503|504|524)\b|overloaded|service.?unavailable/i.test(message))return 'PROVIDER_UNAVAILABLE';
 return 'RETRY_BLOCKED';
}

export async function guardedPrompt(client,budget,id,body,{pollMs=100}={}){
 const monitor=new AbortController();
 let stopped=false,timer;
 const pause=()=>new Promise(resolve=>{timer=setTimeout(resolve,pollMs);});
 const watch=async()=>{
  while(!stopped){
   let result;
   try{result=await client.session.status({signal:monitor.signal});}
   catch{if(stopped)return;throw new ProviderRetryError('MONITOR_FAILED');}
   if(stopped)return;
   if(!result?.data||typeof result.data!=='object'||Array.isArray(result.data))throw new ProviderRetryError('MONITOR_FAILED');
   const code=retryReason(result.data[id]);
   if(code)throw new ProviderRetryError(code);
   await pause();
  }
 };
 try{
  return await budget.stage(()=>Promise.race([
   Promise.resolve().then(()=>client.session.prompt({path:{id},body})),
   watch(),
  ]));
 }catch(error){
  stopped=true;clearTimeout(timer);monitor.abort();
  // Use a fresh bounded signal: the shared prompt deadline may have expired.
  // Cancellation is best effort; no inference outcome or billing is inferred.
  try{await withTimeout(()=>client.session.abort({path:{id},signal:AbortSignal.timeout(1000)}),1000);}
  catch{/* retain the original failure */}
  throw error;
 }finally{
  stopped=true;clearTimeout(timer);monitor.abort();
 }
}
