// SDK usage is reported by the provider bridge; cost is not proof of final billing.
function count(value,optional=false){
 if(optional&&value===undefined)return 0;
 if(!Number.isSafeInteger(value)||value<0)throw Error('Missing or invalid token accounting');
 return value;
}
function tokens(info){
 const t=info?.tokens;
 if(!t||typeof t!=='object'||Array.isArray(t))throw Error('Missing token accounting');
 const cache=t.cache===undefined?{}:t.cache;
 if(!cache||typeof cache!=='object'||Array.isArray(cache))throw Error('Invalid cache accounting');
 return {input:count(t.input)+count(cache.read,true)+count(cache.write,true),output:count(t.output)+count(t.reasoning,true)};
}
function cost(info){
 const v=info?.cost;
 return typeof v==='number'&&Number.isFinite(v)&&v>=0?v:null;
}
export function combineModelUsage(coordinator,specialist){
 const a=tokens(coordinator),b=tokens(specialist);
 const input=a.input+b.input,output=a.output+b.output;
 if(!Number.isSafeInteger(input)||!Number.isSafeInteger(output))throw Error('Token total overflow');
 const x=cost(coordinator),y=cost(specialist);
 const sum=x===null||y===null?null:x+y;
 return {input_tokens:input,output_tokens:output,cost_usd:sum!==null&&Number.isFinite(sum)?sum:null};
}
