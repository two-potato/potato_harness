import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from datetime import datetime,timezone,timedelta

ROOT=Path(__file__).resolve().parents[2]

class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('harness.publisher.core'),'Publisher missing')
        from harness.publisher import Publisher, PublicationError
        from harness.controller import initialize,Controller,Event
        self.Error=PublicationError
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'state.db';initialize(self.db)
        task=json.loads((ROOT/'fixtures/valid/task.json').read_text());task.update(revision=0,row_version=0,scope=['src'])
        c=Controller(self.db,guard=lambda c:True);c.create_task(task,event_id='create',idempotency_key='create')
        for i,s in enumerate(['CLASSIFIED','PLANNED','ASSIGNED','EXECUTING']):c.transition('fixture',i,Event(str(i),str(i),s))
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO leases VALUES(?,?,?,?,?,?,?,?,?)',('lease','fixture','fixture',0,'worker','space',1,(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),'ACTIVE'))
            db.execute('INSERT INTO lease_claims VALUES(?,?,?)',('lease','path','src'))
        self.p=Publisher(self.db,self.root/'objects')
        self.args=dict(lease_id='lease',worker_session_id='worker',workspace_id='space',fencing_token=1,path='src/file.py',artifact=b'output',expected_digest='sha256:'+hashlib.sha256(b'output').hexdigest())

    def test_valid_immutable_blob_and_receipt(self):
        result=self.p.publish(**self.args)
        self.assertEqual(Path(result['object_path']).read_bytes(),b'output')
        self.assertEqual(self.p.publish(**self.args),result)

    def test_wrong_binding_rejected(self):
        for key,value in [('worker_session_id','other'),('workspace_id','other'),('fencing_token',2),('expected_digest','sha256:'+'0'*64),('path','elsewhere/x')]:
            with self.subTest(key=key),self.assertRaises(self.Error):self.p.publish(**dict(self.args,**{key:value}))

    def test_revoked_and_expired_lease_rejected_even_cached(self):
        self.p.publish(**self.args)
        for field,value in [('status','REVOKED'),('status','SUSPECT'),('expires_at','2000-01-01T00:00:00Z')]:
            with sqlite3.connect(self.db) as db:db.execute(f'UPDATE leases SET {field}=?',(value,))
            with self.assertRaises(self.Error):self.p.publish(**self.args)

    def test_stale_task_revision_rejected(self):
        with sqlite3.connect(self.db) as db:db.execute('UPDATE tasks SET revision=1')
        with self.assertRaises(self.Error):self.p.publish(**self.args)

    def test_traversal_secrets_and_symlink_store_denied(self):
        for path in ['../outside','src/../x','src/.env','/tmp/x','src//x']:
            with self.subTest(path=path),self.assertRaises(self.Error):self.p.publish(**dict(self.args,path=path))
        from harness.publisher import Publisher
        alias=self.root/'alias';alias.symlink_to(self.root/'objects',target_is_directory=True)
        with self.assertRaises(self.Error):Publisher(self.db,alias)

    def test_corrupted_existing_object_not_accepted(self):
        result=self.p.publish(**self.args);p=Path(result['object_path']);p.chmod(0o600);p.write_bytes(b'corruption')
        with self.assertRaises(self.Error):self.p.publish(**self.args)

    def test_expiry_during_storage_does_not_commit_receipt(self):
        import time
        from unittest.mock import patch
        with sqlite3.connect(self.db) as db:
            db.execute('UPDATE leases SET expires_at=?',((datetime.now(timezone.utc)+timedelta(milliseconds=100)).isoformat(),))
        with patch('harness.publisher.core.os.fsync',side_effect=lambda fd:time.sleep(.15)):
            with self.assertRaises(self.Error):self.p.publish(**self.args)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM artifact_publications').fetchone()[0],0)
