"""Sequential orchestration with real Git/SQLite and trusted synthetic executor."""
import json
from copy import deepcopy
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from harness.budget import Budget
from harness.context import compile_context
from harness.controller import Controller, ControllerError, Event, ROOT, initialize
from harness.leases import LeaseManager
from harness.publisher import Publisher
from harness.runtime.dispatch import reserve_provider_dispatch
from harness.runtime.workspace import repository_identity, _git
from harness.runtime.workflow import run_sequential_workflow
from harness.state import Outbox
from harness.verifier import TrustedEvidence, digest_bytes


class SequentialTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.repo=self.root/'source'
        self.repo.mkdir()
        _git(self.repo,'init')
        for name in ('api.py','ui.py'):
            (self.repo/name).write_text('value = 1\n')
        _git(self.repo,'add','.')
        _git(self.repo,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','base')
        self.base=_git(self.repo,'rev-parse','HEAD')
        self.db=self.root/'state.db'
        initialize(self.db)
        self.controller=Controller(self.db,guard=lambda _:True)
        self.budget=Budget(self.db)
        self.workspaces=self.root/'workspaces'
        self.workspaces.mkdir(mode=0o700)
        self.objects=self.root/'objects'
        self.publisher=Publisher(self.db,self.objects)
        self.attestations={}
        self.calls=[]
        self.add('api','backend',[])
        self.add('ui','frontend',['api'])
        self.dag={'schema_version':'3.0.1','workflow_id':'flow','nodes':[
            {'id':'a','task_id':'api','needs':[]},{'id':'b','task_id':'ui','needs':['a']}]}
        self.args=dict(dag=self.dag,workflow_id='flow',user_turn_id='turn',
                       repository_id=repository_identity(self.repo),approved_revisions={'api':0,'ui':0},
                       available_owners=('backend','frontend'),repo=self.repo,workspace_root=self.workspaces,
                       object_store=self.objects,output_paths={'api':['api.py'],'ui':['ui.py']},
                       collector=self.attestations.__getitem__,trusted_issuers=frozenset({'fixture-host'}),
                       execute=self.execute)

    def add(self,key,owner,depends):
        t=json.loads((ROOT/'fixtures/valid/task.json').read_text())
        commit={'hash_algorithm':'sha1','value':self.base}
        t.update(task_id=key,owner=owner,scope=[key+'.py'],depends_on=depends,
                 workflow_id='flow',user_turn_id='turn',repository_id=repository_identity(self.repo),
                 revision=0,row_version=0,base_commit=commit,target_commit=commit,budget_id='b-'+key)
        self.controller.create_task(t,event_id=key+'create',idempotency_key=key+'create')
        for status in ('CLASSIFIED','PLANNED'):
            self.move(key,status)
        record=json.loads((ROOT/'fixtures/valid/budget.json').read_text())
        record.update(task_id=key,budget_id='b-'+key,revision=0,token_soft=100000,token_hard=100000,
                      cost_usd_soft=1,cost_usd_hard=1,wall_time_s_soft=90,wall_time_s_hard=90)
        self.budget.configure(key,record)

    def move(self,key,status):
        t=self.controller.get_task(key)
        return self.controller.transition(key,t['row_version'],Event(key+status,key+status,status))

    def execute(self,task,layout,segments):
        key=task['task_id']
        self.calls.append(key)
        self.assertEqual(len(segments),int(key=='ui'))
        session='session-'+key
        if key=='ui':
            self.assertIn('value = 2',segments[0]['text'])
            self.assertEqual((Path(layout['workspace'])/'api.py').read_text(),'value = 1\n')
        self.move(key,'ASSIGNED')
        t=self.move(key,'EXECUTING')
        lease=LeaseManager(self.db).acquire(key,t['row_version'],session,layout['workspace_id'],
                                          [{'kind':'path','key':key+'.py'}])
        pack=compile_context(t,{'role':t['owner'],'session_id':session},segments,99999,len)
        receipt=reserve_provider_dispatch(self.db,task_id=key,revision=0,row_version=t['row_version'],
                  owner=t['owner'],lease_id=lease['lease_id'],session=session,workspace=layout['workspace_id'],
                  model='fixture/test',context_digest=pack['content_hash'],tokens=100000,cost=.5)
        data=b'value = 2\n'
        digest=digest_bytes(data)
        self.publisher.publish(lease_id=lease['lease_id'],worker_session_id=session,
            workspace_id=layout['workspace_id'],fencing_token=lease['fencing_token'],
            path=key+'.py',artifact=data,expected_digest=digest)
        Outbox(self.db).finish(receipt['effect_id'],{'synthetic':True},True)
        self.budget.settle(receipt['attempt_id'],10,0)
        LeaseManager(self.db).release(lease['lease_id'],reconcile=True)
        integration=Path(layout['integration_repo'])
        (integration/(key+'.py')).write_bytes(data)
        _git(integration,'add',key+'.py')
        _git(integration,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','fixture proposal')
        target=_git(integration,'rev-parse','HEAD')
        t=self.controller.pin_target(key,t['row_version'],{'hash_algorithm':'sha1','value':target},
                                     event_id=key+'pin',idempotency_key=key+'pin')
        artifact=b'synthetic evidence'
        record=json.loads((ROOT/'fixtures/valid/evidence-record.json').read_text())
        record.update(evidence_id=key+'evidence',task_id=key,task_revision=1,
                      repository_id=t['repository_id'],commit=t['target_commit'],
                      artifact_digest=digest_bytes(artifact),issuer_id='fixture-host',
                      attestation_ref=key+'attestation',run_id=key+'run')
        self.attestations[record['attestation_ref']]=TrustedEvidence(deepcopy(record),artifact)
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?,?)',(record['evidence_id'],key,1,target,
                         record['artifact_digest'],record['attestation_ref'],json.dumps(record)))
        for status in ('REVIEWING','VERIFYING','COMPLETION_AUDITING','ACCEPTED','DONE'):
            self.move(key,status)
        return {key+'.py':digest}

    def run_flow(self,**overrides):
        return run_sequential_workflow(self.db,**dict(self.args,**overrides))

    def test_sequential_dependency_uses_real_publisher_and_fresh_evidence(self):
        result=self.run_flow()
        self.assertEqual(result['status'],'DONE',result)
        self.assertEqual(self.calls,['api','ui'])
        self.assertEqual(result['completed'],['api','ui'])
        self.assertEqual(_git(self.repo,'rev-parse','HEAD'),self.base)
        self.assertEqual((self.repo/'api.py').read_text(),'value = 1\n')
        with self.assertRaises(ControllerError):
            self.run_flow()

    def test_callback_cannot_claim_completion_without_controller_evidence(self):
        result=self.run_flow(execute=lambda *args:{'api.py':digest_bytes(b'fake')})
        self.assertEqual(result['status'],'HOLD')
        self.assertEqual(result['active_task'],'api')
        self.assertEqual(result['completed'],[])
        with self.assertRaises(ControllerError):
            self.run_flow()

    def test_revoked_evidence_blocks_dependent_execution(self):
        def execute(*args):
            result=self.execute(*args)
            self.attestations['apiattestation']=TrustedEvidence(
                self.attestations['apiattestation'].record,b'synthetic evidence',revoked=True)
            return result
        result=self.run_flow(execute=execute)
        self.assertEqual(result['status'],'HOLD')
        self.assertEqual(self.calls,['api'])

    def test_interrupt_preserves_durable_no_replay_marker(self):
        def stop(*args):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_flow(execute=stop)
        with sqlite3.connect(self.db) as db:
            row=db.execute('SELECT status,active_task FROM sequential_workflows').fetchone()
        self.assertEqual(row,('RUNNING','api'))
        with self.assertRaises(ControllerError):
            self.run_flow()

    def test_wrong_artifact_allowlist_is_rejected_before_execution(self):
        with self.assertRaises(ControllerError):
            self.run_flow(output_paths={'api':['ui.py'],'ui':['ui.py']})
        self.assertEqual(self.calls,[])
