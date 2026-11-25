// Local single-host journal for manual native probes, not a runtime admission gate.
// Host-owned database and trusted callbacks only. Never store prompts, keys or raw errors.
import fs from 'node:fs';
import path from 'node:path';
import {modelRef} from './server-policy.mjs';

const slot='r5-first-native-probe';
const roles=['valera-ceo','backend'];
const historical=[
 ['legacy-omo-deadline','LEGACY_OMO','DEADLINE'],
 ['native-beam-reports','NATIVE_FREE','RATE_LIMIT'],
 ['native-deepseek-reports','NATIVE_FREE','RATE_LIMIT']
];
const now=()=>new Date().toISOString();

function privateDirectory(dir){
 fs.mkdirSync(dir,{recursive:true,mode:0o700});
 const s=fs.lstatSync(dir);
 if(!s.isDirectory()||s.uid!==process.getuid()||(s.mode&0o077)!==0||
    fs.realpathSync(dir)!==dir)throw Error('UNSAFE_LEDGER_DIRECTORY');
}
function checkFile(file){
 if(!fs.existsSync(file)&&!fs.lstatSync(file,{throwIfNoEntry:false}))return;
 const s=fs.lstatSync(file);
 if(!s.isFile()||s.nlink!==1||s.uid!==process.getuid()||(s.mode&0o077)!==0)throw Error('UNSAFE_LEDGER_FILE');
}

export function openNativeLedger(Database,home){
 if(typeof home!=='string'||!path.isAbsolute(home)||fs.realpathSync(home)!==home||
    !process.getuid||process.getuid()===0)throw Error('UNSAFE_LEDGER_HOME');
 const root=path.join(home,'.local/state/potato-harness/opencode-free');
 privateDirectory(root);
 const file=path.join(root,'inference-ledger.sqlite3');
 // Pre-create private file, reject symlinks and aliases; same-UID host is trusted.
 for(const suffix of ['','-journal','-wal','-shm'])checkFile(file+suffix);
 if(!fs.existsSync(file)){
  try{fs.closeSync(fs.openSync(file,'wx',0o600));}
  catch(e){if(e.code!=='EEXIST')throw e;}
 }
 checkFile(file);
 const db=new Database(file);
 try{return createNativeLedger(db);}
 catch(e){db.close();throw e;}
}

