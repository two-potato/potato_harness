"""Actual v2 SDK subprocess through runtime; only sandbox execution is a test seam."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from harness.runtime import init, run, halo

def check(adapter):
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)/'trial'
        subprocess.run([sys.executable,'tools/create_trial.py','--directory',str(root),'--adapter',adapter],check=True)
        cfg=json.loads((root/'config.json').read_text())
        state=root/'state'
        init(cfg,state)
        result=run(state,sandbox_probe=lambda:{'available':True,'reason':'CI injected sandbox seam'},
                   sandbox_run=lambda *a,**k:{'returncode':0,'stdout':'CI sandbox seam; no source execution','stderr':'','timed_out':False})
        assert result['state']=='DONE',result['reason']
        assert result['provider_mode']=='synthetic'
        assert not result['unresolved_effects']
        assert result['grant']['status']=='REVOKED'
        assert halo(state)['status']=='HOLD'
        output=json.loads((root/'result/result.json').read_text())
        assert output['adapter']==adapter and output['provider_mode']=='synthetic'
        assert (root/'repo/calculation.py').read_text().endswith('unit_cents + quantity\n')
        assert (state/'workspace/calculation.py').read_text().endswith('unit_cents * quantity\n')
        print(json.dumps({'status':'PASS','layer':'actual-v2-worker-runtime','adapter':adapter,'synthetic_provider':True,'sandbox':'injected-seam'}))

def check_attached():
    import sqlite3
    from harness.runtime.attached_trial import TEST_IDS
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)/'trial'
        subprocess.run([sys.executable,'tools/create_trial.py','--directory',str(root),
                        '--adapter','opencode-v2-attached-free-fixture'],check=True)
        cfg=json.loads((root/'config.json').read_text())
        state=root/'state';init(cfg,state)
        # Actual worker, actual SQLite, actual Bubblewrap, injected server only.
        result=run(state,confirm_attached_trial=True)
        assert result['state']=='DONE',result['reason']
        assert result['provider_mode']=='synthetic'
        assert result['executed_test_ids']==list(TEST_IDS)
        assert not result['unresolved_effects']
        assert result['grant']['status']=='REVOKED'
        with sqlite3.connect(state/'state.db') as db:
            assert db.execute('SELECT state FROM attached_worker_handoffs').fetchall()==[('CONSUMED',)]
            assert db.execute('SELECT state FROM outbox').fetchall()==[('SUCCEEDED',)]
        with sqlite3.connect(state/'attached-controlled-ledger.sqlite3') as db:
            assert db.execute('SELECT state FROM attached_attempts').fetchall()==[('VALIDATED',)]
            assert db.execute('SELECT role,state FROM attached_stages ORDER BY role').fetchall()==[
                ('backend','VALIDATED'),('valera-ceo','VALIDATED')]
        assert (state/'workspace/calculation.py').read_text().endswith('unit_cents * quantity\n')
        print('PASS: attached controlled transport, actual runtime and three actual Bubblewrap tests; zero external prompts')

def main():
    check('opencode-v2-fixture')
    check('opencode-v2-native-free-fixture')
    check_attached()

if __name__=='__main__':main()
