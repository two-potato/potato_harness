process.env.DO_NOT_TRACK='1';process.env.OMO_DISABLE_TELEMETRY='1';process.env.OMO_DISABLE_POSTHOG='1';process.env.OMO_SEND_ANONYMOUS_TELEMETRY='0';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
export const ROOT=path.resolve(here,'../../..');
export const VERSIONS={opencode:'1.19.5',omo:'5.1.60',bun:'1.4.4'};
export const ROLES=['valera-ceo','architect','backend','frontend','search','ml-recommendations','qa','devops-sre','security'];
function enums(file){
 const text=fs.readFileSync(path.resolve(here,'../node_modules/oh-my-opencode/dist/config/schema',file),'utf8');
 return [...text.matchAll(/^\s+(?:"([^"]+)"|([a-z][a-z_-]*)):\s*"[^"]+";/gm)].map(m=>m[1]||m[2]);
}
export function omoProfile(){
 return {telemetry:false,auto_update:false,model_fallback:false,runtime_fallback:false,
 sisyphus_agent:{disabled:true,default_builder_enabled:false,planner_enabled:false,replace_plan:false},
 disabled_agents:enums('agent-names.d.ts'),disabled_hooks:enums('hooks.d.ts'),
 disabled_skills:enums('agent-names.d.ts').concat(['security-research','security-review']),
 disabled_mcps:['websearch','context7','grep_app'],
 claude_code:{mcp:false,commands:false,skills:false,agents:false,hooks:false,plugins:false},
 team_mode:{enabled:false},tmux:{enabled:false},
 background_task:{defaultConcurrency:0,maxLiveDescendantsPerRoot:0},
 experimental:{disable_omo_env:true,disable_live_parent_wake_routing:true},skills:{sources:[]}};
}
export function harnessConfig(model){
 if(typeof model!=='string'||!/^[-\w.]+\/[-\w.:]+$/.test(model))throw Error('Explicit provider/model required');
 const common=['AGENTS.md','rules/PRIORITY.md','rules/SECURITY.md','rules/REPORTING.md'].map(f=>fs.readFileSync(path.join(ROOT,f),'utf8')).join('\n');
 const skillFor=role=>({'valera-ceo':'harness-delegate',architect:'harness-contract-design',qa:'harness-verify',security:'harness-security-review','devops-sre':'harness-recover'}[role]||'harness-implement');
 const agent=Object.fromEntries(ROLES.map(role=>[role,{model,mode:role==='valera-ceo'?'primary':'subagent',
 description:`Potato Harness ${role}`,prompt:common+'\n'+fs.readFileSync(path.join(ROOT,'agents',role+'.md'),'utf8')+'\n'+fs.readFileSync(path.join(ROOT,'skills',skillFor(role),'SKILL.md'),'utf8')+'\nReturn only the requested structured proposal. Host tools and approvals are unavailable to this model session.',
 permission:{'*':'deny'},tools:{'*':false},steps:4}]));
 for(const name of ['build','plan','general','explore'])agent[name]={disable:true};
 return {$schema:'https://opencode.ai/config.json',model,default_agent:'valera-ceo',agent,permission:{'*':'deny'},mcp:{},command:{},autoupdate:false,share:'disabled',plugin:[path.join(here,'plugin.mjs')]};
}
export function prepareProject(directory,model){
 fs.mkdirSync(path.join(directory,'.omo'),{recursive:true});
 fs.writeFileSync(path.join(directory,'.omo/omo.jsonc'),JSON.stringify(omoProfile(),null,2));
 const config=harnessConfig(model);fs.writeFileSync(path.join(directory,'opencode.json'),JSON.stringify(config,null,2));
 return config;
}
