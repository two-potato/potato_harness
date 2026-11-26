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
// Discovery only: the two observed providers, no automatic router aliases.
function catalogCandidate(m){
 if(!m||typeof m.id!=='string'||m.id.length>200||
    !['opencode','openrouter'].includes(m.providerID))return null;
 const provider=m.providerID,prefix=provider+'/';
 const qualified=m.id.startsWith(prefix),id=qualified?m.id.slice(prefix.length):m.id;
 const shape=provider==='opencode'?/^[a-z0-9][a-z0-9._-]{0,126}-free$/:
  /^[a-z0-9][a-z0-9._-]{0,126}\/[a-z0-9][a-z0-9._-]{0,126}:free$/;
 if(!shape.test(id)||id.split('/').some(p=>p.includes('..')))return null;
 return {model:prefix+id,enabled:m.enabled===true,
  zero_catalog_price:isFreeModel(m,{providerID:provider,id:m.id}),
  ...(qualified?{identity_shape:'qualified'}:{})};
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
  report.catalog_counts={total:models.data.length,opencode:0,openrouter:0,other:0};
  for(const m of models.data){
   const key=['opencode','openrouter'].includes(m?.providerID)?m.providerID:'other';
   report.catalog_counts[key]++;
  }
  const matches=models.data.map(catalogCandidate).filter(Boolean);
  if(matches.length>128||new Set(matches.map(m=>m.model)).size!==matches.length)return {...report,reason:'CATALOG_AMBIGUOUS'};
  report.candidates=matches;
  if(!report.candidates.some(m=>m.enabled&&m.zero_catalog_price&&!m.identity_shape))return {...report,reason:'FREE_MODEL_NOT_VERIFIED'};
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
