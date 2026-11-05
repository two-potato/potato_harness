// Host-side model gateway. Worker text has no file, shell, MCP or delegation tools.
import {createServer} from 'node:net';
import {randomBytes} from 'node:crypto';
import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
import { createOpencodeClient,createOpencodeServer } from '@opencode-ai/sdk';
import {fileURLToPath} from 'node:url';
import {validateAssignment} from './contracts.mjs';
import {prepareProject,ROLES} from './profile.mjs';
let server,session,client;
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'potato-model-'));
try{
 const input=await new Response(Bun.stdin.stream()).text();
 if(Buffer.byteLength(input)>262144)throw Error('Oversized model request');
 const request=JSON.parse(input);
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
 const deadline=AbortSignal.timeout(120000);
 const availablePort=await new Promise((resolve,reject)=>{const socket=createServer();socket.once('error',reject);socket.listen(0,'127.0.0.1',()=>{const port=socket.address().port;socket.close(error=>error?reject(error):resolve(port));});});
 server=await createOpencodeServer({hostname:'127.0.0.1',port:availablePort,timeout:30000,config,signal:deadline});
 client=createOpencodeClient({baseUrl:server.url,directory:temporary,throwOnError:true,signal:deadline,headers:{Authorization:'Basic '+Buffer.from('potato:'+password).toString('base64')}});
 const roster=await client.app.agents();
 if(!roster.data?.find(a=>a.name==='valera-ceo')?.description?.includes('[OMO 5.1.60 + Potato Harness]'))throw Error('OMO composition not active');
 const coordination=request.coordination;
 if(!coordination||typeof coordination.objective!=='string'||!Array.isArray(coordination.scope))throw Error('Host-approved coordination summary required');
 const planning=await client.session.create({body:{title:'Potato control-only assignment'}});
 let planAnswer;
 try{planAnswer=await client.session.prompt({path:{id:planning.data.id},body:{agent:'valera-ceo',parts:[{type:'text',text:JSON.stringify({objective:coordination.objective,scope:coordination.scope,approved_owner:request.role,instructions:'You coordinate only. Do not inspect source or use tools. Return exactly JSON {owner: approved_owner, reason: short routing explanation}.'})}],tools:{}}});}
 finally{await client.session.delete({path:{id:planning.data.id}});}
 if(planAnswer.data.info.error||planAnswer.data.parts.some(p=>p.type==='tool'))throw Error('Coordinator planning failed');
 validateAssignment(JSON.parse(planAnswer.data.parts.filter(p=>p.type==='text').map(p=>p.text).join('')),request.role);
 const created=await client.session.create({body:{title:'Potato scoped specialist'}});session=created.data.id;
 const answer=await client.session.prompt({path:{id:session},body:{agent:request.role,parts:[{type:'text',text:request.prompt+'\nReturn exactly JSON: {"edits":[{"path":"relative/file","content":"complete new text"}],"summary":"short explanation"}. No Markdown. No tool calls.'}],tools:{}}});
 const data=answer.data;
 if(data.info.error)throw Error('Model provider failed');
 if(data.parts.some(p=>p.type==='tool'))throw Error('Unexpected model tool request');
 const text=data.parts.filter(p=>p.type==='text').map(p=>p.text).join('');
 if(Buffer.byteLength(text)>1048576)throw Error('Oversized proposal');
 const proposal=JSON.parse(text);
 if(!proposal||Object.keys(proposal).sort().join(',')!=='edits,summary'||!Array.isArray(proposal.edits)||proposal.edits.length>16||typeof proposal.summary!=='string'||proposal.summary.length>4096)throw Error('Invalid proposal');
 for(const edit of proposal.edits)if(!edit||Object.keys(edit).sort().join(',')!=='content,path'||typeof edit.path!=='string'||typeof edit.content!=='string'||Buffer.byteLength(edit.content)>65536)throw Error('Invalid edit');
 const tokens=data.info.tokens;
 const finite=n=>typeof n==='number'&&Number.isFinite(n)&&n>=0;
 const planningTokens=planAnswer.data.info.tokens;
 const planInput=planningTokens.input+(planningTokens.cache?.read||0)+(planningTokens.cache?.write||0);
 const planOutput=planningTokens.output+planningTokens.reasoning;
 const inputTokens=planInput+tokens.input+(tokens.cache?.read||0)+(tokens.cache?.write||0),outputTokens=planOutput+tokens.output+tokens.reasoning;
 if(!Number.isSafeInteger(inputTokens)||!Number.isSafeInteger(outputTokens)||inputTokens<0||outputTokens<0)throw Error('Missing token accounting');
 console.log(JSON.stringify({...proposal,usage:{input_tokens:inputTokens,output_tokens:outputTokens,cost_usd:finite(data.info.cost)&&finite(planAnswer.data.info.cost)?data.info.cost+planAnswer.data.info.cost:null}}));
}catch{
 console.error('OpenCode/OMO specialist request failed. Inspect host provider setup; raw prompts and credentials omitted.');process.exitCode=2;
}finally{
 if(client&&session)try{await client.session.delete({path:{id:session}});}catch{}
 server?.close();fs.rmSync(temporary,{recursive:true,force:true});
}
