// Owned foreground CLI child; no existing server attachment or provider-key forwarding.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {randomBytes} from 'node:crypto';
import {spawn} from 'node:child_process';
import {withTimeout} from './bridge_limits.mjs';
import {modelRef,nativeConfig,pluginSource,verifyServerSnapshot} from './server-policy.mjs';

export function parseEndpoint(line){
 const obj=JSON.parse(line);
 if(Object.keys(obj).join(',')!=='url'||typeof obj.url!=='string'||!/^http:\/\/127\.0\.0\.1:[0-9]{1,5}$/.test(obj.url))throw Error('UNSAFE_SERVER_ENDPOINT');
 const u=new URL(obj.url),port=Number(u.port);
 if(!Number.isInteger(port)||port<1||port>65535)throw Error('UNSAFE_SERVER_ENDPOINT');
 return obj.url;
}
export function localFetch(endpoint,password,signal,send=globalThis.fetch){
 const origin=new URL(endpoint).origin;
 return async(input,init)=>{
  const request=new Request(input,init);
  const url=new URL(request.url);
  if(url.origin!==origin||url.username||url.password||signal?.aborted)throw Error('LOCAL_SERVER_ONLY');
  const headers=new Headers(request.headers);
  headers.set('Authorization','Basic '+Buffer.from('opencode:'+password).toString('base64'));
  return send(new Request(request,{headers,redirect:'error',signal:signal?AbortSignal.any([request.signal,signal]):request.signal}));
 };
}
function privateDir(dir){
 fs.mkdirSync(dir,{recursive:true,mode:0o700});
 const stat=fs.lstatSync(dir);
 if(!stat.isDirectory()||stat.isSymbolicLink()||(stat.mode&0o077)!==0||stat.uid!==process.getuid())throw Error('UNSAFE_SERVER_STATE_DIRECTORY');
 return dir;
}
function waitEndpoint(child){
 return new Promise((resolve,reject)=>{
  let pending='',done=false;
  const fail=()=>{if(!done){done=true;reject(Error('SERVER_START_FAILED'));}};
  child.once('error',fail);child.once('exit',fail);
  child.stdout.on('data',chunk=>{
   if(done)return;
   pending+=chunk.toString('utf8');
   if(pending.length>16384){fail();return;}
   const i=pending.indexOf('\n');if(i<0)return;
   try{const endpoint=parseEndpoint(pending.slice(0,i).trim());done=true;resolve(endpoint);}
   catch{fail();}
  });
 });
}
function checkVersion(binary,env,cwd){
 return new Promise((resolve,reject)=>{
  const p=spawn(binary,['--version'],{cwd,env,stdio:['ignore','pipe','ignore']});
  let out='';
  const timer=setTimeout(()=>{p.kill('SIGKILL');reject(Error('CLI_VERSION_TIMEOUT'));},4000);
  p.stdout.on('data',b=>{out+=b.toString();if(out.length>1024)p.kill('SIGKILL');});
  p.once('error',()=>{clearTimeout(timer);reject(Error('CLI_VERSION_FAILED'));});
  p.once('close',code=>{clearTimeout(timer);if(code===0&&/^(?:opencode v?)?2\.4\.1$/.test(out.trim()))resolve();else reject(Error('CLI_VERSION_MISMATCH'));});
 });
}
export async function launchPrivateServer({binary,operatorHome,model,worker='backend',maxOutput=2048,clientFactory}){
 if(typeof binary!=='string'||!path.isAbsolute(binary)||!fs.statSync(binary).isFile())throw Error('ABSOLUTE_CLI_REQUIRED');
 if(typeof operatorHome!=='string'||!path.isAbsolute(operatorHome))throw Error('ABSOLUTE_HOME_REQUIRED');
 const ref=modelRef(model);
 // Stable, private state for the official client; never rotate it to evade quotas.
 const root=privateDir(path.join(operatorHome,'.local/state/potato-harness/opencode-free'));
 const data=privateDir(path.join(root,'data')),cache=privateDir(path.join(root,'cache')),state=privateDir(path.join(root,'state'));
 const directory=fs.mkdtempSync(path.join(root,'run-'));
 const plugin=privateDir(path.join(directory,'policy'));
 const config=nativeConfig(model,maxOutput,plugin);
 fs.writeFileSync(path.join(plugin,'server.mjs'),pluginSource(config,ref,maxOutput,worker),{mode:0o600});
 const password=randomBytes(32).toString('base64url'),abort=new AbortController();
 const env={PATH:'/usr/bin:/bin',HOME:root,XDG_DATA_HOME:data,XDG_CACHE_HOME:cache,XDG_STATE_HOME:state,
  XDG_CONFIG_HOME:directory,OPENCODE_CONFIG_DIR:directory,OPENCODE_CONFIG_CONTENT:JSON.stringify(config),
  OPENCODE_DB:':memory:',OPENCODE_CONFIG_PROJECT_DISABLE:'1',OPENCODE_DISABLE_CLAUDE_CODE:'1',
  OPENCODE_FILEWATCHER_DISABLE:'1',OPENCODE_DISABLE_FFF:'1',DO_NOT_TRACK:'1',OPENCODE_PASSWORD:password};
 let child,exited,closed=false;
 const close=async()=>{
  if(closed)return;closed=true;abort.abort();
  try{
   if(child&&child.exitCode===null&&child.signalCode===null){
    child.stdin.end();
    try{await withTimeout(()=>exited,1000);}catch{child.kill('SIGKILL');await withTimeout(()=>exited,1000);}
   }
  }finally{fs.rmSync(directory,{recursive:true,force:true});}
 };
 try{
  await checkVersion(binary,env,directory);
  child=spawn(binary,['serve','--stdio','--hostname','127.0.0.1','--port','0'],{cwd:directory,env,stdio:['pipe','pipe','ignore']});
  child.stdin.on('error',()=>{});
  exited=new Promise(resolve=>{child.once('exit',resolve);child.once('error',resolve);});
  const endpoint=await withTimeout(()=>waitEndpoint(child),10000);
  const client=clientFactory({baseUrl:endpoint,fetch:localFetch(endpoint,password,abort.signal)});
  const health=await withTimeout(()=>client.server.info(),5000);
  if(health?.version!=='2.4.1')throw Error('SERVER_VERSION_MISMATCH');
  return {client,directory,config,ref,plugin,maxOutput,close};
 }catch(e){await close();throw e;}
}
export async function awaitServerPolicy(server,{now=()=>performance.now(),pause=()=>new Promise(r=>setTimeout(r,100)),timeout=15000}={}){
 const {client,directory,config,ref,maxOutput,plugin}=server;
 const location={directory},end=now()+timeout;
 do{
  const [plugins,agents,models]=await Promise.all([
   client.plugin.list({location}),client.agent.list({location}),client.model.list({location})
  ]);
  if(verifyServerSnapshot({plugins,agents,models},config,ref,maxOutput,plugin))return;
  await pause();
 }while(now()<end);
 throw Error('SERVER_POLICY_OR_FREE_MODEL_NOT_READY');
}
