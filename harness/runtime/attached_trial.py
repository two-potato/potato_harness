"""Exact synthetic scope for the reviewed first attached model trial."""
import ast
import re
from pathlib import Path
from harness.runtime.workspace import _git_bytes

ADAPTER = 'opencode-v2-attached-free'
MODEL = 'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free'
OBJECTIVE = 'Fix subtotal so it multiplies integer unit price by quantity. Preserve function signature.'
TEST_ARGV = ['/usr/bin/python3','-B','-m','unittest','discover','-s','tests','-v']
FILES = {
    'calculation.py': b'def subtotal(unit_cents, quantity):\n    return unit_cents + quantity\n',
    'tests/test_calculation.py': b'import unittest\nfrom calculation import subtotal\nclass CalculationTests(unittest.TestCase):\n    def test_total(self): self.assertEqual(subtotal(1250,3),3750)\n    def test_zero(self): self.assertEqual(subtotal(1250,0),0)\n    def test_one(self): self.assertEqual(subtotal(1250,1),1250)\n',
}

def verify_source(repo,base):
    names=set()
    for entry in filter(None,_git_bytes(repo,'ls-tree','-rz','--full-tree',base).split(b'\0')):
        header,name=entry.split(b'\t',1)
        mode,kind,blob=header.decode().split()
        name=name.decode()
        if mode!='100644' or kind!='blob' or name not in FILES or _git_bytes(repo,'cat-file','blob',blob)!=FILES[name]:
            raise ValueError('Attached trial requires exact synthetic source')
        names.add(name)
    if names!=set(FILES):
        raise ValueError('Attached trial source set mismatch')

def verify_workspace(workspace):
    workspace=Path(workspace)
    actual={str(p.relative_to(workspace)) for p in workspace.rglob('*')}
    if actual!=set(FILES)|{'tests'} or (workspace/'tests').is_symlink():
        raise ValueError('Attached trial workspace set mismatch')
    for name,content in FILES.items():
        p=workspace/name
        if p.resolve()!=p or p.is_symlink() or not p.is_file() or p.stat().st_nlink!=1 or p.read_bytes()!=content:
            raise ValueError('Attached trial workspace source mismatch')


# Exact first-trial policy, not a general Python or project policy.
def verify_proposal(content):
    if type(content) is not str or len(content.encode())>4096:
        raise ValueError('Attached trial proposal outside pure-function scope')
    try:
        actual=ast.dump(ast.parse(content),include_attributes=False)
    except (SyntaxError,ValueError,RecursionError) as exc:
        raise ValueError('Attached trial invalid Python proposal') from exc
    allowed=[ast.dump(ast.parse('def subtotal(unit_cents, quantity):\n    return '+expr+'\n'),include_attributes=False)
             for expr in ('unit_cents * quantity','quantity * unit_cents')]
    if actual not in allowed:
        raise ValueError('Attached trial proposal outside pure-function scope')

TEST_IDS=tuple('test_calculation.CalculationTests.'+name for name in ('test_one','test_total','test_zero'))

def verify_test_result(test):
    # Exit zero alone is not acceptance. The pure AST prevents import-time
    # exit or forged unittest output by this particular scoped candidate.
    if (type(test) is not dict or type(test.get('returncode')) is not int or
            test['returncode']!=0 or test.get('timed_out') is not False or
            test.get('stdout')!='' or type(test.get('stderr')) is not str):
        raise ValueError('Attached trial expected successful three-test transcript')
    lines=test['stderr'].splitlines()
    expected=[f'{name.rsplit(".",1)[-1]} ({name}) ... ok' for name in TEST_IDS]
    if (len(lines)!=8 or lines[:3]!=expected or lines[3]!='' or
            not re.fullmatch(r'-{60,80}',lines[4]) or
            not re.fullmatch(r'Ran 3 tests in \d+\.\d+s',lines[5]) or
            lines[6:]!=['','OK']):
        raise ValueError('Attached trial expected successful three-test transcript')
    return list(TEST_IDS)
