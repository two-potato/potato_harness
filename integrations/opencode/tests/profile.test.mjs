import {test} from 'node:test';import assert from 'node:assert/strict';
import {harnessConfig,omoProfile,ROLES} from '../src/profile.mjs';
test('coordinator and worker tools remain denied',()=>{const c=harnessConfig('opencode/gpt-6.1-sol');assert.equal(c.default_agent,'valera-ceo');assert.equal(Object.values(c.agent).filter(a=>!a.disable).length,9);for(const role of ROLES)assert.equal(c.agent[role].permission['*'],'deny');});
test('OMO defaults cannot install a second coordinator',()=>{const p=omoProfile();assert.equal(p.sisyphus_agent.disabled,true);assert.ok(p.disabled_agents.includes('sisyphus'));assert.ok(p.disabled_hooks.includes('todo-continuation-enforcer'));assert.equal(p.telemetry,false);});
test('actual pinned plugin imports',async()=>{const m=await import('oh-my-opencode');assert.equal(typeof m.omoPlugin,'function');});
test('OMO official environment opt-out is set before factory startup',()=>{assert.equal(process.env.DO_NOT_TRACK,'1');assert.equal(process.env.OMO_DISABLE_POSTHOG,'1');assert.equal(process.env.OMO_SEND_ANONYMOUS_TELEMETRY,'0');});
