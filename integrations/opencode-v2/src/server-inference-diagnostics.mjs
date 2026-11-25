// Fixed diagnostic categories; never serialize a response, exception or unknown event.
import {BridgeDeadlineError} from './bridge_limits.mjs';
import {auditSequence,auditViolation} from './server-audit.mjs';
const kinds=['agent-switched','model-switched','location-switched','user','assistant','idle','synthetic','system','skill','shell','compaction'];
const finishes=['stop','length','tool-calls','content-filter','error','unknown'];
export function errorCategory(error){
 if(error instanceof BridgeDeadlineError)return 'DEADLINE';
 if(error instanceof SyntaxError)return 'INVALID_JSON';
 const status=error?.status??error?.statusCode??error?.data?.statusCode;
 if(status===401||status===403)return 'AUTH';
 if(status===429)return 'RATE_LIMIT';
 if(typeof status==='number'&&status>=500&&status<=599)return 'PROVIDER_UNAVAILABLE';
 if(status===400||status===404||status===422)return 'REQUEST_REJECTED';
 const types=new Map([['permission.rejected','PERMISSION_REJECTED'],['provider.no-route','NO_ROUTE'],['provider.free-limit','FREE_LIMIT'],['provider.quota','QUOTA'],['provider.rate-limit','RATE_LIMIT'],['provider.auth','AUTH'],['provider.transport','TRANSPORT'],['provider.internal','PROVIDER_UNAVAILABLE'],['provider.timeout','DEADLINE'],['provider.invalid-request','REQUEST_REJECTED'],['provider.invalid-output','INVALID_OUTPUT'],['provider.unsupported-operation','UNSUPPORTED'],['provider.budget-limit','BUDGET_LIMIT'],['provider.model-budget-limit','BUDGET_LIMIT'],['provider.go-limit','QUOTA'],['tool.execution','TOOL_EXECUTION']]);
 return types.get(error?.type)??'REJECTED';
}
export function responseShape(messages,role,ref){
 if(!Array.isArray(messages)||messages.length>100)return null;
 const counts=Object.fromEntries(kinds.map(k=>[k,0]));counts.other=0;
 for(const m of messages)counts[kinds.includes(m?.type)?m.type:'other']++;
 const a=messages.filter(m=>m?.type==='assistant');
 const idle=messages.filter(m=>m?.type==='idle');
 const summary={counts};
 if(idle.length===1){const x=idle[0];summary.idle={outcome:['succeeded','failed','interrupted'].includes(x.outcome)?x.outcome:'ABSENT_OR_OTHER',error:x.error?errorCategory(x.error):'NONE'};}
 if(a.length!==1)return summary;
 const x=a[0],parts=Array.isArray(x.content)?x.content:null;
 const cost=x.cost;
 return {...summary,assistant:{
  agent_match:x.agent===role,model_match:x.model?.providerID===ref.providerID&&x.model?.id===ref.id,
  variant_absent:x.model?.variant===undefined,completed:!!x.time?.completed,retry:!!x.retry,
  error:x.error?errorCategory(x.error):'NONE',
  finish:finishes.includes(x.finish)?x.finish:'ABSENT_OR_OTHER',
  parts_valid:!!parts&&parts.every(p=>p?.type==='text'||p?.type==='reasoning'),
  text_present:!!parts&&parts.some(p=>p?.type==='text'&&typeof p.text==='string'&&p.text.length>0),
  cost_state:cost===undefined||cost===null?'MISSING':cost===0?'ZERO':typeof cost==='number'&&Number.isFinite(cost)&&cost>0?'POSITIVE':'INVALID',
  tokens_present:!!x.tokens
 }};
}
export function auditShape(actual,worker){
 if(!Array.isArray(actual)||actual.length>1024)return null;
 const expected=auditSequence(worker);
 return {ready:actual.includes('ready'),
  model_hooks:actual.filter(x=>x==='model:valera-ceo'||x==='model:'+worker).length,
  http_hooks:actual.filter(x=>x==='http:valera-ceo'||x==='http:'+worker).length,
  violation:actual.some(x=>auditViolation(x)!==null),
  violation_reason:actual.map(auditViolation).find(x=>x!==null)??null,
  valid_prefix:actual.every((x,i)=>x===expected[i])};
}
