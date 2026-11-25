// OpenCode Console API: explicit paid model only. Never forward SDK headers.
import {ProviderRetryError} from '../../opencode/src/provider_retry.mjs';
export const CONSOLE_URL='https://opencode.ai/inference/openai/v1/chat/completions';
export const CONSOLE_MODEL='minimax-m3';
const MAX_RESPONSE=2*1024*1024;
function count(value){if(!Number.isSafeInteger(value)||value<0)throw Error('UNKNOWN_PROVIDER_TOKENS');return value;}
function sum(...values){return count(values.reduce((a,b)=>a+count(b),0));}
export function consoleUsage(text){
 let usage,done=false;
 for(const frame of text.replace(/\r\n/g,'\n').split('\n\n')){
  const data=frame.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');
  if(!data)continue;
  if(done)throw Error('UNEXPECTED_PROVIDER_TRAILER');
  if(data==='[DONE]'){done=true;continue;}
  const item=JSON.parse(data);
  if(item.usage!==undefined&&item.usage!==null){
   if(usage)throw Error('DUPLICATE_PROVIDER_USAGE');
   usage=item.usage;
  }
 }
 if(!done||!usage)throw Error('UNKNOWN_PROVIDER_USAGE');
 const o=usage.opencode,t=o?.tokens;
 if(!t)throw Error('UNKNOWN_PROVIDER_TOKENS');
 const input=sum(t.input,t.cache_read,t.cache_write_5m,t.cache_write_1h);
 const output=count(t.output); // Console documents that output already includes reasoning.
 const cost=usage.cost;
 return {input_tokens:input,output_tokens:output,cost_usd:o.billing_source==='balance'&&o.estimated!==true&&typeof cost==='number'&&Number.isFinite(cost)&&cost>=0?cost:null};
}
async function boundedText(response){
 if(!response.body)throw Error('EMPTY_PROVIDER_BODY');
 const reader=response.body.getReader(),decoder=new TextDecoder('utf-8',{fatal:true});
 let size=0,text='';
 try{
  for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>MAX_RESPONSE)throw Error('OVERSIZED_PROVIDER_RESPONSE');text+=decoder.decode(value,{stream:true});}
  return text+decoder.decode();
 }finally{try{await reader.cancel();}catch{}reader.releaseLock();}
}
function httpError(status){
 if(status===401||status===403)return Object.assign(Error('Provider authorization rejected'),{code:'AUTH',statusCode:status});
 if(status===429)return new ProviderRetryError('RATE_LIMIT');
 if(status>=500&&status<=599)return new ProviderRetryError('PROVIDER_UNAVAILABLE');
 return Error('PROVIDER_REJECTED');
}
export function consoleResponder(key,{signal,send=globalThis.fetch}={}){
 if(typeof key!=='string'||!key||key.length>4096||/[\r\n\0]/.test(key))throw Error('MISSING_CONSOLE_KEY');
 const records=new Map(),attempts=new Set();let failed=false;
 return {
  async respond(phase,body){
   if(failed||signal?.aborted||!['valera','specialist'].includes(phase)||attempts.has(phase)||(phase==='specialist'&&!records.has('valera')))throw Error('CONSOLE_DISPATCH_DENIED');
   attempts.add(phase);
   try{
    const cap=body.max_tokens??body.max_completion_tokens;
    if(body.model!==CONSOLE_MODEL||!Number.isSafeInteger(cap)||cap<1||cap>2048||body.stream!==true||!Array.isArray(body.messages)||body.tools?.length)throw Error('CONSOLE_BODY_DENIED');
    // Only text messages; no file URLs, tool calls, remote images or auxiliary params.
    const messages=body.messages.map(m=>{
     if(!['system','user','assistant'].includes(m.role))throw Error('CONSOLE_MESSAGE_DENIED');
     const content=typeof m.content==='string'?m.content:Array.isArray(m.content)&&m.content.every(p=>p.type==='text'&&typeof p.text==='string')?m.content.map(p=>p.text).join(''):null;
     if(content===null)throw Error('CONSOLE_MESSAGE_DENIED');
     return {role:m.role,content};
    });
    const payload=JSON.stringify({model:CONSOLE_MODEL,messages,max_tokens:cap,stream:true,stream_options:{include_usage:true}});
    if(Buffer.byteLength(payload)>262144)throw Error('CONSOLE_INPUT_BOUND');
    const response=await send(CONSOLE_URL,{method:'POST',redirect:'error',signal,headers:{Authorization:'Bearer '+key,'Content-Type':'application/json','Accept':'text/event-stream'},body:payload});
    if(!response.ok){try{await response.body?.cancel();}catch{}throw httpError(response.status);}
    if(!response.headers.get('content-type')?.toLowerCase().startsWith('text/event-stream'))throw Error('UNEXPECTED_PROVIDER_CONTENT');
    const raw=await boundedText(response);
    const record=consoleUsage(raw);
    records.set(phase,record);
    if(record.cost_usd===null)throw Error('UNKNOWN_PROVIDER_COST');
    return new Response(raw,{headers:{'Content-Type':'text/event-stream'}});
   }catch(error){failed=true;throw error;}
  },
  usage(){
   if(failed||records.size!==2)throw Error('INCOMPLETE_CONSOLE_USAGE');
   const a=records.get('valera'),b=records.get('specialist'),cost=a.cost_usd+b.cost_usd;
   if(!Number.isFinite(cost))throw Error('UNKNOWN_PROVIDER_COST');
   return {input_tokens:sum(a.input_tokens,b.input_tokens),output_tokens:sum(a.output_tokens,b.output_tokens),cost_usd:cost};
  }
 };
}
