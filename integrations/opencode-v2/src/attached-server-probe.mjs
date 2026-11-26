// Advisory discovery only. No session, prompt, policy mutation or live admission.
import {withTimeout} from './bridge_limits.mjs';
import {isFreeModel} from './server-policy.mjs';

export const ATTACHED_ENDPOINT='http://127.0.0.1:4096';
export function attachedFetch({password,signal,send=globalThis.fetch}={}){
 return async(input,init)=>{
  const req=new Request(input,init),url=new URL(req.url);
  if(url.origin!==ATTACHED_ENDPOINT||url.username||url.password||signal?.aborted)throw Error('LOCAL_SERVER_ONLY');
  const headers=new Headers(req.headers);
  headers.delete('Authorization');
  if(password)headers.set('Authorization','Basic '+Buffer.from('opencode:'+password).toString('base64'));
  return send(new Request(req,{headers,redirect:'error',signal:signal?AbortSignal.any([req.signal,signal]):req.signal}));
 };
}
export async function inspectAttachedServer({clientFactory,directory,password,send}){
 const report={status:'HOLD',layer:'attached-server-catalog',endpoint:ATTACHED_ENDPOINT,
  version:null,candidates:[],external_inference:false,attempted_prompts:0,
  policy_verified:false,billing_verified:false,runtime_admission:false};
 const controller=new AbortController();
 try{
  const client=clientFactory({baseUrl:ATTACHED_ENDPOINT,fetch:attachedFetch({password,signal:controller.signal,send})});
  const health=await withTimeout(()=>client.server.info(),5000);
  if(health?.version!=='2.4.1')return {...report,reason:'SERVER_VERSION_MISMATCH'};
  report.version='2.4.1';
  const models=await withTimeout(()=>client.model.list({location:{directory}}),15000);
  if(!Array.isArray(models?.data)||models.data.length>20000)return {...report,reason:'CATALOG_UNAVAILABLE'};
  const matches=models.data.filter(m=>m?.providerID==='openrouter'&&typeof m.id==='string'&&
   /^[a-z0-9][a-z0-9._/-]{0,180}:free$/i.test(m.id)&&/nemotron/i.test(m.id));
  if(matches.length>32||new Set(matches.map(m=>m.id)).size!==matches.length)return {...report,reason:'CATALOG_AMBIGUOUS'};
  report.candidates=matches.map(m=>({model:'openrouter/'+m.id,enabled:m.enabled===true,
   zero_catalog_price:isFreeModel(m,{providerID:'openrouter',id:m.id})}));
  if(!report.candidates.some(m=>m.enabled&&m.zero_catalog_price))return {...report,reason:'NEMOTRON_FREE_NOT_VERIFIED'};
  return {...report,status:'PASS',reason:'CATALOG_ONLY'};
 }catch{
  return {...report,reason:'SERVER_OR_CATALOG_UNAVAILABLE'};
 }finally{controller.abort();}
}
if(import.meta.main){
 let report;
 try{
  if(process.argv.length!==2)throw Error('NO_ARGUMENTS');
  const {OpenCode}=await import('@opencode/client');
  report=await inspectAttachedServer({clientFactory:OpenCode.make,directory:process.cwd(),
   password:process.env.POTATO_OPENCODE_PASSWORD});
 }catch{
  report={status:'HOLD',layer:'attached-server-catalog',reason:'SETUP_HOLD',
   external_inference:false,attempted_prompts:0,runtime_admission:false};
 }
 console.log(JSON.stringify(report,null,2));
 process.exitCode=report.status==='PASS'?0:2;
}
