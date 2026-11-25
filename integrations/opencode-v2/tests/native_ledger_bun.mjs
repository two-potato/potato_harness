import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Database} from 'bun:sqlite';
import {openNativeLedger,runJournaledProbe} from '../src/native-ledger.mjs';
const home=fs.mkdtempSync(path.join(os.tmpdir(),'potato-bun-ledger-'));
let ledger;
try{
 ledger=openNativeLedger(Database,home);
 assert.equal(ledger.status().historical.length,3);
 let calls=0;
 await assert.rejects(runJournaledProbe(ledger,{model:'opencode/test-free'},async()=>{calls++;}),/HISTORICAL_OUTCOMES_UNRESOLVED/);
 assert.equal(calls,0);ledger.close();ledger=undefined;
 const file=path.join(home,'.local/state/potato-harness/opencode-free/inference-ledger.sqlite3');
 const db=new Database(file);
 // Disposable test-only ledger, never the operator path.
 db.exec('DELETE FROM native_history');db.close();
 // Opening the real host API re-seeds historical holds, proving that deleting
 // rows cannot be used as a normal activation path.
 ledger=openNativeLedger(Database,home);
 assert.equal(ledger.status().historical.length,3);
 assert.equal(ledger.status().attempts.length,0);
 console.log('PASS: pinned Bun SQLite native ledger, persistent historical HOLD, zero dispatch');
}finally{ledger?.close();fs.rmSync(home,{recursive:true,force:true});}
