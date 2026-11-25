// Host-owned budget for one provider effect; timeout does not prove non-delivery.
export const BRIDGE_MAX_MS=120_000;
export const FINALIZATION_RESERVE_MS=4_000;
export const SESSION_DELETE_TIMEOUT_MS=1_500;
export class BridgeDeadlineError extends Error {}
export async function withTimeout(operation,timeoutMs){
 if(!Number.isSafeInteger(timeoutMs)||timeoutMs<1||timeoutMs>BRIDGE_MAX_MS)throw Error('Invalid bounded operation timeout');
 let timer;
 try{return await Promise.race([
  Promise.resolve().then(operation),
  new Promise((_,reject)=>{timer=setTimeout(()=>reject(new BridgeDeadlineError('OpenCode gateway stage timed out; outcome uncertain')),timeoutMs);})
 ]);}finally{clearTimeout(timer);}
}
export function bridgeBudget(timeoutMs,now=()=>performance.now()){
 if(!Number.isSafeInteger(timeoutMs)||timeoutMs<FINALIZATION_RESERVE_MS+1||timeoutMs>BRIDGE_MAX_MS)throw Error('Invalid host bridge timeout');
 const start=now();
 const remainingMs=()=>Math.floor(timeoutMs-(now()-start));
 return {remainingMs,stage(operation){
  const allowance=remainingMs()-FINALIZATION_RESERVE_MS;
  if(allowance<1)throw new BridgeDeadlineError('OpenCode gateway deadline exhausted; outcome uncertain');
  return withTimeout(operation,allowance);
 }};
}
