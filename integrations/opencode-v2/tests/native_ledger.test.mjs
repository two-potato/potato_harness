import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {createNativeLedger,runJournaledProbe} from '../src/native-ledger.mjs';
const model='opencode/test-free';
const usage={input_tokens:10,output_tokens:5,cost_usd:0};
function fixture(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'potato-ledger-'));
 t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const file=path.join(dir,'ledger');
 const db=new DatabaseSync(file),ledger=createNativeLedger(db);
 // Only an isolated TEST database may remove seeded holds to exercise the
 // future journal mechanics. The production CLI has no reconciliation bypass.
 return {file,db,ledger,ready:()=>db.exec('DELETE FROM native_history')};
}
test('historical cohorts persist, never invent request counts or prices',async t=>{
 const {file,ledger}=fixture(t);
 let called=false;
 await assert.rejects(runJournaledProbe(ledger,{model},async()=>{called=true;}),/HISTORICAL_OUTCOMES_UNRESOLVED/);
 assert.equal(called,false);assert.equal(ledger.status().historical.length,3);ledger.close();
 const reopened=createNativeLedger(new DatabaseSync(file));
 assert.equal(reopened.status().historical.length,3);
 assert.equal(reopened.status().attempts.length,0);reopened.close();
});
test('durable reservation excludes duplicate or alternate model attempts',t=>{
 const {file,ledger,ready}=fixture(t);ready();
 const id=ledger.reserve(model);
 const second=createNativeLedger(new DatabaseSync(file));
 assert.equal(second.status().attempts[0].outcome,'UNKNOWN');
 assert.throws(()=>second.reserve('opencode/other-free'));
 assert.throws(()=>ledger.beforePrompt(id,'backend'));
 ledger.beforePrompt(id,'valera-ceo');
 assert.throws(()=>ledger.beforePrompt(id,'valera-ceo'));
 assert.throws(()=>ledger.beforePrompt(id,'backend'));
 assert.equal(second.status().attempts[0].stages[0].cost_usd,null);
 second.close();ledger.close();
});
test('interrupted attempt remains unknown after reopen; no second stage or replay',t=>{
 const {file,ledger,ready}=fixture(t);ready();
 const id=ledger.reserve(model);
 ledger.beforePrompt(id,'valera-ceo');ledger.close();
 const reopened=createNativeLedger(new DatabaseSync(file));
 assert.equal(reopened.status().attempts[0].outcome,'UNKNOWN');
 assert.equal(reopened.status().attempts[0].stages[0].state,'DISPATCHING');
 assert.throws(()=>reopened.reserve(model));reopened.close();
});
test('validated stages persist exact reported usage and final checks',async t=>{
 const {ledger,ready}=fixture(t);ready();
 const report=await runJournaledProbe(ledger,{model},async options=>{
  for(const role of ['valera-ceo','backend']){
   options.beforePrompt(role);
   options.onValidatedStage(role,usage);
  }
  return {status:'PASS',external_inference:true,attempted_prompts:2,
   admitted_model_hooks:2,admitted_http_hooks:2,diagnostics:{cleanup_failed:false},
   usage:{input_tokens:20,output_tokens:10,cost_usd:0}};
 });
 assert.equal(report.ledger_state,'VALIDATED');
 assert.equal(ledger.status().billing_verified,false);
 assert.deepEqual(ledger.status().attempts[0].stages.map(s=>s.input_tokens),[10,10]);
 assert.throws(()=>ledger.reserve(model));ledger.close();
});
test('late failure preserves earlier reported usage, unknown cost for later stage',async t=>{
 const {ledger,ready}=fixture(t);ready();
 await assert.rejects(runJournaledProbe(ledger,{model},async options=>{
  options.beforePrompt('valera-ceo');options.onValidatedStage('valera-ceo',usage);
  options.beforePrompt('backend');throw Error('PRIVATE_PROVIDER_TEXT');
 }),/NATIVE_PROBE_OUTCOME_UNKNOWN/);
 const a=ledger.status().attempts[0];assert.equal(a.state,'UNKNOWN');
 assert.equal(a.stages[0].cost_usd,0);assert.equal(a.stages[1].cost_usd,null);
 assert.ok(!JSON.stringify(a).includes('PRIVATE_PROVIDER_TEXT'));ledger.close();
});
test('false success, excessive usage and missing cleanup cannot validate',t=>{
 const {ledger,ready}=fixture(t);ready();
 const id=ledger.reserve(model);ledger.beforePrompt(id,'valera-ceo');
 assert.throws(()=>ledger.validatedStage(id,'valera-ceo',{...usage,output_tokens:1025}));
 assert.equal(ledger.finish(id,{status:'PASS',external_inference:true}),'UNKNOWN');
 assert.throws(()=>ledger.finish(id,null));ledger.close();
});
test('preflight hold without dispatch still cannot replay the same slot',t=>{
 const {ledger,ready}=fixture(t);ready();
 const id=ledger.reserve(model);
 assert.equal(ledger.finish(id,{status:'HOLD',attempted_prompts:0,external_inference:false,
  diagnostics:{cleanup_failed:false}}),'NO_DISPATCH');
 assert.throws(()=>ledger.reserve(model));ledger.close();
});
