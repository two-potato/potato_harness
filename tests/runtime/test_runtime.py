import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from harness.runtime import init,run,status,recover,halo


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.repo=self.root/'source';self.repo.mkdir()
        (self.repo/'calc.py').write_text('value = 1\n')
        def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(self.repo),*args],stderr=subprocess.DEVNULL).decode().strip()
        git('init');git('add','calc.py');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','base')
        self.config={'repo':str(self.repo),'base_sha':git('rev-parse','HEAD'),'model':'test/fixture','worker_command':['/usr/bin/false'],'scope':['calc.py'],'test_argv':['/usr/bin/python3','-c','assert True'],'objective':'Configured fixture checks pass','budget':{'tokens':100000,'cost_usd':1,'estimate_cost_usd':.5,'wall_time_s':60},'output':str(self.root/'output')}
        self.state=self.root/'state';init(self.config,self.state)
    def worker(self,request,command,timeout):
        self.assertNotEqual(request['projectDir'],str(self.state/'workspace'))
        return {'edits':[{'path':'calc.py','content':'value = 2\n'}],'summary':'fixture replacement','usage':{'input_tokens':100,'output_tokens':10,'cost_usd':.01}}
    def test_integrated_host_fixture(self):
        result=run(self.state,worker=self.worker,sandbox_probe=lambda:{'available':True,'reason':'injected test seam'},sandbox_run=lambda *a,**k:{'returncode':0,'stdout':'fixture test','stderr':'','timed_out':False})
        self.assertEqual(result['state'],'DONE',result['reason'])
        self.assertEqual(result['task_status'],'DONE')
        self.assertEqual((self.repo/'calc.py').read_text(),'value = 1\n')
        self.assertEqual(len(json.loads((self.state/'evidence.json').read_text())),3)
        self.assertEqual(halo(self.state)['status'],'HOLD')
        with self.assertRaises(ValueError):run(self.state,worker=self.worker)
    def test_marketplace_profile_reaches_executor_as_mandatory_policy(self):
        state = self.root / 'marketplace-state'
        init(dict(self.config, domain_profile='marketplace'), state)

        def worker(request, command, timeout):
            policy = next(
                item for item in json.loads(request['prompt'])['instructions']
                if item['name'] == 'policy'
            )
            self.assertTrue(policy['mandatory'])
            self.assertIn('Marketplace engineering profile', policy['text'])
            return {'edits': [{'path': 'calc.py', 'content': 'value = 2\n'}],
                    'summary': 'fixture', 'usage': {'input_tokens': 100,
                    'output_tokens': 10, 'cost_usd': 0.01}}

        result = run(state, worker=worker, sandbox_probe=lambda: {'available': True},
                     sandbox_run=lambda *args, **kwargs: {'returncode': 0,
                     'stdout': 'ok', 'stderr': '', 'timed_out': False})
        self.assertEqual(result['state'], 'DONE', result['reason'])
        with self.assertRaisesRegex(ValueError, 'Unknown domain profile'):
            init(dict(self.config, domain_profile='../custom'), self.root / 'invalid')

    def test_v2_profile_selects_pinned_worker_and_marks_fixture_provenance(self):
        from harness.runtime import _config, _worker_command
        from harness.controller import ROOT
        base={k:v for k,v in self.config.items() if k!='worker_command'}
        config=dict(base,adapter='opencode-v2-fixture',model='fixture/test',
                    scope=['calculation.py'],objective='Fix subtotal so it multiplies integer unit price by quantity. Preserve function signature.')
        self.assertEqual(_worker_command(_config(config))[-2:],
                         [str(ROOT/'integrations/opencode-v2/src/worker.mjs'),'fixture'])
        for changed in (dict(adapter='unknown'),dict(model='opencode/minimax-m3'),
                        dict(worker_command=['/bin/sh']),dict(jev_provider='opencode')):
            with self.assertRaises(ValueError): _config(dict(config,**changed))
        live=dict(config,adapter='opencode-v2-console',model='opencode/minimax-m3')
        with self.assertRaises(ValueError): _config(live)
        live['provider_budget_confirmed']=True
        self.assertEqual(_worker_command(_config(live))[-1],'console')
        with self.assertRaises(ValueError): _config(dict(live,model='opencode/mimo-v2.6-flash-free'))
        default={k:v for k,v in live.items() if k!='adapter'}
        self.assertEqual(_config(default)['adapter'],'opencode-v2-console')
        self.assertEqual(_worker_command(_config(default)),[str(ROOT/'integrations/opencode-v2/node_modules/.bin/bun'),str(ROOT/'integrations/opencode-v2/src/worker.mjs'),'console'])
        self.assertEqual(_worker_command(_config(self.config)),['/usr/bin/false'])
        with self.assertRaises(ValueError): _config(dict(live,adapter='opencode-v1'))
        with self.assertRaises(ValueError): _config(base)

    def test_native_free_fixture_profile_and_live_gate(self):
        from harness.runtime import _config, _worker_command
        base={k:v for k,v in self.config.items() if k!='worker_command'}
        cfg=dict(base,adapter='opencode-v2-native-free-fixture',model='opencode/potato-runtime-fixture-free',
                 scope=['calculation.py'],objective='Fix subtotal so it multiplies integer unit price by quantity. Preserve function signature.')
        self.assertEqual(_worker_command(_config(cfg))[-1],'native-free-fixture')
        for patch in (dict(adapter='opencode-v2-native-free'),dict(model='opencode/beam-free'),
                      dict(provider_budget_confirmed=True),dict(jev_provider='opencode'),dict(scope=['other.py'])):
            with self.assertRaises(ValueError): _config(dict(cfg,**patch))
        with self.assertRaisesRegex(ValueError,'live activation HOLD'):
            _config(dict(cfg,adapter='opencode-v2-native-free',model='opencode/beam-free'))
        with self.assertRaises(KeyError): _worker_command(dict(cfg,adapter='opencode-v2-native-free'))

    def test_attached_trial_zero_budget_and_no_dispatch_without_explicit_confirmation(self):
        from harness.runtime import _config, _worker_command
        root=self.root/'attached-trial'
        subprocess.run([__import__('sys').executable,'tools/create_trial.py','--directory',str(root),
                        '--adapter','opencode-v2-attached-free'],check=True)
        cfg=json.loads((root/'config.json').read_text())
        self.assertEqual(cfg['budget']['cost_usd'],0)
        self.assertEqual(cfg['budget']['estimate_cost_usd'],0)
        self.assertEqual(_worker_command(_config(cfg))[-1],'attached-free')
        for patch in (dict(model='openrouter/openrouter/free'),dict(scope=['other.py']),
                      dict(test_argv=['/usr/bin/true']),dict(provider_budget_confirmed=True),
                      dict(budget=dict(cfg['budget'],cost_usd=1)),dict(domain_profile='marketplace')):
            with self.assertRaises(ValueError):_config(dict(cfg,**patch))
        state=root/'state';init(cfg,state)
        with self.assertRaisesRegex(ValueError,'explicit local run confirmation'):
            run(state)
        self.assertEqual(status(state)['state'],'INITIALIZED')
        self.assertEqual(status(state)['unresolved_effects'],[])
        with self.assertRaisesRegex(ValueError,'source mismatch'):
            (state/'workspace'/'calculation.py').write_text('different')
            from harness.runtime.attached_trial import verify_workspace
            verify_workspace(state/'workspace')

    def test_native_fixture_uncertainty_retains_outbox_and_never_replays(self):
        import sqlite3
        root=self.root/'native-trial'
        subprocess.run([__import__('sys').executable,'tools/create_trial.py','--directory',str(root),'--adapter','opencode-v2-native-free-fixture'],check=True)
        state=root/'state';init(json.loads((root/'config.json').read_text()),state)
        calls=[]
        def rate_limit(request,command,timeout):
            self.assertEqual(command[-1],'native-free-fixture')
            self.assertEqual(request['token_allowance'],json.loads((root/'config.json').read_text())['budget']['tokens'])
            calls.append(request['model'])
            raise RuntimeError('synthetic provider rate limit')
        result=run(state,worker=rate_limit,sandbox_probe=lambda:{'available':True})
        self.assertEqual(result['state'],'HOLD')
        self.assertEqual(result['provider_mode'],'synthetic')
        self.assertEqual(len(result['unresolved_effects']),1)
        self.assertEqual(result['grant']['status'],'REVOKED')
        self.assertEqual((state/'workspace/calculation.py').read_text().splitlines()[-1],'    return unit_cents + quantity')
        with sqlite3.connect(state/'state.db') as db:
            self.assertEqual(db.execute('SELECT state FROM outbox').fetchone()[0],'UNKNOWN')
            self.assertEqual(db.execute('SELECT count(*) FROM budget_reservations WHERE settlement IS NULL').fetchone()[0],1)
        self.assertEqual(recover(state)['state'],'HOLD')
        with self.assertRaises(ValueError):run(state,worker=rate_limit)
        self.assertEqual(calls,['opencode/potato-runtime-fixture-free'])
        self.assertEqual(halo(state)['status'],'HOLD')

    def test_native_offline_guard_and_no_publication(self):
        from unittest.mock import patch
        from harness.runtime import _config, _worker_command
        for isolated in (False, True):
            root=self.root/('offline-'+str(isolated))
            subprocess.run([__import__('sys').executable,'tools/create_trial.py','--directory',str(root),'--adapter','opencode-v2-native-free-offline','--model','opencode/beam-free'],check=True)
            cfg=json.loads((root/'config.json').read_text())
            self.assertEqual(_worker_command(_config(cfg))[-1],'native-free-offline')
            for change in (dict(adapter='opencode-v2-native-free'),dict(model='opencode/paid'),
                           dict(model='opencode/potato-runtime-fixture-free'),dict(provider_budget_confirmed=True)):
                with self.assertRaises(ValueError):_config(dict(cfg,**change))
            state=root/'state';init(cfg,state)
            calls=[]
            def worker(*args):
                calls.append(1)
                return {'edits':[{'path':'calculation.py','content':'unexpected'}],'summary':'unexpected','usage':{'input_tokens':1,'output_tokens':1,'cost_usd':0}}
            with patch('harness.runtime.require_offline_network',side_effect=None if isolated else ValueError('Offline network namespace required')):
                result=run(state,worker=worker,sandbox_probe=lambda:{'available':True})
            self.assertEqual(result['state'],'HOLD')
            self.assertEqual(result['provider_mode'],'offline')
            self.assertEqual(len(calls),int(isolated))
            self.assertEqual(len(result['unresolved_effects']),int(isolated))
            import sqlite3
            with sqlite3.connect(state/'state.db') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM budget_reservations').fetchone()[0],int(isolated))
            self.assertFalse((state/'result.json').exists())
            self.assertIn('unit_cents + quantity',(state/'workspace/calculation.py').read_text())
            self.assertEqual(halo(state)['status'],'HOLD')
            if isolated:self.assertEqual(result['grant']['status'],'REVOKED')

    def test_old_initialized_state_cannot_dispatch_after_upgrade(self):
        config=json.loads((self.state/'config.json').read_text())
        config.pop('worker_command')
        (self.state/'config.json').write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError,'cannot migrate in place'):
            run(self.state,worker=lambda *a:self.fail('Old state was dispatched'))
        self.assertEqual(status(self.state)['state'],'INITIALIZED')
        self.assertEqual(recover(self.state)['state'],'HOLD')

    def test_console_missing_key_blocks_before_reservation(self):
        from unittest.mock import patch
        import sqlite3
        state=self.root/'console-state'
        init(dict({k:v for k,v in self.config.items() if k!='worker_command'},adapter='opencode-v2-console',model='opencode/minimax-m3',provider_budget_confirmed=True),state)
        with patch.dict('os.environ',{},clear=True):
            result=run(state,worker=lambda *a:self.fail('Provider dispatched without key'),
                       sandbox_probe=lambda:{'available':True})
        self.assertEqual(result['state'],'HOLD')
        self.assertIn('key missing before dispatch',result['reason'])
        self.assertEqual(result['unresolved_effects'],[])
        with sqlite3.connect(state/'state.db') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM budget_reservations').fetchone()[0],0)

    def test_console_budget_is_host_bound_and_not_model_generated(self):
        from unittest.mock import patch
        state=self.root/'console-budget-state'
        init(dict({k:v for k,v in self.config.items() if k!='worker_command'},adapter='opencode-v2-console',model='opencode/minimax-m3',provider_budget_confirmed=True),state)
        def worker(request,command,timeout):
            self.assertEqual(request['provider_budget'],{'tokens':100000,'cost_usd':.5})
            self.assertEqual(command[-1],'console')
            self.assertNotIn('synthetic-test-key',json.dumps(request))
            return self.worker(request,command,timeout)
        with patch.dict('os.environ',{'OPENCODE_API_KEY':'synthetic-test-key'}):
            result=run(state,worker=worker,sandbox_probe=lambda:{'available':True},
                       sandbox_run=lambda *a,**k:{'returncode':0,'stdout':'ok','stderr':'','timed_out':False})
        self.assertEqual(result['state'],'DONE',result['reason'])

    def test_missing_sandbox_never_calls_provider(self):
        def forbidden(*a):self.fail('Provider called without sandbox')
        result=run(self.state,worker=forbidden,sandbox_probe=lambda:{'available':False,'reason':'fixture unavailable'})
        self.assertEqual(result['state'],'HOLD');self.assertIn('Sandbox unavailable',result['reason'])
    def test_provider_uncertainty_never_replays(self):
        def crash(*a):raise RuntimeError('fixture interrupted provider')
        result=run(self.state,worker=crash,sandbox_probe=lambda:{'available':True})
        self.assertEqual(result['state'],'HOLD');self.assertEqual(len(result['unresolved_effects']),1)
        self.assertEqual(recover(self.state)['state'],'HOLD')
        with self.assertRaises(ValueError):run(self.state,worker=self.worker)
    def test_unknown_cost_retains_reservation(self):
        def unknown(*a):
            response=self.worker(*a);response['usage']['cost_usd']=None;return response
        result=run(self.state,worker=unknown,sandbox_probe=lambda:{'available':True})
        self.assertEqual(result['state'],'HOLD');self.assertIn('cost unknown',result['reason'])
        import sqlite3
        with sqlite3.connect(self.state/'state.db') as db:self.assertEqual(db.execute('SELECT count(*) FROM budget_reservations WHERE settlement IS NULL').fetchone()[0],1)
    def test_failed_tests_block_completion(self):
        result=run(self.state,worker=self.worker,sandbox_probe=lambda:{'available':True},sandbox_run=lambda *a,**k:{'returncode':1,'stdout':'failure','stderr':'','timed_out':False})
        self.assertEqual(result['state'],'HOLD');self.assertNotEqual(result['task_status'],'DONE')
    def test_unscoped_edit_rejected(self):
        def invalid(*args):
            response=self.worker(*args);response['edits'][0]['path']='../escape';return response
        result=run(self.state,worker=invalid,sandbox_probe=lambda:{'available':True})
        self.assertEqual(result['state'],'HOLD');self.assertIn('unscoped',result['reason'])
    def test_highrisk_scope_rejected(self):
        config=dict(self.config,scope=['auth/password.py'])
        with self.assertRaises(ValueError):init(config,self.root/'other-state')
    def test_actual_usage_overrun_is_persisted_and_blocks(self):
        def expensive(*args):
            response=self.worker(*args);response['usage'].update(input_tokens=150000,output_tokens=100000,cost_usd=25);return response
        result=run(self.state,worker=expensive,sandbox_probe=lambda:{'available':True})
        self.assertEqual(result['state'],'HOLD');self.assertIn('exceeded',result['reason'])
        self.assertEqual((self.state/'workspace/calc.py').read_text(),'value = 1\n')
        import sqlite3
        with sqlite3.connect(self.state/'state.db') as db:
            self.assertEqual(db.execute('SELECT used_tokens,used_cost FROM budgets').fetchone(),(250000,25))
    def test_real_git_target_and_export(self):
        result=run(self.state,worker=self.worker,sandbox_probe=lambda:{'available':True},sandbox_run=lambda *a,**k:{'returncode':0,'stdout':'ok','stderr':'','timed_out':False})
        self.assertEqual(result['state'],'DONE',result['reason'])
        data=json.loads((self.state/'result.json').read_text())
        kind=subprocess.check_output(['/usr/bin/git','-C',str(self.state/'integration-repo'),'cat-file','-t',data['target_commit']['value']]).decode().strip()
        self.assertEqual(kind,'commit')
        self.assertTrue((Path(self.config['output'])/'result.json').is_file())
        self.assertTrue(list((Path(self.config['output'])/'artifacts').iterdir()))
    def test_total_wall_deadline_blocks_after_slow_provider(self):
        import time
        config=json.loads((self.state/'config.json').read_text());config['budget']['wall_time_s']=.02
        (self.state/'config.json').write_text(json.dumps(config))
        def slow(*args):time.sleep(.04);return self.worker(*args)
        result=run(self.state,worker=slow,sandbox_probe=lambda:{'available':True})
        self.assertEqual(result['state'],'HOLD');self.assertIn('wall time',result['reason'])
    def test_export_ignore_cannot_hide_regression_inputs(self):
        (self.repo/'.gitattributes').write_text('regression.py export-ignore\ncalc.py export-subst\n')
        (self.repo/'regression.py').write_text('raise AssertionError("must remain visible")\n')
        (self.repo/'calc.py').chmod(0o755)
        subprocess.check_call(['/usr/bin/git','-C',str(self.repo),'add','.'],stdout=subprocess.DEVNULL)
        subprocess.check_call(['/usr/bin/git','-C',str(self.repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','attrs'],stdout=subprocess.DEVNULL)
        config=dict(self.config,base_sha=subprocess.check_output(['/usr/bin/git','-C',str(self.repo),'rev-parse','HEAD']).decode().strip(),output=str(self.root/'other-output'))
        other=self.root/'other-state';init(config,other)
        self.assertTrue((other/'workspace/regression.py').is_file())
        self.assertTrue((other/'workspace/calc.py').stat().st_mode & 0o111)
        result=run(other,worker=self.worker,sandbox_probe=lambda:{'available':True},sandbox_run=lambda *a,**k:{'returncode':0,'stdout':'fixture','stderr':'','timed_out':False})
        self.assertEqual(result['state'],'DONE',result['reason'])
        target=json.loads((other/'result.json').read_text())['target_commit']['value']
        for name in ('regression.py','calc.py','.gitattributes'):
            blob=subprocess.check_output(['/usr/bin/git','-C',str(other/'integration-repo'),'show',target+':'+name])
            self.assertEqual(blob,(other/'workspace'/name).read_bytes())
    def test_halo_explicit_splits_reject_overlap(self):
        row={'trace_id':'fixture-trace','status':'PASS','checks':['fixture'],'bindings':{'policy':'fixture'},'optional_detail':'fixture detail'}
        paths=[]
        for name in ('train','eval','holdout'):
            path=self.root/(name+'.json');path.write_text(json.dumps([row]));paths.append(path)
        result=halo(self.state,train=paths[0],evaluation=paths[1],holdout=paths[2])
        self.assertEqual(result['status'],'REJECTED')
