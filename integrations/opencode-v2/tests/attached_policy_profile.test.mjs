import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {attachedModelRef,buildProfile,prepareProfile,inspectPolicy,effectiveAgentDeny,verifyAttachedSnapshot} from '../src/attached-policy-profile.mjs';
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
 assert.equal(fs.statSync(path.join(f.dir,'opencode.json')).mode&0o777,0o600);
 assert.ok(!fs.readFileSync(path.join(f.dir,'opencode.json'),'utf8').includes('apiKey'));
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
 fs.appendFileSync(path.join(f.dir,'opencode.json'),' ');
 assert.equal((await inspectPolicy(f.options)).reason,'LOCAL_PROFILE_MISMATCH');
 assert.equal(f.calls(),0);
});

test('project discovery stages opencode.json and scopes all snapshot queries to the private Location',async t=>{
 const f=fixture(t);if(!f)return;
 assert.deepEqual(JSON.parse(fs.readFileSync(path.join(f.dir,'opencode.json'),'utf8')),f.p.config);
 assert.equal(fs.existsSync(path.join(path.dirname(f.dir),'opencode.json')),false);
 const calls=[];
 const clientFactory=()=>({server:{info:async()=>({version:'2.4.1'})},
  ...Object.fromEntries([['plugin','plugins'],['agent','agents'],['model','models']].map(([key,value])=>[
   key,{list:async arg=>{calls.push(key);assert.deepEqual(arg,{location:{directory:f.dir}});return f.snapshot[value];}}
  ]))});
 const report=await inspectPolicy({...f.options,clientFactory});
 assert.equal(report.status,'PASS');
 assert.deepEqual(calls.sort(),['agent','model','plugin']);
 assert.equal(report.runtime_admission,false);
});

const denyAll={action:'*',resource:'*',effect:'deny'};
const inherited=[denyAll,{action:'edit',resource:'*',effect:'allow'},
 {action:'webfetch',resource:'*',effect:'allow'},{action:'shell',resource:'*',effect:'ask'},
 {action:'shell',resource:'git status*',effect:'allow'},
 {action:'shell',resource:'docker *',effect:'ask'}];
const browserDeny={action:'browser',resource:'*',effect:'deny'};
test('attached snapshot proves final universal deny over inherited allow and ask',async t=>{
 const f=fixture(t);if(!f)return;
 for(const a of f.snapshot.agents.data)a.permissions=[...inherited,denyAll,denyAll,browserDeny];
 const before=JSON.stringify(f.snapshot);
 assert.equal(verifyAttachedSnapshot(f.snapshot,f.p),true);
 assert.equal(JSON.stringify(f.snapshot),before);
 const result=await inspectPolicy(f.options);
 assert.equal(result.status,'PASS');assert.equal(result.effective_deny_roles,9);
 assert.equal(result.runtime_admission,false);assert.equal(result.attempted_prompts,0);
});
test('effective denial rejects later allow or ask, missing universal deny and malformed rules',()=>{
 assert.equal(effectiveAgentDeny([denyAll]),true);
 assert.equal(effectiveAgentDeny([...inherited,denyAll,browserDeny]),true);
 for(const bad of [null,[],[browserDeny],inherited,[denyAll,{action:'edit',resource:'*',effect:'allow'}],
  [denyAll,{action:'shell',resource:'*',effect:'ask'},browserDeny],
  [{action:'*',resource:'*',effect:'unknown'},denyAll],
  [{...denyAll,extra:true}], [{...denyAll,resource:1}], [null,denyAll]])
  assert.equal(effectiveAgentDeny(bad),false);
});
test('attached snapshot still rejects extra roles, plugin, wrong system/model, price or tool capability',async t=>{
 const f=fixture(t);if(!f)return;
 const a=f.snapshot.agents.data[0];
 a.permissions=[...inherited,denyAll];
 const patches=[['system','wrong'],['steps',2],['mode','wrong'],['model',{providerID:'other',id:'wrong'}]];
 for(const [key,value] of patches){const prev=a[key];a[key]=value;
  assert.equal((await inspectPolicy(f.options)).status,'HOLD');a[key]=prev;}
 a.permissions.push({action:'shell',resource:'*',effect:'allow'});
 assert.equal((await inspectPolicy(f.options)).status,'HOLD');a.permissions.pop();
 f.snapshot.agents.data.push({...a,id:'extra'});
 assert.equal((await inspectPolicy(f.options)).status,'HOLD');f.snapshot.agents.data.pop();
 f.snapshot.models.data[0].capabilities.tools=true;
 assert.equal((await inspectPolicy(f.options)).status,'HOLD');
});
