// Candidate only. Keep the existing host wire contract and refuse live requests.
import {ROLES,harnessConfig} from '../../opencode/src/profile.mjs';
import {validateAssignment} from '../../opencode/src/contracts.mjs';
import {combineModelUsage} from '../../opencode/src/bridge_accounting.mjs';
export const FIXTURE_MODEL='fixture/test';
export const MODEL_REF=Object.freeze({providerID:'fixture',id:'test'});
export const FIXTURE_URL='https://potato-fixture.invalid/v1/chat/completions';
export const deny=()=>[{action:'*',resource:'*',effect:'deny'}];

export function validateRequest(request){
 if(!request||request.model!==FIXTURE_MODEL||!ROLES.includes(request.role)||request.role==='valera-ceo'||typeof request.prompt!=='string'||Buffer.byteLength(request.prompt)>262144)throw Error('V2_CANDIDATE_FIXTURE_ONLY');
 if(!Number.isSafeInteger(request.output_token_allowance)||request.output_token_allowance<2||request.output_token_allowance>4096)throw Error('INVALID_ALLOWANCE');
 const c=request.coordination;
 if(!c||typeof c.objective!=='string'||!Array.isArray(c.scope)||c.scope.some(p=>typeof p!=='string'))throw Error('INVALID_COORDINATION');
 return Math.floor(request.output_token_allowance/2);
}
export function candidateConfig(maxOutput){
 const old=harnessConfig(FIXTURE_MODEL);
 const agents=Object.fromEntries(ROLES.map(role=>[role,{
  model:FIXTURE_MODEL,mode:role==='valera-ceo'?'primary':'subagent',
  description:'Potato Harness v2 candidate '+role,system:old.agent[role].prompt,
  permissions:deny(),steps:1
 }]));
 return {model:FIXTURE_MODEL,default_agent:'valera-ceo',update:'disable',share:'disabled',
  automations:false,snapshots:false,formatter:false,lsp:false,warming:false,
  compaction:{auto:false,background:false},permissions:deny(),agents,
  providers:{fixture:{name:'Potato fixture',package:'@opencode/ai/providers/openai-compatible',
   settings:{baseURL:'https://potato-fixture.invalid/v1',apiKey:'fixture-only'},
   models:{test:{name:'Fixture',capabilities:{tools:false,input:['text'],output:['text']},
    limit:{context:128000,output:maxOutput},cost:{input:0,output:0}}}}}
 };
}
export function parseAssistant(messages,role){
 if(!Array.isArray(messages)||messages.some(m=>!m||!['agent-switched','model-switched','location-switched','user','assistant','idle'].includes(m.type)))throw Error('UNEXPECTED_SESSION_ACTIVITY');
 const answers=messages.filter(m=>m.type==='assistant');
 if(answers.length!==1)throw Error('EXPECTED_ONE_ASSISTANT');
 const a=answers[0];
 if(a.error)throw a.error;
 if(a.retry||a.agent!==role||a.model?.providerID!==MODEL_REF.providerID||a.model?.id!==MODEL_REF.id||a.finish!=='stop'||!a.time?.completed||!Array.isArray(a.content)||a.content.some(p=>!['text','reasoning'].includes(p.type)))throw Error('UNSAFE_ASSISTANT_RESULT');
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
 // The SDK contract differs from v1, but its token fields map to the same host counters.
 // Missing cost must remain null; fixture zero prices do not establish live cost.
 return {...p,usage:combineModelUsage(plan.info,answer.info)};
}
