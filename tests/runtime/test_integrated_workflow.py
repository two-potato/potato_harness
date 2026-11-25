"""Real bounded runtime under the sequential coordinator; synthetic worker/sandbox seams."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from harness.budget import Budget
from harness.controller import Controller, ControllerError, Event, ROOT, initialize
from harness.runtime.workspace import _git, repository_identity
from harness.runtime.workflow_executor import run_fixture_workflow
from harness.state import Outbox


class IntegratedWorkflowTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
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
        self.c=Controller(self.db,guard=lambda c:c.after['status'] in ('CLASSIFIED','PLANNED'))
        self.budget=Budget(self.db)
        self.spaces=self.root/'spaces'
        self.spaces.mkdir(mode=0o700)
        self.objects=self.root/'objects'
        self.objects.mkdir(mode=0o700)
        self.calls=[]
        for key,role,deps in [('api','backend',[]),('ui','frontend',['api'])]:
            task=json.loads((ROOT/'fixtures/valid/task.json').read_text())
            commit={'hash_algorithm':'sha1','value':self.base}
            task.update(task_id=key,owner=role,scope=[key+'.py'],depends_on=deps,
                workflow_id='flow',user_turn_id='turn',repository_id=repository_identity(self.repo),
                revision=0,row_version=0,base_commit=commit,target_commit=commit,
                budget_id='budget-'+key,task_class='BOUNDED',risk='LOW',policy_version='bounded-trial-3.0',
                objective='Replace fixture value',required_checks=['relevant_checks','basic_review','acceptance_coverage'],
                acceptance=[{'id':'configured-tests','expected':'Replace fixture value',
                             'requires':['relevant_checks','basic_review','acceptance_coverage']}])
            task=self.c.create_task(task,event_id=key+'create',idempotency_key=key+'create')
            for status in ('CLASSIFIED','PLANNED'):
                task=self.c.transition(key,task['row_version'],Event(key+status,key+status,status))
            record=json.loads((ROOT/'fixtures/valid/budget.json').read_text())
            record.update(task_id=key,budget_id=task['budget_id'],revision=0,token_soft=100000,
                token_hard=100000,cost_usd_soft=1,cost_usd_hard=1,wall_time_s_soft=60,wall_time_s_hard=60)
            self.budget.configure(key,record)
        self.args=dict(dag={'schema_version':'3.0.1','workflow_id':'flow','nodes':[
                           {'id':'a','task_id':'api','needs':[]},{'id':'b','task_id':'ui','needs':['a']}]},
            workflow_id='flow',user_turn_id='turn',repository_id=repository_identity(self.repo),
            approved_revisions={'api':0,'ui':0},available_owners=('backend','frontend'),
            repo=self.repo,workspace_root=self.spaces,object_store=self.objects,
            test_argv_by_task={'api':['/usr/bin/python3','-c','assert True'],
                               'ui':['/usr/bin/python3','-c','assert True']},
            worker=self.worker,sandbox_probe=lambda:{'available':True,'reason':'injected test seam'},
            sandbox_run=lambda *a,**k:{'returncode':0,'stdout':'ok','stderr':'','timed_out':False})

    def worker(self,request,command,timeout):
        self.assertEqual(command,['/usr/bin/false'])
        self.assertEqual(request['model'],'fixture/workflow')
        role=request['role']
        self.calls.append(role)
        data=json.loads(request['prompt'])['data']
        dependencies=[x for x in data if x['name'].startswith('dependency:')]
        if role=='frontend':
            self.assertEqual(len(dependencies),1)
            self.assertIn('value = 2',dependencies[0]['untrusted_data'])
        else:
            self.assertEqual(dependencies,[])
        self.assertEqual(list(Path(request['projectDir']).iterdir()),[])
        return {'edits':[{'path':'api.py' if role=='backend' else 'ui.py','content':'value = 2\n'}],
                'summary':'synthetic replacement','usage':{'input_tokens':10,'output_tokens':10,'cost_usd':0}}

    def run_flow(self,**patch):
        return run_fixture_workflow(self.db,**dict(self.args,**patch))

    def test_shared_runtime_two_tasks_done(self):
        result=self.run_flow()
        self.assertEqual(result['status'],'DONE',result)
        self.assertEqual(self.calls,['backend','frontend'])
        self.assertEqual(result['completed'],['api','ui'])
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM evidence').fetchone()[0],6)
            self.assertEqual(db.execute("SELECT count(*) FROM provider_attempts WHERE kind='PREFLIGHT'").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM leases WHERE status IN ('ACTIVE','SUSPECT')").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM outbox WHERE state='SUCCEEDED'").fetchone()[0],2)
            self.assertEqual(db.execute('SELECT count(*) FROM budget_reservations WHERE settlement IS NULL').fetchone()[0],0)
        self.assertEqual((self.repo/'api.py').read_text(),'value = 1\n')
        for directory in self.spaces.iterdir():
            result=json.loads((directory/'result.json').read_text())
            self.assertEqual(result['provider_mode'],'synthetic')
        with self.assertRaises(ControllerError):
            self.run_flow()

    def test_uncertain_first_worker_stops_second(self):
        def interrupted(*args):
            self.calls.append('backend')
            raise RuntimeError('synthetic unknown outcome')
        result=self.run_flow(worker=interrupted)
        self.assertEqual(result['status'],'HOLD')
        self.assertEqual(self.calls,['backend'])
        self.assertEqual(len(Outbox(self.db).unresolved('api')),1)
        self.assertEqual(self.c.get_task('ui')['status'],'PLANNED')
        self.assertEqual(Outbox(self.db).unresolved('ui'),[])

    def test_failed_validation_prevents_dependent_dispatch(self):
        result=self.run_flow(sandbox_run=lambda *a,**k:{'returncode':1,'stdout':'fail','stderr':'','timed_out':False})
        self.assertEqual(result['status'],'HOLD')
        self.assertEqual(self.calls,['backend'])
        self.assertEqual(self.c.get_task('ui')['status'],'PLANNED')
        self.assertEqual(self.c.get_task('api')['status'],'BLOCKED')

    def test_missing_worker_and_invalid_tests_fail_before_claim(self):
        for change in (dict(worker=None),dict(test_argv_by_task={'api':['python'],'ui':['/usr/bin/false']})):
            with self.assertRaises((ValueError,ControllerError)):
                self.run_flow(**change)
        self.assertEqual(self.calls,[])
        self.assertEqual(list(self.spaces.iterdir()),[])
