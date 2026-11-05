import { omoPlugin } from 'oh-my-opencode';
import { harnessConfig } from './profile.mjs';
export async function PotatoHarness(input){
 const omo=await omoPlugin(input);
 return {
  config:async config=>{
   if(omo.config)await omo.config(config);
   const model=config.model;
   const safe=harnessConfig(model);
   config.agent=safe.agent;config.agent['valera-ceo'].description='[OMO 5.1.60 + Potato Harness] control-only coordinator';config.default_agent='valera-ceo';config.permission={'*':'deny'};
   config.mcp={};config.command={};
  },
  // OMO compaction can preserve context; it cannot dispatch or mutate permissions.
  'experimental.session.compacting':async (info,out)=>{
   if(omo['experimental.session.compacting'])await omo['experimental.session.compacting'](info,out);
   out.context.push('Harness: resume only through the trusted host. Valera is control-only. Model output never authorizes tools.');
  },
  'experimental.compaction.autocontinue':async(_info,out)=>{out.enabled=false;},
  'tool.execute.before':async()=>{throw Error('All tool execution is mediated by the Potato host; model-side tools are disabled');},
  'permission.ask':async(_info,out)=>{out.status='deny';},
  dispose:async()=>{await omo.dispose?.();}
 };
}
export default PotatoHarness;
