// Host-side model gateway. Worker text has no file, shell, MCP or delegation tools.
import {createServer} from 'node:net';
import {randomBytes} from 'node:crypto';
import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
import { createOpencodeClient,createOpencodeServer } from '@opencode-ai/sdk';
import {fileURLToPath} from 'node:url';
import {validateAssignment} from './contracts.mjs';
import {prepareProject,ROLES} from './profile.mjs';
import {bridgeBudget,withTimeout,SESSION_DELETE_TIMEOUT_MS,FINALIZATION_RESERVE_MS} from './bridge_limits.mjs';
import {combineModelUsage} from './bridge_accounting.mjs';
import {valeraFailure} from './valera_diagnostics.mjs';
// Only fixed, non-secret phase markers may reach the trusted host.
let activePhase=null,phaseStarted=0,valeraStep='unknown';
function beginPhase(phase){activePhase=phase;phaseStarted=performance.now();emitPhase('start');}
function emitPhase(status,detail={}){if(activePhase)console.error('POTATO_GATEWAY_PHASE '+JSON.stringify({phase:activePhase,status,elapsed_ms:Math.max(0,Math.round(performance.now()-phaseStarted)),...detail}));}
function endPhase(status,detail){emitPhase(status,detail);activePhase=null;}
let server,session,client;
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'potato-model-'));
try{
 beginPhase('request');
 const input=await new Response(Bun.stdin.stream()).text();
 if(Buffer.byteLength(input)>262144)throw Error('Oversized model request');
 const request=JSON.parse(input);
 const budget=bridgeBudget(request.bridge_timeout_ms??75_000);
 if(!ROLES.includes(request.role)||request.role==='valera-ceo'||typeof request.prompt!=='string')throw Error('Invalid specialist request');
 const fixtureURL=process.env.POTATO_PROVIDER_FIXTURE_URL;
 if(fixtureURL && (request.model!=='fixture/test'||process.env.OPENCODE_API_KEY||!/^http:\/\/127\.0\.0\.1:[0-9]+\/v1$/.test(fixtureURL)))throw Error('Unsafe test provider configuration');
 // Use an empty host-owned provider directory, never untrusted checkout config.
 process.env.PATH=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../node_modules/.bin')+':/usr/bin:/bin';
 process.chdir(temporary);
 for(const key of Object.keys(process.env))if(!['PATH','OPENCODE_API_KEY','HOME','TMPDIR','LANG'].includes(key))delete process.env[key];
 process.env.DO_NOT_TRACK='1';process.env.OMO_DISABLE_TELEMETRY='1';process.env.OMO_DISABLE_POSTHOG='1';process.env.OMO_SEND_ANONYMOUS_TELEMETRY='0';
 process.env.HOME=temporary;
 process.env.XDG_CONFIG_HOME=path.join(temporary,'config');process.env.XDG_CACHE_HOME=path.join(temporary,'cache');process.env.XDG_DATA_HOME=path.join(temporary,'data');process.env.OPENCODE_DISABLE_DEFAULT_PLUGINS='true';
 if(!Number.isSafeInteger(request.output_token_allowance)||request.output_token_allowance<1)throw Error('Finite output token allowance required');
 const maxOutput=Math.floor(Math.min(request.output_token_allowance,4096)/2);
 if(maxOutput<1)throw Error('Two bounded model outputs require token allowance >=2');
 const config=prepareProject(temporary,request.model);
 const [provider,modelID]=request.model.split('/');
 config.provider={[provider]:{models:{[modelID]:{name:modelID,limit:{context:128000,output:maxOutput}}}}};
 if(fixtureURL)Object.assign(config.provider[provider],{npm:'@ai-sdk/openai-compatible',name:'Fixture',options:{baseURL:fixtureURL,apiKey:'test-only'}});
 const password=randomBytes(32).toString('hex');
 process.env.OPENCODE_SERVER_PASSWORD=password;process.env.OPENCODE_SERVER_USERNAME='potato';
 const deadline=AbortSignal.timeout(Math.max(1,budget.remainingMs()-FINALIZATION_RESERVE_MS));
 endPhase('ok');beginPhase('server');
 const availablePort=await new Promise((resolve,reject)=>{const socket=createServer();socket.once('error',reject);socket.listen(0,'127.0.0.1',()=>{const port=socket.address().port;socket.close(error=>error?reject(error):resolve(port));});});
 server=await budget.stage(()=>createOpencodeServer({hostname:'127.0.0.1',port:availablePort,timeout:30000,config,signal:deadline}));
 client=createOpencodeClient({baseUrl:server.url,directory:temporary,throwOnError:true,signal:deadline,headers:{Authorization:'Basic '+Buffer.from('potato:'+password).toString('base64')}});
 endPhase('ok');beginPhase('omo');
 const roster=await budget.stage(()=>client.app.agents());
 if(!roster.data?.find(a=>a.name==='valera-ceo')?.description?.includes('[OMO 5.1.60 + Potato Harness]'))throw Error('OMO composition not active');
 endPhase('ok');beginPhase('valera');
 valeraStep='coordination';
 const coordination=request.coordination;
 if(!coordination||typeof coordination.objective!=='string'||!Array.isArray(coordination.scope))throw Error('Host-approved coordination summary required');
 valeraStep='session';
 const planning=await budget.stage(()=>client.session.create({body:{title:'Potato control-only assignment'}}));
 let planAnswer,promptFailed=false;
 valeraStep='prompt';
 try{planAnswer=await budget.stage(()=>client.session.prompt({path:{id:planning.data.id},body:{agent:'valera-ceo',parts:[{type:'text',text:JSON.stringify({objective:coordination.objective,scope:coordination.scope,approved_owner:request.role,instructions:'You coordinate only. Do not inspect source or use tools. Return exactly JSON {owner: approved_owner, reason: short routing explanation}.'})}],tools:{}}}));}
 catch(error){promptFailed=true;throw error;}
 finally{
  if(!promptFailed)valeraStep='close';
  try{await withTimeout(()=>client.session.delete({path:{id:planning.data.id}}),SESSION_DELETE_TIMEOUT_MS);}
  catch(error){if(!promptFailed)throw error;}
 }
 valeraStep='response';
 if(planAnswer.data.info.error)throw planAnswer.data.info.error;
 if(planAnswer.data.parts.some(p=>p.type==='tool'))throw Error('Coordinator planning failed');
 valeraStep='json';
 const plan=JSON.parse(planAnswer.data.parts.filter(p=>p.type==='text').map(p=>p.text).join(''));
 valeraStep='assignment';
 validateAssignment(plan,request.role);
 endPhase('ok');beginPhase('specialist');
 const created=await budget.stage(()=>client.session.create({body:{title:'Potato scoped specialist'}}));session=created.data.id;
 const answer=await budget.stage(()=>client.session.prompt({path:{id:session},body:{agent:request.role,parts:[{type:'text',text:request.prompt+'\nReturn exactly JSON: {"edits":[{"path":"relative/file","content":"complete new text"}],"summary":"short explanation"}. No Markdown. No tool calls.'}],tools:{}}}));
 const data=answer.data;
 if(data.info.error)throw Error('Model provider failed');
 if(data.parts.some(p=>p.type==='tool'))throw Error('Unexpected model tool request');
 const text=data.parts.filter(p=>p.type==='text').map(p=>p.text).join('');
 if(Buffer.byteLength(text)>1048576)throw Error('Oversized proposal');
 const proposal=JSON.parse(text);
 if(!proposal||Object.keys(proposal).sort().join(',')!=='edits,summary'||!Array.isArray(proposal.edits)||proposal.edits.length>16||typeof proposal.summary!=='string'||proposal.summary.length>4096)throw Error('Invalid proposal');
 for(const edit of proposal.edits)if(!edit||Object.keys(edit).sort().join(',')!=='content,path'||typeof edit.path!=='string'||typeof edit.content!=='string'||Buffer.byteLength(edit.content)>65536)throw Error('Invalid edit');
 endPhase('ok');beginPhase('usage');
 const usage=combineModelUsage(planAnswer.data.info,data.info);
 endPhase('ok');
 console.log(JSON.stringify({...proposal,usage}));
}catch(error){
 endPhase('error',activePhase==='valera'?valeraFailure(valeraStep,error):{});
 console.error('OpenCode/OMO specialist request failed. Inspect host provider setup; raw prompts and credentials omitted.');process.exitCode=2;
}finally{
 beginPhase('cleanup');
 let cleanupFailed=false;
 if(client&&session)try{
  await withTimeout(()=>client.session.delete({path:{id:session}}),SESSION_DELETE_TIMEOUT_MS);
 }catch{cleanupFailed=true;}
 try{server?.close();}catch{cleanupFailed=true;}
 endPhase(cleanupFailed?'error':'ok');
 fs.rmSync(temporary,{recursive:true,force:true});
}
