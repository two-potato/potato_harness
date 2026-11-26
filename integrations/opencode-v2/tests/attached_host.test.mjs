import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {openAttachedStageLedger,attachedStateRoot,ATTACHED_TRIAL_MODEL as model} from '../src/attached-stage-ledger.mjs';
import {runAttachedHost} from '../src/attached-host.mjs';
import {OBJECTIVE} from '../src/trial-fixture.mjs';
const request={model,role:'backend',prompt:'synthetic trial',coordination:{objective:OBJECTIVE,scope:['calculation.py']},
 output_token_allowance:2048,token_allowance:100,bridge_timeout_ms:10000};
function home(t){
 if(process.getuid()===0){t.skip('unprivileged host required');return null;}
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'potato-attached-host-'));
 t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return dir;
}
test('stable private ledger preserves the same slot across opens under permissive umask',t=>{
 const dir=home(t);if(!dir)return;
 const previous=process.umask(0);let l;
 try{l=openAttachedStageLedger(DatabaseSync,dir);}finally{process.umask(previous);}
 l.reserve(model,100,1024);l.beforePrompt('valera-ceo');l.close();
 const root=attachedStateRoot(dir),file=path.join(root,'inference-ledger.sqlite3');
 assert.equal(fs.statSync(file).mode&0o777,0o600);
 l=openAttachedStageLedger(DatabaseSync,dir);
 try{assert.equal(l.status().attempt.state,'DISPATCHING');assert.throws(()=>l.reserve(model,100,1024));}finally{l.close();}
});
test('ledger opener refuses symlink and group-readable file',t=>{
 const dir=home(t);if(!dir)return;
 const root=attachedStateRoot(dir),file=path.join(root,'inference-ledger.sqlite3');
 const target=path.join(dir,'outside');fs.writeFileSync(target,'untouched',{mode:0o600});
 fs.symlinkSync(target,file);assert.throws(()=>openAttachedStageLedger(DatabaseSync,dir));
 assert.equal(fs.readFileSync(target,'utf8'),'untouched');fs.unlinkSync(file);
 fs.writeFileSync(file,'');fs.chmodSync(file,0o640);
 assert.throws(()=>openAttachedStageLedger(DatabaseSync,dir));
});
test('host denial does not create an audited profile, reserve a slot or access the server',async t=>{
 const dir=home(t);if(!dir)return;
 let calls=0;
 const opts={operatorHome:dir,password:'fixture',Database:DatabaseSync,clientFactory:()=>{calls++;throw Error('unexpected');}};
 await assert.rejects(()=>runAttachedHost(request,opts),/ATTACHED_HOST_NOT_ADMITTED/);
 await assert.rejects(()=>runAttachedHost(request,{...opts,admit:async scope=>{
  assert.match(scope.request_sha256,/^[a-f0-9]{64}$/);assert.equal(scope.model,model);return false;
 }}),/ATTACHED_ADMISSION_REQUIRED/);
 assert.equal(calls,0);
 assert.ok(!fs.readdirSync(attachedStateRoot(dir)).some(x=>x.startsWith('run-')));
 const l=openAttachedStageLedger(DatabaseSync,dir);
 try{assert.equal(l.status().attempt,null);}finally{l.close();}
});
test('admitted host stages audited profile only after durable slot; failed connect retains it',async t=>{
 const dir=home(t);if(!dir)return;
 let location;
 await assert.rejects(()=>runAttachedHost(request,{
  operatorHome:dir,password:'fixture',Database:DatabaseSync,
  admit:async scope=>{location=scope.directory;assert.ok(!fs.existsSync(location));return true;},
  clientFactory:()=>{
   const l=openAttachedStageLedger(DatabaseSync,dir);
   try{assert.equal(l.status().attempt.state,'RESERVED');}finally{l.close();}
   const source=fs.readFileSync(path.join(location,'policy','server.mjs'),'utf8');
   assert.ok(source.includes('"offline":false'));
   assert.ok(source.includes('audit.log'));
   assert.equal(fs.statSync(path.join(location,'audit.log')).mode&0o777,0o600);
   assert.equal(fs.readFileSync(path.join(location,'audit.log'),'utf8'),'');
   throw Error('injected connect failure');
  }
 }),/ATTACHED_RUNTIME_OUTCOME_UNKNOWN/);
 const l=openAttachedStageLedger(DatabaseSync,dir);
 try{assert.equal(l.status().attempt.state,'UNKNOWN');assert.equal(l.status().stages.length,0);}finally{l.close();}
 assert.ok(fs.existsSync(location));
});
