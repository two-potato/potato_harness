"""Historical trial reports are advisory, bounded and non-mutating."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from tools.native_reconciliation import inspect_trial, main

class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.db=self.root/'state.db'
        with sqlite3.connect(self.db) as db:
            db.executescript("""
                CREATE TABLE schema_migrations(version INTEGER);
                INSERT INTO schema_migrations VALUES(1);
                CREATE TABLE tasks(task_id TEXT PRIMARY KEY,state TEXT);
                INSERT INTO tasks VALUES('local-task','BLOCKED');
                CREATE TABLE outbox(effect_id TEXT PRIMARY KEY,task_id TEXT,state TEXT,
                  provider_operation_id TEXT,created_at TEXT,updated_at TEXT,payload_json TEXT);
                INSERT INTO outbox VALUES('local-effect','local-task','UNKNOWN','SECRET_PROVIDER_ID',
                  '2026-11-25T08:18:06+00:00','2026-11-25T08:19:21+00:00','SECRET_PROMPT');
                INSERT INTO outbox VALUES('other-effect','other-task','UNKNOWN',NULL,NULL,NULL,NULL);
            """)
        (self.root/'run.json').write_text(json.dumps({'task_id':'local-task','state':'HOLD','secret':'SECRET_KEY'}))
        (self.root/'gateway-phases.json').write_text(json.dumps({'outcome':'ERROR','events':[
            {'phase':'omo','status':'ok','elapsed_ms':5},
            {'phase':'valera','status':'error','elapsed_ms':66994,'step':'prompt','reason_code':'DEADLINE'},
            {'phase':'valera','status':'error','elapsed_ms':1,'step':'prompt','reason_code':'SECRET_ERROR'}]}))
    def test_unknown_local_effect_no_secret_no_write(self):
        before=self.db.read_bytes()
        r=inspect_trial(self.root)
        self.assertEqual(r['provider_mode'],'UNSPECIFIED_LEGACY')
        self.assertEqual(r['local_finding'],'UNRESOLVED_EFFECTS')
        self.assertEqual(r['unresolved_effect_count'],1)
        self.assertEqual(r['unresolved_with_provider_id'],1)
        self.assertEqual(r['unresolved_effects'][0]['created_utc'],'2026-11-25T08:18:06+00:00')
        self.assertEqual(r['gateway']['errors'][0]['reason_code'],'DEADLINE')
        self.assertEqual(len(r['gateway']['errors']),1)
        self.assertNotIn('SECRET',json.dumps(r))
        self.assertNotIn('local-effect',json.dumps(r))
        self.assertFalse(r['billing_verified'])
        self.assertFalse(r['provider_outcome_verified'])
        self.assertEqual(before,self.db.read_bytes())
        digest=r.pop('report_sha256')
        self.assertEqual(digest,hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest())
    def test_missing_provider_identifier_does_not_settle_effect(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE outbox SET provider_operation_id=NULL WHERE task_id='local-task'")
        r=inspect_trial(self.root)
        self.assertEqual(r['unresolved_with_provider_id'],0)
        self.assertEqual(r['unresolved_effect_count'],1)
        self.assertFalse(r['runtime_admission'])
    def test_no_local_unresolved_is_not_provider_verification(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE outbox SET state='SUCCEEDED' WHERE task_id='local-task'")
        r=inspect_trial(self.root)
        self.assertEqual(r['local_finding'],'NO_LOCAL_UNRESOLVED_EFFECTS')
        self.assertFalse(r['provider_outcome_verified'])
        self.assertFalse(r['runtime_admission'])
    def test_missing_db_not_created_and_cli_redacts_path(self):
        self.db.unlink()
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['--state',str(self.root)]),2)
        self.assertFalse(self.db.exists())
        self.assertNotIn(str(self.root),out.getvalue())
        self.assertEqual(json.loads(out.getvalue())['reports'][0]['status'],'UNAVAILABLE')
    def test_symlink_and_oversize_metadata_rejected(self):
        p=self.root/'gateway-phases.json'
        p.unlink()
        p.symlink_to(self.root/'run.json')
        with self.assertRaises(ValueError):
            inspect_trial(self.root)
        p.unlink()
        p.write_bytes(b' '* (1024*1024+1))
        with self.assertRaises(ValueError):
            inspect_trial(self.root)
    def test_malformed_timestamps_not_echoed(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE outbox SET created_at='SECRET',updated_at='SECRET' WHERE task_id='local-task'")
        r=inspect_trial(self.root)
        self.assertIsNone(r['unresolved_effects'][0]['created_utc'])
        self.assertIsNone(r['unresolved_effects'][0]['updated_utc'])
