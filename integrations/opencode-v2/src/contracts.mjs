// Native v2 profiles; the trusted host selects fixture or Console.
import {ROLES,rolePrompts} from './profile.mjs';
import {validateAssignment} from './assignment.mjs';
import {combineModelUsage} from './bridge_accounting.mjs';
export const FIXTURE_MODEL='fixture/test';
export const MODEL_REF=Object.freeze({providerID:'fixture',id:'test'});
export const FIXTURE_URL='https://potato-fixture.invalid/v1/chat/completions';
export const CONSOLE_PROFILE=Object.freeze({requestModel:'opencode/minimax-m3',modelRef:Object.freeze({providerID:'potato-console',id:'minimax-m3'})});
export const FIXTURE_PROFILE=Object.freeze({requestModel:FIXTURE_MODEL,modelRef:MODEL_REF});
export const deny=()=>[{action:'*',resource:'*',effect:'deny'}];

export function validateRequest(request,profile=FIXTURE_PROFILE){
 if(!request||request.model!==profile.requestModel||!ROLES.includes(request.role)||request.role==='valera-ceo'||typeof request.prompt!=='string'||Buffer.byteLength(request.prompt)>262144)throw Error('V2_CANDIDATE_FIXTURE_ONLY');
 if(!Number.isSafeInteger(request.output_token_allowance)||request.output_token_allowance<2||request.output_token_allowance>4096)throw Error('INVALID_ALLOWANCE');
 const c=request.coordination;
 if(!c||typeof c.objective!=='string'||!Array.isArray(c.scope)||c.scope.some(p=>typeof p!=='string'))throw Error('INVALID_COORDINATION');
 return Math.floor(request.output_token_allowance/2);
}
export function candidateConfig(maxOutput,profile=FIXTURE_PROFILE){
 const modelRef=profile.modelRef,modelName=modelRef.providerID+'/'+modelRef.id;
 const prompts=rolePrompts();
 const agents=Object.fromEntries(ROLES.map(role=>[role,{
  model:modelName,mode:role==='valera-ceo'?'primary':'subagent',
  description:'Potato Harness '+role,system:prompts[role],
  permissions:deny(),steps:1
 }]));
 return {model:modelName,default_agent:'valera-ceo',update:'disable',share:'disabled',
  automations:false,snapshots:false,formatter:false,lsp:false,warming:false,
  // v2 starts these discovery plugins even without a configured local model.
  plugins:['-opencode.provider.ollama','-opencode.provider.lmstudio','-opencode.provider.vllm'],
  compaction:{auto:false,background:false},permissions:deny(),agents,
  providers:{[modelRef.providerID]:{name:'Potato isolated transport',package:'@opencode/ai/providers/openai-compatible',
   settings:{baseURL:'https://potato-fixture.invalid/v1',apiKey:'fixture-only'},
   models:{[modelRef.id]:{name:modelRef.id,capabilities:{tools:false,input:['text'],output:['text']},
    limit:{context:128000,output:maxOutput},cost:{input:0,output:0}}}}}
 };
}
// The pinned v2 message endpoint emits cursor.next even for the last nonempty
// page. Read from the beginning and prove the bounded transcript is complete
// by checking that the next page is empty; never silently truncate history.
export async function readBoundedMessages(read,sessionID){
 const page=await read({sessionID,order:'asc',limit:100});
 if(!Array.isArray(page?.data)||page.data.length>100)throw Error('INVALID_MESSAGE_PAGE');
 if(page.data.length){
  const cursor=page.cursor?.next;
  if(typeof cursor!=='string'||!cursor||cursor.length>4096)throw Error('MISSING_MESSAGE_CURSOR');
  const tail=await read({sessionID,cursor,limit:1});
  if(!Array.isArray(tail?.data)||tail.data.length!==0)throw Error('UNEXPECTED_MESSAGE_PAGINATION');
 }
 return page;
}
export function parseAssistant(messages,role,modelRef=MODEL_REF){
 if(!Array.isArray(messages)||messages.some(m=>!m||!['agent-switched','model-switched','location-switched','user','assistant','idle'].includes(m.type)))throw Error('UNEXPECTED_SESSION_ACTIVITY');
 const answers=messages.filter(m=>m.type==='assistant');
 if(answers.length!==1)throw Error('EXPECTED_ONE_ASSISTANT');
 const a=answers[0];
 if(a.error)throw a.error;
 if(a.retry||a.agent!==role||a.model?.providerID!==modelRef.providerID||a.model?.id!==modelRef.id||a.finish!=='stop'||!a.time?.completed||!Array.isArray(a.content)||a.content.some(p=>!['text','reasoning'].includes(p.type)))throw Error('UNSAFE_ASSISTANT_RESULT');
 const text=a.content.filter(p=>p.type==='text').map(p=>p.text).join('');
 if(Buffer.byteLength(text)>1048576)throw Error('OVERSIZED_RESULT');
 return {value:JSON.parse(text),info:a};
}
export function combine(plan,answer,role,scope){
 validateAssignment(plan.value,role);
 const p=answer.value;
 if(!p||Object.keys(p).sort().join(',')!=='edits,summary'||!Array.isArray(p.edits)||!p.edits.length||p.edits.length>16||typeof p.summary!=='string'||p.summary.length>4096)throw Error('INVALID_PROPOSAL');
 const seen=new Set();
 for(const e of p.edits){
  if(!e||Object.keys(e).sort().join(',')!=='content,path'||typeof e.path!=='string'||!scope.includes(e.path)||seen.has(e.path)||typeof e.content!=='string'||Buffer.byteLength(e.content)>65536)throw Error('INVALID_EDIT');
  seen.add(e.path);
 }
 // Map SDK fixture token fields to the host counters.
 // Missing cost must remain null; fixture zero prices do not establish live cost.
 return {...p,usage:combineModelUsage(plan.info,answer.info)};
}
