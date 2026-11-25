// Trusted host CLI, not an agent tool. Scrub environment before loading SDK.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
let home,code=2;
try{
 const mode=process.argv[2];
 if(!['fixture','console','native-free-fixture'].includes(mode)||process.argv.length!==3)throw Error('INVALID_ADAPTER_MODE');
 const key=mode==='console'?process.env.OPENCODE_API_KEY:undefined;
 if(mode==='console'&&!key)throw Error('MISSING_CONSOLE_KEY');
 for(const name of Object.keys(process.env))delete process.env[name];
 home=fs.mkdtempSync(path.join(os.tmpdir(),'potato-v2-host-'));
 Object.assign(process.env,{PATH:'/usr/bin:/bin',HOME:home,XDG_CONFIG_HOME:path.join(home,'config'),XDG_DATA_HOME:path.join(home,'data'),XDG_CACHE_HOME:path.join(home,'cache'),DO_NOT_TRACK:'1'});
 process.chdir(home);
 const raw=await new Response(Bun.stdin.stream()).text();
 if(Buffer.byteLength(raw)>262144)throw Error('OVERSIZED_REQUEST');
 const request=JSON.parse(raw);
 const onPhase=event=>fs.writeSync(2,'POTATO_GATEWAY_PHASE '+JSON.stringify(event)+'\n');
 let result;
 if(mode==='native-free-fixture'){
  const {runNativeRuntimeFixture}=await import('./server-inference.mjs');
  const {launchNativeFixture,awaitNativeFixture}=await import('./native-runtime-fixture.mjs');
  result=await runNativeRuntimeFixture(request,{launch:launchNativeFixture,awaitPolicy:awaitNativeFixture,onPhase});
 }else{
  const {OpenCode}=await import('@opencode/sdk');
  const {runCandidate,runConsole}=await import('./adapter.mjs');
  if(mode==='fixture'){
   const {trialFixture}=await import('./trial-fixture.mjs');
   result=await runCandidate(request,{OpenCode,respond:trialFixture(request),onPhase});
  }else result=await runConsole(request,{OpenCode,key,onPhase});
 }
 fs.writeSync(1,JSON.stringify(result)+'\n');code=0;
}catch{fs.writeSync(2,'OpenCode v2 host request failed; raw details omitted.\n');}
finally{if(home)try{fs.rmSync(home,{recursive:true,force:true});}catch{code=2;}}
process.exit(code);
