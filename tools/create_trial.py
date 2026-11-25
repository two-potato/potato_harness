#!/usr/bin/env python3
"""Create a clean local bug-repair repository and pinned runtime config."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);p.add_argument('--model');p.add_argument('--adapter',choices=('opencode-v2-fixture','opencode-v2-console'));p.add_argument('--confirm-provider-budget',action='store_true');a=p.parse_args()
    if a.adapter is None:a.adapter='opencode-v2-console' if a.model and a.model!='fixture/test' else 'opencode-v2-fixture'
    if a.adapter=='opencode-v2-fixture':
        if a.model not in (None,'fixture/test') or a.confirm_provider_budget:p.error('Fixture uses fixture/test without provider budget')
        a.model='fixture/test'
    elif a.adapter=='opencode-v2-console':
        if a.model!='opencode/minimax-m3' or not a.confirm_provider_budget:p.error('Explicit paid model and confirmed provider budget required')

    root=a.directory.absolute();root.mkdir(parents=True,exist_ok=False);repo=root/'repo';repo.mkdir();(repo/'tests').mkdir()
    (repo/'calculation.py').write_text('def subtotal(unit_cents, quantity):\n    return unit_cents + quantity\n')
    (repo/'tests/test_calculation.py').write_text('import unittest\nfrom calculation import subtotal\nclass CalculationTests(unittest.TestCase):\n    def test_total(self): self.assertEqual(subtotal(1250,3),3750)\n    def test_zero(self): self.assertEqual(subtotal(1250,0),0)\n    def test_one(self): self.assertEqual(subtotal(1250,1),1250)\n')
    def git(*args):return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','-C',str(repo),*args],text=True).strip()
    git('init','-b','main');git('add','.');git('-c','user.name=Potato Trial','-c','user.email=trial@example.invalid','commit','-m','fixture: subtotal bug')
    config={'repo':str(repo),'base_sha':git('rev-parse','HEAD'),'model':a.model,'scope':['calculation.py'],'test_argv':['/usr/bin/python3','-B','-m','unittest','discover','-s','tests','-v'],'objective':'Fix subtotal so it multiplies integer unit price by quantity. Preserve function signature.','budget':{'tokens':100000,'cost_usd':1.0,'estimate_cost_usd':0.5,'wall_time_s':120},'output':str(root/'result'),'completion_jev':False}
    if a.adapter:config['adapter']=a.adapter
    if a.confirm_provider_budget:config['provider_budget_confirmed']=True
    (root/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    print('Created clean repository and pinned config: '+str(root/'config.json'))
    print('Initialize: '+str(ROOT/'.venv-demo/bin/python')+' -m harness.runtime init --config '+str(root/'config.json')+' --state '+str(root/'state'))
if __name__=='__main__':main()
