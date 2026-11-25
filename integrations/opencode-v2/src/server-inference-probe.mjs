// Explicit opt-in only. Historical outcomes remain blocking; no automatic retry.
import os from 'node:os';
import {Database} from 'bun:sqlite';
import {probeArgs} from './server-inference.mjs';
import {openNativeLedger} from './native-ledger.mjs';
let ledger,report;
try{
 const args=process.argv.slice(2);
 if(args.length===1&&args[0]==='--ledger-status'){
  ledger=openNativeLedger(Database,os.homedir());
  console.log(JSON.stringify({status:'HOLD',...ledger.status()},null,2));
  process.exitCode=2;
 }else{
  probeArgs(args);
  ledger=openNativeLedger(Database,os.homedir());
  // Independent approval, egress and provider reconciliation are not available
  // in this increment. Keep the existing command fail-closed even on a fresh
  // host: local records alone cannot authorize an external trial.
  const snapshot=ledger.status();
  if(snapshot.historical.length)throw Error('HISTORICAL_OUTCOMES_UNRESOLVED');
  throw Error('LIVE_ADMISSION_NOT_IMPLEMENTED');
 }
}catch(e){
 const known=['HISTORICAL_OUTCOMES_UNRESOLVED','LIVE_ADMISSION_NOT_IMPLEMENTED'];
 report={status:'HOLD',layer:'native-cli-server-inference-probe',
  reason:known.includes(e?.message)?e.message:'LEDGER_OR_SETUP_HOLD',
  external_inference:false,attempted_prompts:0,runtime_admission:false};
 console.log(JSON.stringify(report));
 process.exitCode=2;
}finally{
 try{ledger?.close();}catch{process.exitCode=2;}
}
