// Host-only, one fixed attached OpenRouter trial slot. No reconciliation,
// reset, retry, provider switching or authority to launch a live session.
// The previous native journal is untouched.
export const ATTACHED_TRIAL_MODEL='openrouter/nvidia/nemotron-3-ultra-550b-a55b:free';
const roles=['valera-ceo','backend'];
const slot='attached-first-runtime';
export function createAttachedStageLedger(db){
 const get=(sql,...p)=>db.prepare(sql).get(...p);
 const run=(sql,...p)=>db.prepare(sql).run(...p);
 const all=(sql,...p)=>db.prepare(sql).all(...p);
 function tx(fn){
  db.exec('BEGIN IMMEDIATE');
  try{const result=fn();db.exec('COMMIT');return result;}
  catch(e){db.exec('ROLLBACK');throw e;}
 }
 db.exec('PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON; PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL;');
 tx(()=>db.exec("CREATE TABLE IF NOT EXISTS attached_attempts(id TEXT PRIMARY KEY,model TEXT NOT NULL,token_limit INTEGER NOT NULL,output_limit INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN ('RESERVED','DISPATCHING','VALIDATED','UNKNOWN')));"+
 "CREATE TABLE IF NOT EXISTS attached_stages(attempt_id TEXT NOT NULL REFERENCES attached_attempts(id),role TEXT NOT NULL CHECK(role IN ('valera-ceo','backend')),state TEXT NOT NULL CHECK(state IN ('DISPATCHING','VALIDATED')),input_tokens INTEGER,output_tokens INTEGER,cost_usd REAL,PRIMARY KEY(attempt_id,role));"));
 const attempt=()=>get('SELECT * FROM attached_attempts WHERE id=?',slot);
 const stages=()=>all("SELECT role,state,input_tokens,output_tokens,cost_usd FROM attached_stages WHERE attempt_id=? ORDER BY CASE role WHEN 'valera-ceo' THEN 0 ELSE 1 END",slot);
 const positive=n=>Number.isSafeInteger(n)&&n>0;
 function reserve(model,tokenLimit,outputLimit){
  if(model!==ATTACHED_TRIAL_MODEL||!positive(tokenLimit)||tokenLimit>100000||
     !positive(outputLimit)||outputLimit>1024)throw Error('ATTACHED_STAGE_BOUNDS');
  tx(()=>{
   if(get('SELECT count(*) AS n FROM attached_attempts').n!==0)throw Error('ATTACHED_SLOT_ALREADY_USED');
   run("INSERT INTO attached_attempts VALUES(?,?,?,?,'RESERVED')",slot,model,tokenLimit,outputLimit);
  });
 }
 function beforePrompt(role){
  tx(()=>{
   const a=attempt(),s=stages();
   if(!(role===roles[0]&&a?.state==='RESERVED'&&s.length===0)&&
      !(role===roles[1]&&a?.state==='DISPATCHING'&&s.length===1&&
      s[0].role===roles[0]&&s[0].state==='VALIDATED'&&
      a.token_limit-s[0].input_tokens-s[0].output_tokens>=2))
    throw Error('ATTACHED_STAGE_ORDER');
   run("INSERT INTO attached_stages VALUES(?,?,'DISPATCHING',NULL,NULL,NULL)",slot,role);
   run("UPDATE attached_attempts SET state='DISPATCHING' WHERE id=?",slot);
  });
 }
 function validatedStage(role,usage){
  tx(()=>{
   const a=attempt(),s=stages(),current=s.find(x=>x.role===role);
   if(a?.state!=='DISPATCHING'||current?.state!=='DISPATCHING'||!usage||
      !positive(usage.input_tokens)||!positive(usage.output_tokens)||usage.output_tokens>a.output_limit||usage.cost_usd!==0)
    throw Error('ATTACHED_USAGE_INVALID');
   const previous=s.filter(x=>x.state==='VALIDATED').reduce((n,x)=>n+x.input_tokens+x.output_tokens,0);
   if(!Number.isSafeInteger(previous+usage.input_tokens+usage.output_tokens)||
      previous+usage.input_tokens+usage.output_tokens>a.token_limit)throw Error('ATTACHED_STAGE_BUDGET');
   run("UPDATE attached_stages SET state='VALIDATED',input_tokens=?,output_tokens=?,cost_usd=? WHERE attempt_id=? AND role=?",
    usage.input_tokens,usage.output_tokens,usage.cost_usd,slot,role);
  });
 }
 function finish(proposal){
  return tx(()=>{
   const a=attempt(),s=stages();
   if(!a||!['RESERVED','DISPATCHING'].includes(a.state))throw Error('ATTACHED_FINISH_DENIED');
   const u=proposal?.usage;
   const valid=s.length===2&&s.every(x=>x.state==='VALIDATED')&&u?.cost_usd===0&&
    u.input_tokens===s.reduce((n,x)=>n+x.input_tokens,0)&&u.output_tokens===s.reduce((n,x)=>n+x.output_tokens,0);
   const state=valid?'VALIDATED':'UNKNOWN';
   run('UPDATE attached_attempts SET state=? WHERE id=?',state,slot);return state;
  });
 }
 return {reserve,beforePrompt,validatedStage,finish,status:()=>({attempt:attempt()??null,stages:stages(),billing_verified:false,runtime_admission:false}),close:()=>db.close()};
}
