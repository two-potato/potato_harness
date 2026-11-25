"""Verified dependency handoff using real Git, SQLite and Publisher.

Controller guards and evidence collector are explicitly synthetic test seams.
No provider, worker or project execution is involved.
"""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from harness.context import compile_context
from harness.controller import Controller, Event, ROOT, initialize
from harness.leases import LeaseManager
from harness.publisher import Publisher
from harness.runtime.handoff import dependency_segments, HandoffError
from harness.verifier import TrustedEvidence, digest_bytes


class HandoffTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.repo=self.root/'integration'
        self.repo.mkdir()
        self.git('init')
        self.git('config','user.name','Fixture')
        self.git('config','user.email','fixture@example.invalid')
        (self.repo/'api.py').write_text('value = 1\n')
        self.git('add','api.py')
        self.git('commit','-m','base')
        self.base=self.git('rev-parse','HEAD')
        self.db=self.root/'state.db'
        initialize(self.db)
        self.c=Controller(self.db,guard=lambda _:True)
        self.add('api','backend',['api.py'])
        self.add('ui','frontend',['ui.py'],['api'])
        for status in ('CLASSIFIED','PLANNED','ASSIGNED','EXECUTING'):
            self.move('api',status)
        for status in ('CLASSIFIED','PLANNED'):
            self.move('ui',status)
        task=self.c.get_task('api')
        lease=LeaseManager(self.db).acquire('api',task['row_version'],'author-session','api-space',
                                           [{'kind':'path','key':'api.py'}])
        self.content=b'value = 2\n# API_KEY=secretvalue\n'
        self.digest=digest_bytes(self.content)
        self.store=self.root/'objects'
        self.receipt=Publisher(self.db,self.store).publish(
            lease_id=lease['lease_id'],worker_session_id='author-session',
            workspace_id='api-space',fencing_token=lease['fencing_token'],
            path='api.py',artifact=self.content,expected_digest=self.digest)
        LeaseManager(self.db).release(lease['lease_id'],reconcile=True)
        (self.repo/'api.py').write_bytes(self.content)
        self.git('add','api.py')
        self.git('commit','-m','candidate')
        self.target=self.git('rev-parse','HEAD')
        self.c.pin_target('api',task['row_version'],{'hash_algorithm':'sha1','value':self.target},
                          event_id='pin-api',idempotency_key='pin-api')
        artifact=b'trusted synthetic test output'
        task=self.c.get_task('api')
        record=json.loads((ROOT/'fixtures/valid/evidence-record.json').read_text())
        record.update(evidence_id='api-evidence',task_id='api',task_revision=1,
                      repository_id='repo',commit=task['target_commit'],
                      artifact_digest=digest_bytes(artifact),issuer_id='fixture-host',
                      attestation_ref='fixture-attestation')
        self.record=record
        self.attestation=TrustedEvidence(deepcopy(record),artifact)
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?,?)',
                       (record['evidence_id'],'api',1,self.target,record['artifact_digest'],
                        record['attestation_ref'],json.dumps(record)))
        for status in ('REVIEWING','VERIFYING','COMPLETION_AUDITING','ACCEPTED','DONE'):
            self.move('api',status)
        self.args=dict(receiver_id='ui',receiver_revision=0,producer_id='api',producer_revision=1,
                       producer_repo=self.repo,object_store=self.store,
                       expected_artifacts={'api.py':self.digest},collector=self.collect,
                       trusted_issuers=frozenset({'fixture-host'}))

    def git(self,*args):
        return subprocess.check_output(['/usr/bin/git','-C',str(self.repo),*args],
                                       stderr=subprocess.DEVNULL).decode().strip()

    def add(self,key,owner,scope,depends=None,**extra):
        t=json.loads((ROOT/'fixtures/valid/task.json').read_text())
        commit={'hash_algorithm':'sha1','value':self.base}
        t.update(task_id=key,owner=owner,scope=scope,depends_on=depends or [],
                 revision=0,row_version=0,workflow_id='workflow',user_turn_id='turn',
                 repository_id='repo',base_commit=commit,target_commit=commit)
        t.update(extra)
        self.c.create_task(t,event_id=key+'create',idempotency_key=key+'create')

    def move(self,key,status):
        task=self.c.get_task(key)
        self.c.transition(key,task['row_version'],Event(key+status,key+status,status))

    def collect(self,ref):
        if ref!=self.record['attestation_ref']:
            raise KeyError(ref)
        return self.attestation

    def read(self,**patch):
        return dependency_segments(self.db,**dict(self.args,**patch))

    def test_direct_dependency_handoff_is_inert_redacted_context(self):
        before=self.c.get_task('ui')
        segments=self.read()
        self.assertEqual(len(segments),1)
        self.assertEqual(segments[0]['trust'],'untrusted')
        self.assertTrue(segments[0]['mandatory'])
        self.assertIn('value = 2',segments[0]['text'])
        self.assertIn(self.target,segments[0]['text'])
        pack=compile_context(before,{'role':'frontend','session_id':'ui-session'},
                             segments,100000,len)
        self.assertIn('value = 2',pack['text'])
        self.assertNotIn('secretvalue',pack['text'])
        self.assertEqual(self.c.get_task('ui'),before)
        self.assertFalse((self.repo/'ui.py').exists())

    def test_stale_and_unauthorized_dependency_bindings_rejected(self):
        self.add('other','qa',['ui.py'])
        self.move('other','CLASSIFIED')
        self.move('other','PLANNED')
        self.add('foreign','frontend',['ui.py'],['api'],workflow_id='foreign')
        self.move('foreign','CLASSIFIED')
        self.move('foreign','PLANNED')
        for patch in (dict(receiver_id='other'),dict(receiver_id='foreign'),
                      dict(receiver_revision=1),dict(producer_revision=0),
                      dict(producer_revision=True),dict(receiver_id='api'),
                      dict(expected_artifacts={'other.py':self.digest}),
                      dict(expected_artifacts={'../api.py':self.digest})):
            with self.subTest(patch=patch),self.assertRaises(HandoffError):
                self.read(**patch)

    def test_missing_or_revoked_evidence_never_transferred(self):
        for attestation in (TrustedEvidence(self.record,self.attestation.artifact,revoked=True),
                            TrustedEvidence(self.record,b'corrupt')):
            self.attestation=attestation
            with self.assertRaises(HandoffError):
                self.read()
        with sqlite3.connect(self.db) as db:
            db.execute('DELETE FROM evidence')
        with self.assertRaises(HandoffError):
            self.read()

    def test_tampered_object_and_symlink_rejected(self):
        path=Path(self.receipt['object_path'])
        path.chmod(0o600)
        path.write_bytes(b'tampered')
        with self.assertRaises(HandoffError):
            self.read()
        path.unlink()
        outside=self.root/'outside'
        outside.write_bytes(self.content)
        path.symlink_to(outside)
        with self.assertRaises(HandoffError):
            self.read()

    def test_publication_must_match_verified_commit_not_just_object_digest(self):
        content=b'other valid bytes'
        digest=digest_bytes(content)
        target=self.store/digest.split(':')[1]
        target.write_bytes(content)
        target.chmod(0o400)
        receipt=dict(self.receipt,digest=digest,object_path=str(target))
        with sqlite3.connect(self.db) as db:
            db.execute('UPDATE artifact_publications SET digest=?,receipt=?',
                       (digest,json.dumps(receipt)))
        with self.assertRaises(HandoffError):
            self.read(expected_artifacts={'api.py':digest})

    def test_pin_event_and_publication_lease_required(self):
        with sqlite3.connect(self.db) as db:
            db.execute("DELETE FROM events WHERE event_type='pin_target'")
        with self.assertRaises(HandoffError):
            self.read()

    def test_untrusted_issuer_or_unpinned_git_repository_denied(self):
        with self.assertRaises(HandoffError):
            self.read(trusted_issuers=frozenset({'unknown'}))
        with self.assertRaises(HandoffError):
            self.read(producer_repo=self.root)

    def test_active_lease_on_completed_producer_blocks_transfer(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE leases SET status='SUSPECT'")
        with self.assertRaises(HandoffError):
            self.read()
