import test from 'node:test';
import assert from 'node:assert/strict';
import {connectAttachedTransport} from '../src/attached-runtime-transport.mjs';
import {buildProfile} from '../src/attached-policy-profile.mjs';
import {ROLES} from '../src/profile.mjs';
import {POLICY_ID} from '../src/server-policy.mjs';
const model='openrouter/nvidia/nemotron-fixture:free',directory='/private/fixture';
function fixture(){
 const profile=buildProfile(directory,model),calls=[],audit=['ready'];
 const snapshots={plugins:{data:[{id:POLICY_ID,source:{type:'local',path:profile.plugin},state:{status:'active'}}]},
  agents:{data:ROLES.map(id=>({...profile.config.agents[id],id,model:profile.ref}))},
  models:{data:[{...profile.ref,enabled:true,cost:[{input:0,output:0,cache:{read:0,write:0}}],
   limit:{output:1024},capabilities:{tools:false},variants:[]}]}};
 let next=0;
 const raw={server:{info:async()=>({version:'2.4.1'})},
  ...Object.fromEntries([['plugin','plugins'],['agent','agents'],['model','models']].map(([k,v])=>[k,{list:async input=>{
   assert.deepEqual(input,{location:{directory}});return snapshots[v];}}])),
  session:{create:async x=>{calls.push(['create',x]);return {id:'s'+(++next)};},
   prompt:async x=>{calls.push(['prompt',x]);},interrupt:async x=>{calls.push(['interrupt',x]);}},
  experimental:{session:{wait:async x=>{calls.push(['wait',x]);}}},
  message:{list:async x=>{calls.push(['list',x]);return {data:[]};}}};
 const options={directory,model,password:'local-fixture',profile,readAudit:()=>[...audit],verifyProfile:async()=>{},
  clientFactory:({baseUrl})=>{assert.equal(baseUrl,'http://127.0.0.1:4096');return raw;}};
 const create=agent=>({location:{directory},agent,model:profile.ref,permissions:[{action:'*',resource:'*',effect:'deny'}]});
 return {options,raw,snapshots,calls,audit,create};
}
test('attached transport routes owned sessions only and never controls the shared server',async()=>{
 const f=fixture(),t=await connectAttachedTransport(f.options);
 const {id}=await t.client.session.create(f.create('valera-ceo'));
 await assert.rejects(()=>t.client.session.prompt({sessionID:'foreign',text:'x'}));
 await t.client.session.prompt({sessionID:id,text:'inert plan'});
 await assert.rejects(()=>t.client.session.prompt({sessionID:id,text:'retry'}));
 await t.client.experimental.session.wait({sessionID:id});
 await t.client.message.list({sessionID:id,order:'asc',limit:100});
 const b=await t.client.session.create(f.create('backend'));
 await t.client.session.prompt({sessionID:b.id,text:'inert proposal'});
 await t.close();
 assert.deepEqual(f.calls.map(x=>x[0]),['create','prompt','wait','list','create','prompt','interrupt','wait']);
 assert.deepEqual(f.calls.at(-2)[1],{sessionID:b.id,resume:false});
 await assert.rejects(()=>t.client.session.create(f.create('backend')));
});
test('attached transport rejects foreign location, bad order and changed policy',async()=>{
 const f=fixture(),t=await connectAttachedTransport(f.options);
 await assert.rejects(()=>t.client.session.create(f.create('backend')));
 await assert.rejects(()=>t.client.session.create({...f.create('valera-ceo'),location:{directory:'/foreign'}}));
 f.snapshots.models.data[0].capabilities.tools=true;
 await assert.rejects(()=>t.client.session.create(f.create('valera-ceo')),/ATTACHED_POLICY_MISMATCH/);
 assert.deepEqual(f.calls,[]);await t.close();
});
test('uncertain create is preserved as cleanup HOLD; no unowned interrupt',async()=>{
 const f=fixture(),t=await connectAttachedTransport(f.options);
 f.raw.session.create=async()=>{throw Error('transport lost');};
 await assert.rejects(()=>t.client.session.create(f.create('valera-ceo')));
 await assert.rejects(()=>t.close(),/ATTACHED_CLEANUP_UNCERTAIN/);
 assert.deepEqual(f.calls,[]);
});
test('no connection without explicit host bindings or ready audit',async()=>{
 const f=fixture();
 for(const patch of [{password:''},{verifyProfile:undefined},{readAudit:undefined},{model:'openrouter/openrouter/free'}])
  await assert.rejects(()=>connectAttachedTransport({...f.options,...patch}));
 f.audit.push('model:valera-ceo');
 await assert.rejects(()=>connectAttachedTransport(f.options));assert.deepEqual(f.calls,[]);
});
