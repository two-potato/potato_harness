#!/usr/bin/env python3
"""Prepare pinned local runtimes and write a truthful pre-trial environment report."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT=Path(__file__).resolve().parents[1]
INTEGRATION=ROOT/'integrations/opencode-v2'

def call(args,cwd=ROOT,env=None):
    env=dict(os.environ if env is None else env)
    for secret in ('OPENCODE_API_KEY','TYPESAFE_API_KEY'):env.pop(secret,None)
    env.update(DO_NOT_TRACK='1')
    result=subprocess.run([str(x) for x in args],cwd=cwd,env=env,capture_output=True,text=True,timeout=180)
    if result.returncode:raise RuntimeError('Preparation command failed: '+str(args[0])+'\n'+result.stderr[-2000:])
    return (result.stdout+'\n'+result.stderr).strip()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--install',action='store_true');p.add_argument('--verify',action='store_true')
    p.add_argument('--output',type=Path,default=ROOT/'.runtime/trial-readiness.json')
    args=p.parse_args()
    if sys.version_info<(3,12):raise SystemExit('Python 3.12+ is required')
    python=ROOT/'.venv-demo/bin/python'
    if args.install:
        if not python.exists():venv.EnvBuilder(with_pip=True).create(python.parent.parent)
        call([python,'-m','pip','install','-r',ROOT/'requirements-validation.txt',
              '-r',ROOT/'blueprints/marketplace/requirements-dev.txt'])
        call(['npm','ci','--ignore-scripts','--no-audit','--no-fund'],cwd=INTEGRATION)
        call(['node','node_modules/bun/install.js'],cwd=INTEGRATION)
    report={'created_at':datetime.now(timezone.utc).isoformat(),'checks':{},'inference':'NOT_RUN','activation':'NOT_AUTHORIZED'}
    c=report['checks']
    for name,command,cwd,expected in [('python',[python,'--version'],ROOT,None),('opencode_sdk',['node','-p',"require('./node_modules/@opencode/sdk/package.json').version"],INTEGRATION,'2.4.1'),('bun',[INTEGRATION/'node_modules/.bin/bun','--version'],INTEGRATION,'1.4.4')]:
        try:
            version=call(command,cwd=cwd)
            if expected is not None and version!=expected:raise RuntimeError('Pinned runtime version mismatch: '+name)
            c[name]={'status':'PASS','version':version}
        except (OSError,RuntimeError) as e:c[name]={'status':'BLOCKED','reason':str(e)}
    try:
        data=call([python,'-c','import json;from harness.isolation import probe;print(json.dumps(probe()))'])
        isolation=json.loads(data);c['isolation']={'status':'PASS' if isolation['available'] else 'BLOCKED_HOST',**isolation}
    except Exception as e:c['isolation']={'status':'BLOCKED_HOST','reason':str(e)}
    c['credentials']={'status':'CONFIGURED' if os.environ.get('OPENCODE_API_KEY') else 'MISSING_KEY','opencode':bool(os.environ.get('OPENCODE_API_KEY')),'typesafe':bool(os.environ.get('TYPESAFE_API_KEY'))}
    if args.verify:
        for name,command,cwd in [('python_suite',[python,'-m','unittest','discover','-s','tests','-v'],ROOT),('contracts',[python,'tools/validate_pack.py'],ROOT),('v2_unit',['npm','test'],INTEGRATION),('v2_sdk_fixture',[INTEGRATION/'node_modules/.bin/bun','src/smoke.mjs'],INTEGRATION),('manifest',[python,'tools/verify_manifest.py'],ROOT)]:
            env=dict(os.environ);env['PATH']=str(INTEGRATION/'node_modules/.bin')+os.pathsep+env.get('PATH',os.defpath)
            try:c[name]={'status':'PASS','output':call(command,cwd=cwd,env=env)[-3000:]}
            except Exception as e:c[name]={'status':'FAIL','reason':str(e)}
    blockers=[name for name,value in c.items() if value['status'] in ('BLOCKED','BLOCKED_HOST','FAIL')]
    report['readiness']='BLOCKED_HOST_OR_CODE' if blockers else 'READY_FOR_FIXTURE_NOT_CERTIFIED' if c['credentials']['status']=='MISSING_KEY' else 'READY_FOR_TRIALS_NOT_CERTIFIED'
    report['blockers']=blockers
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 1 if blockers else 0

if __name__=='__main__':raise SystemExit(main())
