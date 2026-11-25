"""Actual v2 SDK subprocess through runtime; only sandbox execution is a test seam."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from harness.runtime import init, run, halo

def main():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)/'trial'
        subprocess.run([sys.executable,'tools/create_trial.py','--directory',str(root),'--adapter','opencode-v2-fixture'],check=True)
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
        assert output['adapter']=='opencode-v2-fixture' and output['provider_mode']=='synthetic'
        assert (root/'repo/calculation.py').read_text().endswith('unit_cents + quantity\n')
        assert (state/'workspace/calculation.py').read_text().endswith('unit_cents * quantity\n')
        print(json.dumps({'status':'PASS','layer':'actual-v2-worker-runtime','synthetic_provider':True,'sandbox':'injected-seam'}))

if __name__=='__main__':main()