// Database constructor is an explicit host test seam. The real CLI always uses
// the fixed private path above. No API clears historical holds or reopens a slot.
export function createNativeLedger(db){
 const run=(sql,...args)=>db.prepare(sql).run(...args);
 const get=(sql,...args)=>db.prepare(sql).get(...args);
 const all=(sql,...args)=>db.prepare(sql).all(...args);
 function tx(fn){
  db.exec('BEGIN IMMEDIATE');
  try{const result=fn();db.exec('COMMIT');return result;}
  catch(e){db.exec('ROLLBACK');throw e;}
 }
 db.exec('PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON; PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL;');
 tx(()=>{
  db.exec("CREATE TABLE IF NOT EXISTS native_ledger_meta(version INTEGER PRIMARY KEY CHECK(version=1));"+
    "CREATE TABLE IF NOT EXISTS native_history(id TEXT PRIMARY KEY,profile TEXT NOT NULL,reason TEXT NOT NULL,state TEXT NOT NULL CHECK(state='UNKNOWN'));"+
    "CREATE TABLE IF NOT EXISTS native_attempts(id TEXT PRIMARY KEY,model TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('RESERVED','DISPATCHING','NO_DISPATCH','UNKNOWN','VALIDATED')),created_at TEXT NOT NULL,updated_at TEXT NOT NULL,reason TEXT NOT NULL);"+
    "CREATE TABLE IF NOT EXISTS native_stages(attempt_id TEXT NOT NULL REFERENCES native_attempts(id),role TEXT NOT NULL CHECK(role IN ('valera-ceo','backend')),state TEXT NOT NULL CHECK(state IN ('DISPATCHING','VALIDATED')),input_tokens INTEGER,output_tokens INTEGER,cost_usd REAL,PRIMARY KEY(attempt_id,role));");
  run('INSERT OR IGNORE INTO native_ledger_meta VALUES(1)');
  if(get('SELECT count(*) AS n FROM native_ledger_meta').n!==1)throw Error('LEDGER_VERSION');
  for(const [id,profile,reason] of historical)run("INSERT OR IGNORE INTO native_history VALUES(?,?,?,'UNKNOWN')",id,profile,reason);
 });
 function status(){
  // No destructive recovery. An interrupted reservation/dispatch remains a
  // blocking unknown outcome even if a process is still alive.
  return {historical:all('SELECT id,profile,reason,state FROM native_history ORDER BY id'),
   attempts:all('SELECT id,model,state,created_at,updated_at,reason FROM native_attempts ORDER BY id').map(a=>({...a,
    outcome:['RESERVED','DISPATCHING','UNKNOWN'].includes(a.state)?'UNKNOWN':a.state,
    stages:all('SELECT role,state,input_tokens,output_tokens,cost_usd FROM native_stages WHERE attempt_id=? ORDER BY CASE role WHEN ? THEN 0 ELSE 1 END',a.id,roles[0])})),
   billing_verified:false,runtime_admission:false};
 }
 function reserve(model){
  modelRef(model);
  return tx(()=>{
   if(get('SELECT count(*) AS n FROM native_history').n!==0)throw Error('HISTORICAL_OUTCOMES_UNRESOLVED');
   if(get('SELECT count(*) AS n FROM native_attempts').n!==0)throw Error('NATIVE_PROBE_ALREADY_RESERVED');
   const stamp=now();
   run("INSERT INTO native_attempts VALUES(?,?,'RESERVED',?,?,'NONE')",slot,model,stamp,stamp);
   return slot;
  });
 }
 function beforePrompt(id,role){
  tx(()=>{
   const a=get('SELECT state FROM native_attempts WHERE id=?',id);
   const rows=all('SELECT role,state FROM native_stages WHERE attempt_id=?',id);
   const first=role===roles[0]&&a?.state==='RESERVED'&&rows.length===0;
   const second=role===roles[1]&&a?.state==='DISPATCHING'&&rows.length===1&&rows[0].role===roles[0]&&rows[0].state==='VALIDATED';
   if(id!==slot||(!first&&!second))throw Error('LEDGER_DISPATCH_DENIED');
   run("INSERT INTO native_stages VALUES(?,?,'DISPATCHING',NULL,NULL,NULL)",id,role);
   run("UPDATE native_attempts SET state='DISPATCHING',updated_at=? WHERE id=?",now(),id);
  });
 }
 function validatedStage(id,role,usage){
  if(!usage||!Number.isSafeInteger(usage.input_tokens)||usage.input_tokens<1||
     !Number.isSafeInteger(usage.output_tokens)||usage.output_tokens<1||usage.output_tokens>1024||
     usage.cost_usd!==0)throw Error('LEDGER_USAGE_INVALID');
  tx(()=>{
   if(id!==slot||get('SELECT state FROM native_attempts WHERE id=?',id)?.state!=='DISPATCHING'||
      get('SELECT state FROM native_stages WHERE attempt_id=? AND role=?',id,role)?.state!=='DISPATCHING')throw Error('LEDGER_STAGE_DENIED');
   run("UPDATE native_stages SET state='VALIDATED',input_tokens=?,output_tokens=?,cost_usd=? WHERE attempt_id=? AND role=?",
    usage.input_tokens,usage.output_tokens,usage.cost_usd,id,role);
  });
 }
 function finish(id,report){
  return tx(()=>{
   const a=get('SELECT state FROM native_attempts WHERE id=?',id);
   if(id!==slot||!a||!['RESERVED','DISPATCHING'].includes(a.state))throw Error('LEDGER_FINISH_DENIED');
   const rows=all('SELECT * FROM native_stages WHERE attempt_id=?',id);
   const totals=rows.reduce((sum,r)=>[sum[0]+r.input_tokens,sum[1]+r.output_tokens], [0,0]);
   const valid=report?.status==='PASS'&&report.external_inference===true&&report.attempted_prompts===2&&
    report.diagnostics?.cleanup_failed===false&&report.admitted_http_hooks===2&&report.admitted_model_hooks===2&&
    rows.length===2&&rows.every(r=>r.state==='VALIDATED')&&Number.isSafeInteger(totals[0])&&
    report.usage?.input_tokens===totals[0]&&report.usage?.output_tokens===totals[1]&&report.usage?.cost_usd===0;
   const noDispatch=report?.status==='HOLD'&&report.attempted_prompts===0&&report.external_inference===false&&
    report.diagnostics?.cleanup_failed===false&&rows.length===0&&a.state==='RESERVED';
   const state=valid?'VALIDATED':noDispatch?'NO_DISPATCH':'UNKNOWN';
   const allowed=['RATE_LIMIT','QUOTA','FREE_LIMIT','AUTH','DEADLINE','PROVIDER_UNAVAILABLE','REJECTED'];
   const category=report?.diagnostics?.failure?.category;
   const reason=valid?'NONE':allowed.includes(category)?category:'UNVERIFIED_OUTCOME';
   run('UPDATE native_attempts SET state=?,reason=?,updated_at=? WHERE id=?',state,reason,now(),id);
   return state;
  });
 }
 return {status,reserve,beforePrompt,validatedStage,finish,close:()=>db.close()};
}

export async function runJournaledProbe(ledger,options,probe){
 const id=ledger.reserve(options.model);
 let report;
 try{
  report=await probe({...options,beforePrompt:role=>ledger.beforePrompt(id,role),
   onValidatedStage:(role,usage)=>ledger.validatedStage(id,role,usage)});
 }catch{
  ledger.finish(id,null);
  throw Error('NATIVE_PROBE_OUTCOME_UNKNOWN');
 }
 const state=ledger.finish(id,report);
 if(report.status==='PASS'&&state!=='VALIDATED')throw Error('NATIVE_PROBE_OUTCOME_UNKNOWN');
 return {...report,ledger_state:state};
}
