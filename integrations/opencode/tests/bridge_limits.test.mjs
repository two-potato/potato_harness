import {test} from 'node:test';
import assert from 'node:assert/strict';
import {withTimeout,bridgeBudget,FINALIZATION_RESERVE_MS} from '../src/bridge_limits.mjs';
test('hung session cleanup is bounded',async()=>{
 await assert.rejects(withTimeout(()=>new Promise(()=>{}),15),/timed out/);
});
test('successful bounded operation preserves result',async()=>{
 assert.equal(await withTimeout(async()=>42,100),42);
});
test('both agent calls share one deadline',async()=>{
 let elapsed=0;const b=bridgeBudget(10000,()=>elapsed);
 assert.equal(await b.stage(async()=> 'valera'),'valera');
 elapsed=9000;
 assert.throws(()=>b.stage(async()=> 'backend'),/deadline exhausted/);
});
test('reject invalid timeouts',()=>{
 for(const v of [null,0,Infinity,-1,2.5,121000])assert.throws(()=>bridgeBudget(v),/Invalid host bridge timeout/);
 assert.ok(FINALIZATION_RESERVE_MS>0);
});
