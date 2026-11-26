// Configuration staging and read-only policy snapshot for an operator-owned server.
// This is deliberately a deny-dispatch diagnostic, not a live adapter.
import fs from 'node:fs';
import path from 'node:path';
import {candidateConfig} from './contracts.mjs';
import {modelRef,pluginSource,verifyServerSnapshot} from './server-policy.mjs';
import {ROLES} from './profile.mjs';
import {attachedFetch,ATTACHED_ENDPOINT} from './attached-server-probe.mjs';
import {withTimeout} from './bridge_limits.mjs';

const maxOutput=1024;
export function attachedModelRef(model){
 if(typeof model!=='string'||model.length>200||model.includes('..'))throw Error('EXPLICIT_FREE_MODEL_REQUIRED');
 if(model.startsWith('opencode/'))return modelRef(model);
 if(!/^openrouter\/[a-z0-9][a-z0-9._-]{0,126}\/[a-z0-9][a-z0-9._-]{0,126}:free$/.test(model))
  throw Error('EXPLICIT_FREE_MODEL_REQUIRED');
 return {providerID:'openrouter',id:model.slice('openrouter/'.length)};
}
export function buildProfile(directory,model){
 if(typeof directory!=='string'||!path.isAbsolute(directory)||path.normalize(directory)!==directory)throw Error('ABSOLUTE_DIRECTORY_REQUIRED');
 const ref=attachedModelRef(model),plugin=path.join(directory,'policy');
 const config=candidateConfig(maxOutput,{requestModel:model,modelRef:ref});
 delete config.providers; // Retain operator provider credentials and routes, never rewrite prices.
 config.plugins=[...config.plugins,plugin];
 config.policies=[
  {action:'tool.use',resource:'*',effect:'deny'},
  {action:'mcp.use',resource:'*',effect:'deny'},
  {action:'websearch.use',resource:'*',effect:'deny'}
 ];
 // Always offline-stop at the model hook. No option enables dispatch.
 return {config,ref,plugin,source:pluginSource(config,ref,maxOutput,'backend',undefined,true)};
}
function privateDir(dir){
 const s=fs.lstatSync(dir);
 if(!s.isDirectory()||s.uid!==process.getuid()||(s.mode&0o077)!==0||fs.realpathSync(dir)!==dir)
  throw Error('PRIVATE_DIRECTORY_REQUIRED');
}
function privateRead(file){
 const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);
 try{
  const s=fs.fstatSync(fd);
  if(!s.isFile()||s.uid!==process.getuid()||s.nlink!==1||(s.mode&0o077)!==0||s.size>2*1024*1024)
   throw Error('PRIVATE_FILE_REQUIRED');
  return fs.readFileSync(fd,'utf8');
 }finally{fs.closeSync(fd);}
}
export function prepareProfile(directory,model){
 const profile=buildProfile(directory,model);
 if(!process.getuid||process.getuid()===0)throw Error('UNPRIVILEGED_OPERATOR_REQUIRED');
 privateDir(path.dirname(directory));
 fs.mkdirSync(directory,{mode:0o700}); // never overwrite, never modify ordinary config
 fs.mkdirSync(profile.plugin,{mode:0o700});
 fs.writeFileSync(path.join(directory,'profile.json'),JSON.stringify(profile.config,null,2)+'\n',{mode:0o600,flag:'wx'});
 fs.writeFileSync(path.join(profile.plugin,'server.mjs'),profile.source,{mode:0o600,flag:'wx'});
 return {status:'PREPARED',roles:ROLES.length,model,profile_directory:directory,
  dispatch_disabled:true,runtime_admission:false};
}
export async function inspectPolicy({directory,model,password,clientFactory,send}){
 const report={status:'HOLD',layer:'attached-policy-snapshot',model,roles_loaded:0,
  policy_snapshot_verified:false,external_inference:false,attempted_prompts:0,runtime_admission:false};
 const controller=new AbortController();
 try{
  const profile=buildProfile(directory,model);
  privateDir(directory);privateDir(profile.plugin);
  if(privateRead(path.join(directory,'profile.json'))!==JSON.stringify(profile.config,null,2)+'\n'||
     privateRead(path.join(profile.plugin,'server.mjs'))!==profile.source)
   return {...report,reason:'LOCAL_PROFILE_MISMATCH'};
  const client=clientFactory({baseUrl:ATTACHED_ENDPOINT,fetch:attachedFetch({password,signal:controller.signal,send})});
  const health=await withTimeout(()=>client.server.info(),5000);
  if(health?.version!=='2.4.1')return {...report,reason:'SERVER_VERSION_MISMATCH'};
  const location={directory};
  const [plugins,agents,models]=await withTimeout(()=>Promise.all([
   client.plugin.list({location}),client.agent.list({location}),client.model.list({location})
  ]),15000);
  if(Array.isArray(agents?.data))report.roles_loaded=ROLES.filter(r=>agents.data.some(a=>a.id===r)).length;
  if(!verifyServerSnapshot({plugins,agents,models},profile.config,profile.ref,maxOutput,profile.plugin))
   return {...report,reason:'SERVER_POLICY_SNAPSHOT_MISMATCH'};
  return {...report,status:'PASS',policy_snapshot_verified:true,reason:'SNAPSHOT_ONLY'};
 }catch{
  return {...report,reason:'PROFILE_OR_SERVER_UNAVAILABLE'};
 }finally{controller.abort();}
}
if(import.meta.main){
 let report;
 try{
  const [action,directory,model,...extra]=process.argv.slice(2);
  if(extra.length||!directory||!model)throw Error('INVALID_ARGUMENTS');
  if(action==='prepare')report=prepareProfile(directory,model);
  else if(action==='check'){
   const {OpenCode}=await import('@opencode/client');
   report=await inspectPolicy({directory,model,password:process.env.POTATO_OPENCODE_PASSWORD,clientFactory:OpenCode.make});
  }else throw Error('INVALID_ARGUMENTS');
 }catch{
  report={status:'HOLD',reason:'PROFILE_SETUP_HOLD',external_inference:false,runtime_admission:false};
 }
 console.log(JSON.stringify(report,null,2));
 process.exitCode=['PASS','PREPARED'].includes(report.status)?0:2;
}
