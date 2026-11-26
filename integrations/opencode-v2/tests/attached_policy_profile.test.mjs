import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {attachedModelRef,buildProfile,prepareProfile,inspectPolicy} from '../src/attached-policy-profile.mjs';
import {ROLES} from '../src/profile.mjs';
import {POLICY_ID} from '../src/server-policy.mjs';
const model='openrouter/nvidia/nemotron-fixture:free';
function root(t){
 const base=fs.mkdtempSync(path.join(os.tmpdir(),'potato-profile-'));
 t.after(()=>fs.rmSync(base,{recursive:true,force:true}));
 return path.join(base,'profile');
}
test('explicit free identity only, no automatic router or paid variant',()=>{
 assert.deepEqual(attachedModelRef(model),{providerID:'openrouter',id:'nvidia/nemotron-fixture:free'});
 assert.deepEqual(attachedModelRef('opencode/beam-free'),{providerID:'opencode',id:'beam-free'});
 for(const v of ['openrouter/openrouter/free','openrouter/nvidia/nemotron','openrouter/nvidia/../x:free',
  'openrouter/nvidia/model:free#paid','other/vendor/model:free'])assert.throws(()=>attachedModelRef(v));
});
test('staged configuration reuses all nine prompts and denies every tool; no provider override',t=>{
 const dir=root(t),p=buildProfile(dir,model);
 assert.deepEqual(Object.keys(p.config.agents),ROLES);
 assert.equal(p.config.providers,undefined);
 assert.equal(p.config.default_agent,'valera-ceo');
 for(const role of ROLES){
  assert.equal(p.config.agents[role].model,model);
  assert.equal(p.config.agents[role].steps,1);
  assert.deepEqual(p.config.agents[role].permissions,[{action:'*',resource:'*',effect:'deny'}]);
 }
 assert.ok(p.config.plugins.includes(p.plugin));
 assert.ok(p.source.includes('"offline":true'));
});
test('generated plugin actually denies model dispatch for matching resolved role',async t=>{
 const p=buildProfile(root(t),model);
 const plugin=(await import('data:text/javascript;base64,'+Buffer.from(p.source).toString('base64'))).default;
 const hooks={},reg=(k,f)=>{hooks[k]=f;return {dispose:async()=>{}};};
 const close=await plugin.setup({agent:{transform:f=>reg('agent',f)},model:{transform:f=>reg('model',f)},
  tool:{transform:f=>reg('tool',f)},permission:{hook:reg},session:{hook:reg}});
 const event={kind:'primary',agent:'valera-ceo',sessionID:'s',model:p.ref};
 hooks['experimental.model.resolve'](event);
 assert.throws(()=>hooks['model.request'](event),/OFFLINE_MODEL_REQUEST_DENIED/);
 assert.throws(()=>hooks['http.request'](event),/HTTP_REQUEST_DENIED/);
 await close();
});
function fixture(t){
 const dir=root(t);
 if(process.getuid()===0){t.skip('unprivileged operator required');return null;}
 const result=prepareProfile(dir,model),p=buildProfile(dir,model);
 const snapshot={plugins:{data:[{id:POLICY_ID,source:{type:'local',path:p.plugin},state:{status:'active'}}]},
  agents:{data:ROLES.map(id=>({...p.config.agents[id],id,model:p.ref}))},
  models:{data:[{...p.ref,enabled:true,status:'active',cost:[{input:0,output:0,cache:{read:0,write:0}}],
   limit:{output:1024},capabilities:{tools:false},variants:[]}]}};
 let calls=0;
 const options={directory:dir,model,clientFactory:()=>{calls++;return {server:{info:async()=>({version:'2.4.1'})},
  plugin:{list:async()=>snapshot.plugins},agent:{list:async()=>snapshot.agents},model:{list:async()=>snapshot.models}};}};
 return {dir,p,result,snapshot,options,calls:()=>calls};
}
test('private preparation refuses overwrite and writes no credentials',t=>{
 const f=fixture(t);if(!f)return;
 assert.equal(f.result.status,'PREPARED');
 assert.throws(()=>prepareProfile(f.dir,model));
 assert.equal(fs.statSync(path.join(f.dir,'profile.json')).mode&0o777,0o600);
 assert.ok(!fs.readFileSync(path.join(f.dir,'profile.json'),'utf8').includes('apiKey'));
});
test('exact snapshot is advisory only; missing role, wrong price, extra plugin fail',async t=>{
 const f=fixture(t);if(!f)return;
 const r=await inspectPolicy(f.options);
 assert.equal(r.status,'PASS');assert.equal(r.roles_loaded,9);assert.equal(r.runtime_admission,false);
 const old=f.snapshot.agents.data.pop();
 assert.equal((await inspectPolicy(f.options)).status,'HOLD');
 f.snapshot.agents.data.push(old);
 f.snapshot.models.data[0].cost[0].output=1;
 assert.equal((await inspectPolicy(f.options)).status,'HOLD');
 f.snapshot.models.data[0].cost[0].output=0;
 f.snapshot.plugins.data.push({id:'other',state:{status:'active'},source:{type:'package'}});
 assert.equal((await inspectPolicy(f.options)).status,'HOLD');
});
test('modified local profile fails before server access',async t=>{
 const f=fixture(t);if(!f)return;
 fs.appendFileSync(path.join(f.dir,'profile.json'),' ');
 assert.equal((await inspectPolicy(f.options)).reason,'LOCAL_PROFILE_MISMATCH');
 assert.equal(f.calls(),0);
});
