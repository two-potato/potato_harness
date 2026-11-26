// Self-contained guard embedded only in the attached trial's audited plugin.
// Not an OS egress firewall, provider billing receipt, or global server policy.
export async function attachedWireRequest(request,ref,cap){
 const deny=()=>{throw Error('ATTACHED_WIRE_DENIED');};
 const record=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
 const keys=(x,allowed)=>record(x)&&Object.keys(x).every(k=>allowed.includes(k));
 const bounded=n=>Number.isSafeInteger(n)&&n>0&&n<=cap;
 if(!(request instanceof Request)||request.url!=='https://openrouter.ai/api/v1/chat/completions'||
    request.method!=='POST'||request.bodyUsed||!request.body||
    ref?.providerID!=='openrouter'||ref.id!=='nvidia/nemotron-3-ultra-550b-a55b:free'||
    !Number.isSafeInteger(cap)||cap<1||cap>1024)deny();
 const headers=new Headers(request.headers);
 const allowedHeaders=['authorization','content-type','accept','accept-encoding','user-agent',
  'http-referer','x-title','x-openrouter-title','x-openrouter-categories','x-openrouter-app-url','content-length'];
 if([...headers.keys()].some(k=>!allowedHeaders.includes(k))||
    headers.get('content-type')?.split(';')[0].trim().toLowerCase()!=='application/json')deny();
 // Read a bounded clone, leaving the original request untouched. The replacement
 // is reserialized, eliminating duplicate JSON keys and unknown top-level options.
 const reader=request.clone().body.getReader(),chunks=[];
 let length=0;
 try{
  while(true){
   const {done,value}=await reader.read();if(done)break;
   length+=value.byteLength;
   if(length>262144){void reader.cancel().catch(()=>{});deny();}
   chunks.push(value);
  }
 }finally{reader.releaseLock();}
 let b;
 try{b=JSON.parse(Buffer.concat(chunks,length).toString('utf8'));}catch{deny();}
 if(!keys(b,['model','messages','stream','max_tokens','max_completion_tokens','temperature','top_p',
  'frequency_penalty','presence_penalty','seed','stop','stream_options','usage','reasoning','tools',
  'parallel_tool_calls','provider','response_format','store'])||
    b.model!==ref.id||b.stream!==true||
    ((b.max_tokens===undefined)===(b.max_completion_tokens===undefined))||
    !bounded(b.max_tokens??b.max_completion_tokens)||
    !Array.isArray(b.messages)||b.messages.length<1||b.messages.length>32)deny();
 if(b.tools!==undefined&&(!Array.isArray(b.tools)||b.tools.length!==0))deny();
 if(b.parallel_tool_calls!==undefined&&b.parallel_tool_calls!==false)deny();
 if(b.store!==undefined&&b.store!==false)deny();
 for(const m of b.messages){
  if(!keys(m,['role','content'])||!['system','developer','user'].includes(m.role))deny();
  if(typeof m.content!=='string'&&(!Array.isArray(m.content)||!m.content.length||
     m.content.some(p=>!keys(p,['type','text'])||p.type!=='text'||typeof p.text!=='string')))deny();
 }
 if(b.messages.filter(m=>m.role==='user').length!==1)deny();
 for(const k of ['temperature','top_p','frequency_penalty','presence_penalty','seed'])
  if(b[k]!==undefined&&(typeof b[k]!=='number'||!Number.isFinite(b[k])))deny();
 if(b.stop!==undefined&&!(typeof b.stop==='string'||Array.isArray(b.stop)&&b.stop.every(x=>typeof x==='string')))deny();
 if(b.stream_options!==undefined&&(!keys(b.stream_options,['include_usage'])||b.stream_options.include_usage!==true))deny();
 if(b.usage!==undefined&&(!keys(b.usage,['include'])||b.usage.include!==true))deny();
 if(b.response_format!==undefined&&(!keys(b.response_format,['type'])||!['text','json_object'].includes(b.response_format.type)))deny();
 if(b.reasoning!==undefined&&(!keys(b.reasoning,['enabled','exclude','effort','max_tokens'])||
   ['enabled','exclude'].some(k=>b.reasoning[k]!==undefined&&typeof b.reasoning[k]!=='boolean')||
   b.reasoning.effort!==undefined&&!['none','minimal','low','medium','high','xhigh','max'].includes(b.reasoning.effort)||
   b.reasoning.max_tokens!==undefined&&(!bounded(b.reasoning.max_tokens)||b.reasoning.max_tokens>=(b.max_tokens??b.max_completion_tokens))))deny();
 if(b.provider!==undefined&&(!keys(b.provider,['allow_fallbacks','max_price'])||
   b.provider.allow_fallbacks!==undefined&&b.provider.allow_fallbacks!==false||
   b.provider.max_price!==undefined&&(!keys(b.provider.max_price,['prompt','completion','request','image'])||
    Object.values(b.provider.max_price).some(v=>v!==0))))deny();
 b.provider={allow_fallbacks:false,max_price:{prompt:0,completion:0,request:0,image:0}};
 b.usage={include:true};
 headers.delete('content-length');
 return new Request(request.url,{method:'POST',headers,body:JSON.stringify(b),redirect:'error',signal:request.signal});
}
