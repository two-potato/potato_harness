import {FIXTURE_URL,MODEL_REF,deny} from './contracts.mjs';
import {ROLES} from '../../opencode/src/profile.mjs';

// Never forward to the network. One synthetic HTTP response per authorized stage.
export function fixtureTransport(respond,maxOutput){
 let phase=null,calls=0,violation=false;
 return {
  begin(next){if(phase!==null||!['valera','specialist'].includes(next))throw Error('INVALID_FIXTURE_STAGE');phase=next;calls=0;},
  end(){const n=calls;phase=null;if(violation||n!==1)throw Error('FIXTURE_REQUEST_BOUNDARY');},
  get violated(){return violation;},
  async fetch(input,init){
   const req=new Request(input,init);
   if(req.url!==FIXTURE_URL||req.method!=='POST'||!phase||calls!==0){violation=true;throw Error('FIXTURE_REQUEST_BOUNDARY');}
   calls++;
   const body=await req.json();
   const cap=body.max_tokens??body.max_completion_tokens;
   if(!Number.isSafeInteger(cap)||cap<1||cap>maxOutput||body.model!==MODEL_REF.id||!Array.isArray(body.messages)||(body.tools!==undefined&&(!Array.isArray(body.tools)||body.tools.length!==0))){
    violation=true;throw Error('FIXTURE_REQUEST_CONTRACT');
   }
   return respond(phase,body);
  }
 };
}
export function restrictivePlugin(observed,maxOutput){
 return {id:'potato-harness-v2-candidate',async setup(ctx){
  const registrations=[];
  registrations.push(await ctx.agent.transform(editor=>{
   for(const agent of editor.list())if(!ROLES.includes(agent.id))editor.remove(agent.id);
   editor.default('valera-ceo');
   for(const role of ROLES)editor.update(role,a=>{a.permissions=deny();a.steps=1;});
  }));
  registrations.push(await ctx.tool.transform(editor=>{for(const tool of editor.list())editor.remove(tool.id);}));
  registrations.push(await ctx.permission.hook('evaluate',event=>{event.effect='deny';}));
  registrations.push(await ctx.session.hook('context',event=>{
   event.tools={};event.options.maxOutputTokens=maxOutput;
  }));
  registrations.push(await ctx.session.hook('title',event=>{event.result='Potato bounded fixture';}));
  registrations.push(await ctx.session.hook('retry',event=>{
   event.decision={retry:false};observed.retries++;
  }));
  observed.ready=true;
  return async()=>{for(const registration of registrations.reverse())await registration.dispose();};
 }};
}
