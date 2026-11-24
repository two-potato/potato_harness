import {test} from 'node:test';
import assert from 'node:assert/strict';
import {combineModelUsage} from '../src/bridge_accounting.mjs';
const sample=(input,output,cost,extras={})=>({tokens:{input,output,...extras},cost});
test('missing optional reasoning/cache does not become NaN',()=>{
 assert.deepEqual(combineModelUsage(sample(10,2,0),sample(30,5,0)),{input_tokens:40,output_tokens:7,cost_usd:0});
});
test('explicit reasoning and cache tokens are counted',()=>{
 assert.deepEqual(combineModelUsage(sample(10,2,0.01,{reasoning:3,cache:{read:4,write:5}}),sample(30,5,0.02)),{input_tokens:49,output_tokens:10,cost_usd:0.03});
});
test('missing or invalid cost remains unknown',()=>{
 assert.equal(combineModelUsage(sample(10,2,0),sample(30,5,undefined)).cost_usd,null);
 assert.equal(combineModelUsage(sample(10,2,0),sample(30,5,NaN)).cost_usd,null);
});
test('invalid required counters fail closed',()=>{
 for(const bad of [-1,1.5,null,undefined,true,Number.MAX_SAFE_INTEGER+1])assert.throws(()=>combineModelUsage(sample(bad,2,0),sample(1,1,0)),/token accounting/);
});
test('invalid optional reasoning fails closed',()=>{
 assert.throws(()=>combineModelUsage(sample(1,1,0,{reasoning:null}),sample(1,1,0)),/token accounting/);
});
