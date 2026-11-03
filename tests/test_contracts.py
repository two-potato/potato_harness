import copy,json,sqlite3,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from validate_pack import validators
from jsonschema import ValidationError

class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.v=validators()
    def fixture(self,n):return json.loads((ROOT/'fixtures/valid'/f'{n}.json').read_text())
    def rejects(self,n,change):
        x=self.fixture(n);change(x)
        with self.assertRaises(ValidationError):self.v[n].validate(x)
    def test_missing_task_scope(self):self.rejects('task',lambda x:x.pop('scope'))
    def test_empty_scope(self):self.rejects('task',lambda x:x.update(scope=[]))
    def test_unknown_state(self):self.rejects('task',lambda x:x.update(status='SHIPPED'))
    def test_empty_acceptance(self):self.rejects('task',lambda x:x.update(acceptance=[]))
    def test_missing_revision(self):self.rejects('task',lambda x:x.pop('revision'))
    def test_path_traversal(self):self.rejects('task',lambda x:x.update(scope=['../secrets']))
    def test_glob_rejected(self):self.rejects('task',lambda x:x.update(scope=['backend/**']))
    def test_invalid_commit(self):self.rejects('evidence-record',lambda x:x['commit'].update(value='fake'))
    def test_hash_algorithm_length(self):self.rejects('evidence-record',lambda x:x['commit'].update(hash_algorithm='sha256'))
    def test_sha256_commit_valid(self):
        x=self.fixture('evidence-record');x['commit']={'hash_algorithm':'sha256','value':'c'*64};self.v['evidence-record'].validate(x)
    def test_invalid_artifact_digest(self):self.rejects('evidence-record',lambda x:x.update(artifact_digest='fake'))
    def test_missing_attestation(self):self.rejects('evidence-record',lambda x:x.pop('attestation_ref'))
    def test_empty_acceptance_ids(self):self.rejects('evidence-record',lambda x:x.update(acceptance_ids=[]))
    def test_date_format_enabled(self):self.rejects('evidence-record',lambda x:x.update(created_at='yesterday'))
    def test_missing_action_binding(self):self.rejects('human-approval',lambda x:x.pop('action_digest'))
    def test_empty_approval_scope(self):self.rejects('human-approval',lambda x:x.update(scope=[]))
    def test_missing_approval_nonce(self):self.rejects('human-approval',lambda x:x.pop('nonce'))
    def test_authoritative_jev_rejected(self):self.rejects('jev-result',lambda x:x.update(authoritative=True))
    def test_unknown_jev_verdict(self):self.rejects('jev-result',lambda x:x.update(verdict='DONE'))
    def test_no_zero_worker_budget(self):self.rejects('budget',lambda x:x.update(max_parallel_workers=0))
    def test_unknown_fields_rejected(self):self.rejects('task',lambda x:x.update(skip_checks=True))
    def test_format_is_not_authentication(self):
        # Deliberately shows structural validity cannot establish issuer trust.
        x=self.fixture('human-approval');x['issuer_id']='untrusted-model';self.v['human-approval'].validate(x)

class SQLTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.executescript((ROOT/'state/001_init.sql').read_text())
        self.db.execute("INSERT INTO tasks VALUES('T',0,0,'NEW','backend','repo','{}','2026-11-03')")
    def tearDown(self):self.db.close()
    def test_foreign_keys_enabled(self):self.assertEqual(self.db.execute('PRAGMA foreign_keys').fetchone()[0],1)
    def test_bad_task_state_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE tasks SET state='BOGUS'")
    def test_outbox_unique_key(self):
        sql="INSERT INTO outbox(effect_id,task_id,task_revision,idempotency_key,action_digest,state,payload_json,created_at,updated_at) VALUES(?, 'T',0,'k','d','PENDING','{}','now','now')"
        self.db.execute(sql,('e1',))
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute(sql,('e2',))
    def test_outbox_unknown_is_storable(self):
        self.db.execute("INSERT INTO outbox(effect_id,task_id,task_revision,idempotency_key,action_digest,state,payload_json,created_at,updated_at) VALUES('e','T',0,'k','d','UNKNOWN','{}','now','now')")
        self.assertEqual(self.db.execute('SELECT state FROM outbox').fetchone()[0],'UNKNOWN')
    def test_stale_cas_updates_zero_rows(self):
        self.assertEqual(self.db.execute("UPDATE tasks SET row_version=1 WHERE task_id='T' AND row_version=0").rowcount,1)
        self.assertEqual(self.db.execute("UPDATE tasks SET row_version=2 WHERE task_id='T' AND row_version=0").rowcount,0)

class PolicyTests(unittest.TestCase):
    def test_release_profiles_no_disabled_requirement(self):
        profiles=json.loads((ROOT/'policy/releases.json').read_text())
        def resolve(k):
            p=profiles[k]
            required,disabled=resolve(p['inherits']) if 'inherits' in p else (set(),set())
            required=required|set(p.get('required',[]));disabled=(disabled|set(p.get('disabled',[])))-set(p.get('enabled',[]))
            return required,disabled
        for k in ['3.0','3.1','3.2','3.3']:
            required,disabled=resolve(k);self.assertFalse(required&disabled,k)
    def test_sensitive_floors_present(self):
        p=json.loads((ROOT/'policy/checks.json').read_text())
        for k in ['auth','payments','secrets','permissions','schema_migration','production']:
            self.assertEqual(p['change_signal_floor'][k],'HIGH')
    def test_scenario_ids_complete(self):
        cases=json.loads((ROOT/'evals/cases.json').read_text());ids=[c['id'] for c in cases]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(set(ids),{f'{p}{i:02}' for p,n in [('H',22),('M',10),('C',10)] for i in range(1,n+1)})

if __name__=='__main__':unittest.main()
