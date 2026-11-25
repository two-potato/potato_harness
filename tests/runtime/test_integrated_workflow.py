"""Bounded workflow runtime: synthetic proposals with real or injected isolation."""
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
        self.prepare()

    def prepare(self,*,independent=False,overlap=False,team=False):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.repo=self.root/'source'
        self.repo.mkdir()
        _git(self.repo,'init')
        from harness.scheduler import SPECIALISTS
        roster=[('fixture_'+role,role,[]) for role in sorted(SPECIALISTS)] if team else [
            ('api','backend',[]),('ui','frontend',[] if independent else ['api'])]
        for key,_,_ in roster:
            (self.repo/(key+'.py')).write_text('value = 1\n')
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
        for key,role,deps in roster:
            task=json.loads((ROOT/'fixtures/valid/task.json').read_text())
            commit={'hash_algorithm':'sha1','value':self.base}
            task.update(task_id=key,owner=role,scope=['api.py' if overlap else key+'.py'],depends_on=deps,
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
                           {'id':key,'task_id':key,'needs':deps} for key,_,deps in roster]},
            workflow_id='flow',user_turn_id='turn',repository_id=repository_identity(self.repo),
            approved_revisions={key:0 for key,_,_ in roster},available_owners=tuple(role for _,role,_ in roster),
            repo=self.repo,workspace_root=self.spaces,object_store=self.objects,
            test_argv_by_task={key:['/usr/bin/python3','-c','assert True'] for key,_,_ in roster},
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

    def test_all_eight_specialists_use_bounded_synthetic_runtime(self):
        from harness.scheduler import SPECIALISTS
        import threading
        self.prepare(team=True)
        self.budget.configure_workflow(workflow_id='flow',repository_id=self.args['repository_id'],
                user_turn_id='turn',approved_revisions=self.args['approved_revisions'],
                token_hard=800000,cost_usd_hard=8,max_in_flight=2)
        lock=threading.Lock()
        def worker(request,command,timeout):
            role=request['role']
            self.assertIn(role,SPECIALISTS)
            self.assertEqual(command,['/usr/bin/false'])
            self.assertEqual(request['model'],'fixture/workflow')
            self.assertEqual(request['coordination']['scope'],['fixture_'+role+'.py'])
            with lock:
                self.calls.append(role)
            return {'edits':[{'path':'fixture_'+role+'.py','content':'value = 2\n'}],
                    'summary':'synthetic role fixture',
                    'usage':{'input_tokens':10,'output_tokens':10,'cost_usd':0}}
        result=self.run_flow(max_parallel=2,worker=worker)
        self.assertEqual(result['status'],'DONE',result)
        self.assertEqual(set(result['completed']),{'fixture_'+role for role in SPECIALISTS})
        self.assertEqual(len(self.calls),8)
        self.assertEqual(set(self.calls),SPECIALISTS)
        self.assertEqual(result['provider_mode'],'synthetic')
        for role in SPECIALISTS:
            self.assertEqual((self.repo/('fixture_'+role+'.py')).read_text(),'value = 1\n')
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM evidence').fetchone()[0],24)
            self.assertEqual(db.execute("SELECT count(*) FROM outbox WHERE state='SUCCEEDED'").fetchone()[0],8)
            self.assertEqual(db.execute("SELECT count(*) FROM provider_attempts WHERE kind='PREFLIGHT'").fetchone()[0],1)

    def test_crashed_worker_recovery_fences_effect_and_keeps_budget(self):
        import os
        from harness.runtime.workflow_lifecycle import recover_workflow
        pid=os.fork()
        if pid==0:
            try:
                self.run_flow(worker=lambda *args:os._exit(71))
            finally:
                os._exit(72)
        _,status=os.waitpid(pid,0)
        self.assertEqual(os.waitstatus_to_exitcode(status),71)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT state FROM outbox').fetchone()[0],'DISPATCHING')
            self.assertEqual(db.execute("SELECT count(*) FROM leases WHERE status='ACTIVE'").fetchone()[0],1)
        first=recover_workflow(self.db,workflow_id='flow')
        self.assertEqual(first['status'],'HOLD')
        self.assertEqual(first['active_tasks'],['api'])
        self.assertEqual(first['tasks']['api']['effects'][0]['state'],'UNKNOWN')
        self.assertEqual(first['tasks']['api']['leases'][0]['status'],'SUSPECT')
        self.assertEqual(len(first['tasks']['api']['reservations']),1)
        self.assertEqual(first['tasks']['ui']['status'],'PLANNED')
        self.assertEqual(first,recover_workflow(self.db,workflow_id='flow'))
        with self.assertRaises(ControllerError):
            self.run_flow()

    def test_recovery_cannot_run_inside_active_coordinator(self):
        from harness.runtime.workflow_lifecycle import recover_workflow
        def worker(*args):
            with self.assertRaises(ControllerError):
                recover_workflow(self.db,workflow_id='flow')
            return self.worker(*args)
        result=self.run_flow(worker=worker)
        self.assertEqual(result['status'],'DONE',result)

    def test_overlapping_completed_outputs_are_not_integrated(self):
        from harness.runtime.workflow_lifecycle import fixture_evidence_collector
        from harness.runtime.workflow_integration import integrate_workflow
        self.prepare(overlap=True)
        def worker(request,command,timeout):
            return {'edits':[{'path':'api.py','content':'value = 2\n'}],
                    'summary':'overlapping fixture',
                    'usage':{'input_tokens':10,'output_tokens':10,'cost_usd':0}}
        self.assertEqual(self.run_flow(worker=worker)['status'],'DONE')
        collector=fixture_evidence_collector(self.db,workflow_id='flow')
        root=self.root/'integrated'
        root.mkdir(mode=0o700)
        with self.assertRaisesRegex(ControllerError,'Conflicting workflow output'):
            integrate_workflow(self.db,workflow_id='flow',output_root=root,
                test_argv=['/usr/bin/true'],collector=collector,
                trusted_issuers=frozenset({'trial-host'}))
        self.assertEqual(list(root.iterdir()),[])
        self.assertEqual(_git(self.repo,'rev-parse','HEAD'),self.base)

    def test_local_fixture_evidence_reopens_accepted_host_artifacts(self):
        from harness.runtime.workflow_lifecycle import fixture_evidence_collector
        from harness.runtime.workflow_integration import integrate_workflow
        from harness.verifier import digest_bytes
        self.assertEqual(self.run_flow()['status'],'DONE')
        collector=fixture_evidence_collector(self.db,workflow_id='flow')
        evidence=collector('host:api:relevant_checks')
        self.assertEqual(digest_bytes(evidence.artifact),evidence.record['artifact_digest'])
        state=next(p for p in self.spaces.iterdir() if json.loads((p/'binding.json').read_text())['task_id']=='api')
        artifact=state/'relevant_checks.artifact'
        artifact.write_bytes(b'changed')
        root=self.root/'integrated'
        root.mkdir(mode=0o700)
        with self.assertRaises(ControllerError):
            integrate_workflow(self.db,workflow_id='flow',output_root=root,
                test_argv=['/usr/bin/true'],collector=collector,
                trusted_issuers=frozenset({'trial-host'}))
        self.assertEqual(list(root.iterdir()),[])

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

    def test_shared_workflow_budget_stops_second_task_before_worker(self):
        self.budget.configure_workflow(workflow_id='flow',repository_id=self.args['repository_id'],
                user_turn_id='turn',approved_revisions={'api':0,'ui':0},
                token_hard=100000,cost_usd_hard=2,max_in_flight=1)
        result=self.run_flow()
        self.assertEqual(result['status'],'HOLD')
        self.assertEqual(result['completed'],['api'])
        self.assertEqual(self.calls,['backend'])
        self.assertEqual(self.c.get_task('ui')['status'],'BLOCKED')
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM budget_reservations').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)

    def parallel_budget(self,slots=2):
        self.budget.configure_workflow(workflow_id='flow',repository_id=self.args['repository_id'],
                user_turn_id='turn',approved_revisions={'api':0,'ui':0},
                token_hard=200000,cost_usd_hard=2,max_in_flight=slots)

    def test_parallel_independent_tasks_actually_overlap(self):
        import threading
        self.prepare(independent=True)
        self.parallel_budget()
        barrier=threading.Barrier(2,timeout=15)
        lock=threading.Lock()
        snapshots=[]
        def worker(request,command,timeout):
            with lock:
                self.calls.append(request['role'])
                snapshots.append(request['projectDir'])
            barrier.wait()
            return {'edits':[{'path':'api.py' if request['role']=='backend' else 'ui.py',
                              'content':'value = 2\n'}],'summary':'fixture',
                    'usage':{'input_tokens':10,'output_tokens':10,'cost_usd':0}}
        result=self.run_flow(max_parallel=2,worker=worker)
        self.assertEqual(result['status'],'DONE',result)
        self.assertEqual(result['completed'],['api','ui'])
        self.assertEqual(set(self.calls),{'backend','frontend'})
        self.assertEqual(len(set(snapshots)),2)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM evidence').fetchone()[0],6)
            self.assertEqual(db.execute("SELECT count(*) FROM leases WHERE status IN ('ACTIVE','SUSPECT')").fetchone()[0],0)
            self.assertEqual(db.execute('SELECT active_json FROM workflow_active_batches').fetchone()[0],'[]')
        self.assertEqual((self.repo/'api.py').read_text(),'value = 1\n')

    def test_parallel_profile_preserves_dependency_barrier(self):
        self.parallel_budget()
        result=self.run_flow(max_parallel=2)
        self.assertEqual(result['status'],'DONE',result)
        self.assertEqual(self.calls,['backend','frontend'])

    def test_overlapping_paths_are_serialized_not_raced(self):
        import threading
        self.prepare(independent=True,overlap=True)
        self.parallel_budget()
        lock=threading.Lock()
        def worker(request,command,timeout):
            self.assertTrue(lock.acquire(blocking=False))
            try:
                self.calls.append(request['role'])
                with sqlite3.connect(self.db) as db:
                    active=json.loads(db.execute('SELECT active_json FROM workflow_active_batches').fetchone()[0])
                self.assertEqual(len(active),1)
                return {'edits':[{'path':'api.py','content':'value = 2\n'}],
                        'summary':'fixture','usage':{'input_tokens':10,'output_tokens':10,'cost_usd':0}}
            finally:
                lock.release()
        result=self.run_flow(max_parallel=2,worker=worker)
        self.assertEqual(result['status'],'DONE',result)
        self.assertEqual(self.calls,['backend','frontend'])

    def test_parallel_requires_aggregate_budget_and_complete_sandbox_binding(self):
        with self.assertRaises(ControllerError):
            self.run_flow(max_parallel=2)
        self.parallel_budget(slots=1)
        with self.assertRaises(ControllerError):
            self.run_flow(max_parallel=2)
        for changes in (dict(max_parallel=True),dict(max_parallel=9),
                        dict(max_parallel=2,sandbox_probe=None),
                        dict(max_parallel=2,sandbox_run=None)):
            with self.assertRaises((ValueError,ControllerError)):
                self.run_flow(**changes)
        self.assertEqual(self.calls,[])
        self.assertEqual(list(self.spaces.iterdir()),[])


    def test_parallel_rejects_mixed_sandbox_binding_with_valid_budget(self):
        self.prepare(independent=True)
        self.parallel_budget()
        for change in (dict(sandbox_probe=None),dict(sandbox_run=None),
                       dict(sandbox_probe=False,sandbox_run=False)):
            with self.assertRaises(ControllerError):
                self.run_flow(max_parallel=2,**change)
        self.assertEqual(self.calls,[])
        self.assertEqual(list(self.spaces.iterdir()),[])
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)

    def test_live_parallel_workflow_real_bubblewrap(self):
        import os
        import threading
        from harness.isolation.backend import BubblewrapBackend
        status=BubblewrapBackend().probe()
        if not status['available']:
            if os.environ.get('POTATO_REQUIRE_LIVE_WORKFLOW')=='1':
                self.fail('Required live Bubblewrap unavailable: '+status['reason'])
            self.skipTest('Live Bubblewrap unavailable: '+status['reason'])
        self.prepare(independent=True)
        self.parallel_budget()
        barrier=threading.Barrier(2,timeout=15)
        def worker(request,command,timeout):
            role=request['role']
            barrier.wait()
            return {'edits':[{'path':'api.py' if role=='backend' else 'ui.py',
                              'content':'value = 2\n'}],'summary':'fixture',
                    'usage':{'input_tokens':10,'output_tokens':10,'cost_usd':0}}
        code="""from pathlib import Path
import os, resource, sys, time
own, other = sys.argv[1:]
assert Path(own).read_text() == 'value = 2\\n'
assert Path(other).read_text() == 'value = 1\\n'
assert not Path('/etc/passwd').exists()
assert resource.getrlimit(resource.RLIMIT_NOFILE)[0] <= 64
start=time.monotonic_ns()
time.sleep(2)
print(os.readlink('/proc/self/ns/net'),start,time.monotonic_ns())
"""
        tests={key:['/usr/bin/python3','-c',code,key+'.py',other+'.py']
               for key,other in [('api','ui'),('ui','api')]}
        result=self.run_flow(max_parallel=2,worker=worker,
                             sandbox_probe=None,sandbox_run=None,test_argv_by_task=tests)
        self.assertEqual(result['status'],'DONE',result)
        self.assertEqual(result['provider_mode'],'synthetic')
        self.assertEqual(result['completed'],['api','ui'])
        host_network=os.readlink('/proc/self/ns/net')
        spans=[]
        for directory in self.spaces.iterdir():
            artifact=json.loads((directory/'relevant_checks.artifact').read_text())
            self.assertEqual(artifact['returncode'],0,artifact)
            self.assertFalse(artifact['timed_out'])
            network,start,end=artifact['stdout'].strip().split()
            self.assertNotEqual(network,host_network)
            spans.append((network,int(start),int(end)))
        self.assertEqual(len(spans),2)
        self.assertNotEqual(spans[0][0],spans[1][0])
        self.assertLess(max(s[1] for s in spans),min(s[2] for s in spans),
                        'Real workflow sandbox payloads must overlap')
        for name in ('api.py','ui.py'):
            self.assertEqual((self.repo/name).read_text(),'value = 1\n')
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM evidence').fetchone()[0],6)
            self.assertEqual(db.execute("SELECT count(*) FROM leases WHERE status IN ('ACTIVE','SUSPECT')").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM outbox WHERE state='SUCCEEDED'").fetchone()[0],2)
            self.assertEqual(db.execute('SELECT active_json FROM workflow_active_batches').fetchone()[0],'[]')

    def test_workflow_deadline_rejects_invalid_bounds_before_claim(self):
        for limit in (None,True,0,-1,float('nan'),float('inf'),3601):
            with self.assertRaises(ControllerError):
                self.run_flow(workflow_wall_time_s=limit)
        self.assertEqual(self.calls,[])
        self.assertEqual(list(self.spaces.iterdir()),[])

    def test_workflow_deadline_caps_worker_and_sandbox(self):
        from unittest.mock import patch
        now=[10.]
        observed=[]
        def worker(request,command,timeout):
            observed.append(timeout)
            if request['role']=='backend':
                now[0]=12.
            return self.worker(request,command,timeout)
        def sandbox(*args,**kwargs):
            observed.append(kwargs['timeout'])
            return {'returncode':0,'stdout':'ok','stderr':'','timed_out':False}
        with patch('harness.runtime.workflow.monotonic',side_effect=lambda:now[0]):
            result=self.run_flow(workflow_wall_time_s=8,worker=worker,sandbox_run=sandbox)
        self.assertEqual(result['status'],'DONE',result)
        self.assertEqual(observed,[8.,6.,6.,6.])

    def test_parallel_late_proposals_reconcile_without_publication(self):
        from unittest.mock import patch
        import threading
        self.prepare(independent=True)
        self.parallel_budget()
        now=[10.]
        barrier=threading.Barrier(2,action=lambda:now.__setitem__(0,12.),timeout=15)
        def worker(request,command,timeout):
            self.assertEqual(timeout,2.)
            barrier.wait()
            return {'edits':[{'path':'api.py' if request['role']=='backend' else 'ui.py',
                              'content':'value = 2\n'}],'summary':'late fixture',
                    'usage':{'input_tokens':10,'output_tokens':10,'cost_usd':0}}
        with patch('harness.runtime.workflow.monotonic',side_effect=lambda:now[0]):
            result=self.run_flow(max_parallel=2,workflow_wall_time_s=2,worker=worker)
        self.assertEqual(result['status'],'HOLD',result)
        self.assertEqual(result['reason'],'WORKFLOW_DEADLINE')
        self.assertEqual(result['active_tasks'],['api','ui'])
        self.assertEqual(result['completed'],[])
        for key in ('api','ui'):
            self.assertEqual(self.c.get_task(key)['status'],'BLOCKED')
            self.assertEqual(Outbox(self.db).unresolved(key),[])
        for directory in self.spaces.iterdir():
            self.assertFalse((directory/'result.json').exists())
            self.assertEqual((directory/'workspace'/'api.py').read_text(),'value = 1\n')
            self.assertEqual((directory/'workspace'/'ui.py').read_text(),'value = 1\n')
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM outbox WHERE state='SUCCEEDED'").fetchone()[0],2)
            self.assertEqual(db.execute('SELECT count(*) FROM budget_reservations WHERE settlement IS NULL').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM evidence').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT expired FROM workflow_deadlines').fetchone()[0],1)
        with self.assertRaises(ControllerError):
            self.run_flow(max_parallel=2)

    def test_parallel_unknown_effect_holds_after_already_admitted_batch(self):
        import threading
        self.prepare(independent=True)
        self.parallel_budget()
        barrier=threading.Barrier(2,timeout=15)
        def worker(request,command,timeout):
            role=request['role']
            barrier.wait()
            if role=='backend':
                raise RuntimeError('synthetic uncertain outcome')
            return {'edits':[{'path':'ui.py','content':'value = 2\n'}],
                    'summary':'fixture','usage':{'input_tokens':10,'output_tokens':10,'cost_usd':0}}
        result=self.run_flow(max_parallel=2,worker=worker)
        self.assertEqual(result['status'],'HOLD',result)
        self.assertEqual(result['completed'],['ui'])
        self.assertEqual(result['active_tasks'],['api'])
        self.assertEqual(len(Outbox(self.db).unresolved('api')),1)
        self.assertEqual(Outbox(self.db).unresolved('ui'),[])
        with self.assertRaises(ControllerError):
            self.run_flow(max_parallel=2,worker=worker)
