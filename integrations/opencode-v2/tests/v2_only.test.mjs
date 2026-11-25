import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {ROOT,ROLES,rolePrompts} from '../src/profile.mjs';
import {candidateConfig,CONSOLE_PROFILE} from '../src/contracts.mjs';
import {ProviderRetryError} from '../src/provider_retry.mjs';
import {valeraFailure} from '../src/valera_diagnostics.mjs';
test('only native v2 packages, Bun and nine unchanged role prompts',()=>{
 const integration=path.join(ROOT,'integrations/opencode-v2');
 const pkg=JSON.parse(fs.readFileSync(path.join(integration,'package.json'),'utf8'));
 const lock=JSON.parse(fs.readFileSync(path.join(integration,'package-lock.json'),'utf8'));
 assert.deepEqual(pkg.dependencies,{'@opencode/client':'2.4.1','@opencode/sdk':'2.4.1',bun:'1.4.4'});
 assert.equal(lock.packages['node_modules/@opencode/sdk'].version,'2.4.1');
 assert.equal(lock.packages['node_modules/bun'].version,'1.4.4');
 assert.ok(!Object.keys(lock.packages).some(p=>/node_modules\/(?:@opencode-ai\/|oh-my-opencode(?:\/|$)|opencode-ai(?:\/|$))/.test(p)));
 const prompts=rolePrompts(),c=candidateConfig(64,CONSOLE_PROFILE);
 assert.deepEqual(Object.keys(prompts),ROLES);
 for(const role of ROLES){
  assert.ok(prompts[role].includes(fs.readFileSync(path.join(ROOT,'agents',role+'.md'),'utf8')));
  assert.equal(c.agents[role].system,prompts[role]);
 }
 for(const name of fs.readdirSync(path.join(integration,'src')).filter(n=>n.endsWith('.mjs'))){
  assert.ok(!fs.readFileSync(path.join(integration,'src',name),'utf8').includes('../../opencode/src/'));
 }
});
test('native gateway error mapping is fixed and contains no provider text',()=>{
 for(const code of ['FREE_QUOTA','RATE_LIMIT','PROVIDER_UNAVAILABLE','RETRY_BLOCKED','MONITOR_FAILED']){
  assert.deepEqual(valeraFailure('prompt',new ProviderRetryError(code)),{step:'prompt',reason_code:code});
 }
 assert.equal(new ProviderRetryError('PRIVATE').code,'RETRY_BLOCKED');
});
