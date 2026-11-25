// Native role prompt loader; no legacy configuration or plugin dependencies.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
export const ROOT=path.resolve(here,'../../..');
export const ROLES=['valera-ceo','architect','backend','frontend','search','ml-recommendations','qa','devops-sre','security'];
export function rolePrompts(){
 const common=['AGENTS.md','rules/PRIORITY.md','rules/SECURITY.md','rules/REPORTING.md'].map(f=>fs.readFileSync(path.join(ROOT,f),'utf8')).join('\n');
 const skillFor=role=>({'valera-ceo':'harness-delegate',architect:'harness-contract-design',qa:'harness-verify',security:'harness-security-review','devops-sre':'harness-recover'}[role]||'harness-implement');
 return Object.fromEntries(ROLES.map(role=>[role,common+'\n'+fs.readFileSync(path.join(ROOT,'agents',role+'.md'),'utf8')+'\n'+fs.readFileSync(path.join(ROOT,'skills',skillFor(role),'SKILL.md'),'utf8')+'\nReturn only the requested structured proposal. Host tools and approvals are unavailable to this model session.']));
}
