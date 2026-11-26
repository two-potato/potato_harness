// Trusted host composition for the first bounded trial. No CLI or environment
// flag can supply admission. The embedding authority must verify current
// external limits/egress, exact approval and independent review; absent => HOLD.
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {buildProfile} from './attached-policy-profile.mjs';
import {pluginSource} from './server-policy.mjs';
import {readAudit} from './server-audit.mjs';
import {attachedStateRoot,assertPrivateDirectory,assertPrivateFile,
 openAttachedStageLedger,ATTACHED_TRIAL_MODEL} from './attached-stage-ledger.mjs';
import {runBoundAttachedRuntime} from './attached-runtime-binding.mjs';
import {OBJECTIVE} from './trial-fixture.mjs';
import {withTimeout} from './bridge_limits.mjs';

function readPrivate(file){
 const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);
 try{
  const s=fs.fstatSync(fd);
  if(!s.isFile()||s.nlink!==1||s.uid!==process.getuid()||(s.mode&0o077)!==0||s.size>2*1024*1024)
   throw Error('ATTACHED_UNSAFE_FILE');
  return fs.readFileSync(fd,'utf8');
 }finally{fs.closeSync(fd);}
}

// This is a host-internal helper. It may be invoked only after the bound
// runtime has obtained admission and reserved its durable slot. No overwrite.
function auditedProfile(directory){
 const p=buildProfile(directory,ATTACHED_TRIAL_MODEL);
 const auditFile=path.join(directory,'audit.log');
 const configText=JSON.stringify(p.config,null,2)+'\n';
 const source=pluginSource(p.config,p.ref,1024,'backend',auditFile,false);
 const verifyProfile=()=>{
  assertPrivateDirectory(directory);assertPrivateDirectory(p.plugin);
  if(readPrivate(path.join(directory,'opencode.json'))!==configText||
     readPrivate(path.join(p.plugin,'server.mjs'))!==source)
   throw Error('ATTACHED_PROFILE_CHANGED');
  assertPrivateFile(auditFile);
 };
 return {profile:{...p,source},verifyProfile,readAudit:()=>{assertPrivateFile(auditFile);return readAudit(auditFile);},
  prepare:()=>{
   assertPrivateDirectory(path.dirname(directory));
   fs.mkdirSync(directory,{mode:0o700});
   fs.mkdirSync(p.plugin,{mode:0o700});
   fs.writeFileSync(auditFile,'',{mode:0o600,flag:'wx'});
   fs.writeFileSync(path.join(directory,'opencode.json'),configText,{mode:0o600,flag:'wx'});
   fs.writeFileSync(path.join(p.plugin,'server.mjs'),source,{mode:0o600,flag:'wx'});
   verifyProfile();
  }};
}

export async function runAttachedHost(request,{operatorHome,password,Database,clientFactory,
 admit,onPhase,send}={}){
 // Restrict the first trial before touching the filesystem. No production source
 // or arbitrary project scope is accepted by this profile.
 if(typeof admit!=='function'||typeof Database!=='function'||typeof clientFactory!=='function'||
    typeof password!=='string'||!password||request?.model!==ATTACHED_TRIAL_MODEL||
    request.role!=='backend'||request.coordination?.objective!==OBJECTIVE||
    JSON.stringify(request.coordination?.scope)!=='["calculation.py"]'||
    typeof request.prompt!=='string'||Buffer.byteLength(request.prompt)>262144||
    request.output_token_allowance!==2048||!Number.isSafeInteger(request.token_allowance)||
    request.token_allowance<2||request.token_allowance>100000||
    !Number.isSafeInteger(request.bridge_timeout_ms)||request.bridge_timeout_ms<=4000||
    request.bridge_timeout_ms>120000)
  throw Error('ATTACHED_HOST_NOT_ADMITTED');
 // This only creates a private directory. No profile or prompt before admission.
 const root=attachedStateRoot(operatorHome),directory=path.join(root,'run-'+randomUUID());
 const profile=auditedProfile(directory);
 const ledger=openAttachedStageLedger(Database,operatorHome);
 try{
  return await runBoundAttachedRuntime(request,{
   ledger,onPhase,admit:scope=>withTimeout(()=>admit(scope),5000),
   transport:{...profile,directory,model:ATTACHED_TRIAL_MODEL,password,clientFactory,send}
  });
 }finally{ledger.close();}
}
