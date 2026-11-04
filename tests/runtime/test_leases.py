import json
import multiprocessing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from harness.controller import Controller, Event, initialize
from harness.leases import LeaseManager, LeaseError

ROOT=Path(__file__).resolve().parents[2]

def racer(path,barrier,queue):
    barrier.wait(timeout=10)
    try:
        LeaseManager(path).acquire('fixture',4,str(multiprocessing.current_process().pid),'workspace',[{'kind':'path','key':'src'}])
        queue.put('ok')
    except LeaseError:
        queue.put('blocked')

class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.db';initialize(self.path)
        self.c=Controller(self.path,guard=lambda context:True)
        self.add_task('fixture','fixture')
        self.manager=LeaseManager(self.path)

    def add_task(self,name,repo):
        task=json.loads((ROOT/'fixtures/valid/task.json').read_text())
        task.update(task_id=name,repository_id=repo,revision=0,row_version=0)
        self.c.create_task(task,event_id=name+'create',idempotency_key=name+'create')
        for i,state in enumerate(('CLASSIFIED','PLANNED','ASSIGNED','EXECUTING')):
            self.c.transition(name,i,Event(name+state,name+state,state))

    def acquire(self,key='src',**kwargs):
        return self.manager.acquire('fixture',4,'session','workspace',[{'kind':'path','key':key}],**kwargs)

    def test_schema_binding_and_unrelated_token(self):
        lease=self.acquire()
        other=self.acquire('docs')
        self.assertGreater(other['fencing_token'],lease['fencing_token'])
        self.assertEqual(self.manager.validate(lease['lease_id'],'fixture',0,'session','workspace'),lease)
        for args in [('fixture',1,'session','workspace'),('fixture',0,'wrong','workspace'),('fixture',0,'session','wrong')]:
            with self.assertRaises(LeaseError):self.manager.validate(lease['lease_id'],*args)
        from jsonschema import Draft202012Validator,FormatChecker
        Draft202012Validator(json.loads((ROOT/'schemas/lease.schema.json').read_text()),format_checker=FormatChecker()).validate(lease)

    def test_conflicts_atomic_and_repository_independence(self):
        lease=self.acquire('src/child')
        for key in ('src','src/child','src/child/nested'):
            with self.assertRaises(LeaseError):self.acquire(key)
        with self.assertRaises(LeaseError):
            self.manager.acquire('fixture',4,'s','w',[{'kind':'path','key':'free'},{'kind':'path','key':'src'}])
        self.acquire('free')
        self.add_task('other','other-repo')
        self.manager.acquire('other',4,'s','w',[{'kind':'path','key':'src'}])
        logical=self.manager.acquire('fixture',4,'s','w',[{'kind':'logical','key':'database'}])
        with self.assertRaises(LeaseError):self.manager.acquire('fixture',4,'s','w',logical['resources'])
        self.assertEqual(lease['status'],'ACTIVE')

    def test_expired_and_suspect_block_until_reconciled(self):
        lease=self.acquire()
        with sqlite3.connect(self.path) as db:db.execute("UPDATE leases SET expires_at='2000-01-01T00:00:00+00:00' WHERE lease_id=?",(lease['lease_id'],))
        with self.assertRaises(LeaseError):self.manager.validate(lease['lease_id'],'fixture',0,'session','workspace')
        with self.assertRaises(LeaseError):self.acquire()
        self.manager.suspect(lease['lease_id'])
        with self.assertRaises(LeaseError):self.acquire()
        with self.assertRaises(LeaseError):self.manager.release(lease['lease_id'])
        self.manager.release(lease['lease_id'],reconcile=True)
        self.acquire()
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT status FROM leases WHERE lease_id=?',(lease['lease_id'],)).fetchone()[0],'REVOKED')
            self.assertEqual(db.execute('SELECT count(*) FROM lease_claims WHERE lease_id=?',(lease['lease_id'],)).fetchone()[0],1)

    def test_bad_resources_cas_and_stale_task(self):
        for key in ('/root','a/../b','a//b','a/./b','a/','a\\b','a*','../a','a\nsecret'):
            with self.assertRaises(LeaseError):self.acquire(key)
        with self.assertRaises(LeaseError):self.manager.acquire('fixture',3,'s','w',[{'kind':'path','key':'x'}])
        lease=self.acquire()
        self.c.transition('fixture',4,Event('review','review','REVIEWING'))
        with self.assertRaises(LeaseError):self.manager.validate(lease['lease_id'],'fixture',0,'session','workspace')
        with self.assertRaises(LeaseError):self.acquire('free')

    def test_process_race(self):
        context=multiprocessing.get_context('spawn');barrier=context.Barrier(2);queue=context.Queue()
        workers=[context.Process(target=racer,args=(str(self.path),barrier,queue)) for _ in range(2)]
        for worker in workers:worker.start()
        for worker in workers:worker.join(15);self.assertEqual(worker.exitcode,0)
        self.assertEqual(sorted(queue.get(timeout=2) for _ in workers),['blocked','ok'])
