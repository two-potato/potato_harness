// Trusted host CLI, not an agent tool. Scrub environment before loading SDK.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
let home,code=2;
try{
 const mode=process.argv[2];
 if(!['fixture','console','native-free-fixture','native-free-offline','attached-free','attached-free-fixture','attached-review-check'].includes(mode)||process.argv.length!==3)throw Error('INVALID_ADAPTER_MODE');
 const key=mode==='console'?process.env.OPENCODE_API_KEY:undefined;
 if(mode==='console'&&!key)throw Error('MISSING_CONSOLE_KEY');
 const offline=mode==='native-free-offline';
 const attached=mode==='attached-free'||mode==='attached-review-check';
 const password=mode==='attached-free'?process.env.POTATO_OPENCODE_PASSWORD:undefined;
 if(mode==='attached-free'&&!password)throw Error('ATTACHED_PASSWORD_REQUIRED');
 let nativeBinary,operatorHome=attached?os.homedir():undefined,outerNamespace;
 if(offline){
  const {requireOfflineNetwork}=await import('./offline-network.mjs');
  requireOfflineNetwork();
  nativeBinary=Bun.which('opencode');operatorHome=os.homedir();outerNamespace=process.env.POTATO_OUTER_NETNS;
  if(!nativeBinary)throw Error('CLI_NOT_FOUND');
 }
 for(const name of Object.keys(process.env))delete process.env[name];
 home=fs.mkdtempSync(path.join(os.tmpdir(),'potato-v2-host-'));
 Object.assign(process.env,{PATH:'/usr/bin:/bin',HOME:home,XDG_CONFIG_HOME:path.join(home,'config'),XDG_DATA_HOME:path.join(home,'data'),XDG_CACHE_HOME:path.join(home,'cache'),DO_NOT_TRACK:'1'});
 if(offline)process.env.POTATO_OUTER_NETNS=outerNamespace;
 process.chdir(home);
 if(mode==='attached-review-check'){
  const {verifyAttachedReview}=await import('./attached-admission.mjs');
  verifyAttachedReview(operatorHome);
  const {Database}=await import('bun:sqlite');
  const {openAttachedStageLedger}=await import('./attached-stage-ledger.mjs');
  const ledger=openAttachedStageLedger(Database,operatorHome);
  try{if(ledger.status().attempt!==null)throw Error('ATTACHED_SLOT_ALREADY_USED');}finally{ledger.close();}
  fs.writeSync(1,'PASS: attached reviewed trial preflight\n');code=0;
 }else{
 const raw=await new Response(Bun.stdin.stream()).text();
 if(Buffer.byteLength(raw)>262144)throw Error('OVERSIZED_REQUEST');
 const request=JSON.parse(raw);
 const onPhase=event=>fs.writeSync(2,'POTATO_GATEWAY_PHASE '+JSON.stringify(event)+'\n');
 let result;
 if(mode==='attached-free'){
  // Verify the independently reviewed trust policy before consuming an
  // authorization, creating a live profile or importing the provider client.
  const {verifyAttachedReview,admitReviewedScope}=await import('./attached-admission.mjs');
  verifyAttachedReview(operatorHome);
  const {consumeAttachedHandoff}=await import('./attached-handoff.mjs');
  const boundRequest=consumeAttachedHandoff(request,'attached-free');
  const {OpenCode}=await import('@opencode/client');
  const {Database}=await import('bun:sqlite');
  const {runAttachedHost}=await import('./attached-host.mjs');
  result=await runAttachedHost(boundRequest,{operatorHome,password,Database,clientFactory:OpenCode.make,onPhase,
   admit:scope=>admitReviewedScope(scope,boundRequest,operatorHome)});
 }else if(mode==='attached-free-fixture'){
  const {runAttachedControlledFixture}=await import('./attached-controlled-fixture.mjs');
  result=await runAttachedControlledFixture(request,{onPhase,home});
 }else if(mode==='native-free-fixture'){
  const {runNativeRuntimeFixture}=await import('./server-inference.mjs');
  const {launchNativeFixture,awaitNativeFixture}=await import('./native-runtime-fixture.mjs');
  result=await runNativeRuntimeFixture(request,{launch:launchNativeFixture,awaitPolicy:awaitNativeFixture,onPhase});
 }else if(offline){
  const {OpenCode}=await import('@opencode/client');
  const {launchPrivateServer,awaitServerPolicy}=await import('./server-process.mjs');
  const {runNativeRuntimeOffline}=await import('./server-inference.mjs');
  await runNativeRuntimeOffline(request,{onPhase,awaitPolicy:awaitServerPolicy,
   launch:options=>launchPrivateServer({...options,offline:true,binary:nativeBinary,operatorHome,clientFactory:OpenCode.make})});
  throw Error('OFFLINE_WORKER_MUST_NOT_RETURN');
 }else{
  const {OpenCode}=await import('@opencode/sdk');
  const {runCandidate,runConsole}=await import('./adapter.mjs');
  if(mode==='fixture'){
   const {trialFixture}=await import('./trial-fixture.mjs');
   result=await runCandidate(request,{OpenCode,respond:trialFixture(request),onPhase});
  }else result=await runConsole(request,{OpenCode,key,onPhase});
 }
 fs.writeSync(1,JSON.stringify(result)+'\n');code=0;
 }
}catch{fs.writeSync(2,'OpenCode v2 host request failed; raw details omitted.\n');}
finally{if(home)try{fs.rmSync(home,{recursive:true,force:true});}catch{code=2;}}
process.exit(code);
