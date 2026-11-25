// Fixed advisory error categories, not a retry mechanism.
export const RETRY_CODES=new Set(['FREE_QUOTA','RATE_LIMIT','PROVIDER_UNAVAILABLE','RETRY_BLOCKED','MONITOR_FAILED']);
export class ProviderRetryError extends Error {
 constructor(code){
  super('Provider session stopped by host');
  this.code=RETRY_CODES.has(code)?code:'RETRY_BLOCKED';
 }
}
