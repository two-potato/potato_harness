"""Two-value proposal vocabulary. The worker cannot supply executable source."""
import os
from pathlib import Path
import subprocess
import sys

SOURCE = 'def subtotal(unit_cents, quantity):\n    return unit_cents {operator} quantity\n'
TESTS = '''import unittest
from calculation import subtotal

class PricingTests(unittest.TestCase):
    def test_three_items(self):
        self.assertEqual(subtotal(1250, 3), 3750)
    def test_empty_basket(self):
        self.assertEqual(subtotal(1250, 0), 0)
    def test_single_item(self):
        self.assertEqual(subtotal(1250, 1), 1250)

if __name__ == '__main__':
    unittest.main(verbosity=2)
'''


def validate_proposal(proposal):
    if (not isinstance(proposal, dict) or set(proposal) != {'operator'}
            or proposal['operator'] not in ('add', 'multiply')):
        raise ValueError('Proposal must contain only operator=add or multiply')
    return proposal['operator']


def environment(workspace):
    # Do not forward API keys, Git injection variables or Python startup hooks.
    return {'PATH': os.defpath, 'HOME': str(workspace), 'LANG': 'C.UTF-8',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_AUTHOR_NAME': 'Potato Demo', 'GIT_AUTHOR_EMAIL': 'demo@example.invalid',
            'GIT_COMMITTER_NAME': 'Potato Demo', 'GIT_COMMITTER_EMAIL': 'demo@example.invalid',
            'PYTHONDONTWRITEBYTECODE': '1'}


def command(workspace, args, *, check=True):
    completed = subprocess.run(args, cwd=workspace, env=environment(workspace),
                               capture_output=True, timeout=20, check=False)
    if check and completed.returncode:
        raise RuntimeError('Demo subprocess failed: ' + completed.stderr.decode(errors='replace')[:1000])
    return completed


def git(workspace, *args):
    return command(workspace, ['git', '-c', 'core.hooksPath=/dev/null', *args]).stdout.decode().strip()


def prepare(workspace):
    empty = workspace / 'empty-template'
    empty.mkdir()
    git(workspace, 'init', '--template=' + str(empty), '-b', 'main')
    (workspace / 'calculation.py').write_text(SOURCE.format(operator='+'))
    (workspace / 'test_calculation.py').write_text(TESTS)
    git(workspace, 'add', 'calculation.py', 'test_calculation.py')
    git(workspace, 'commit', '-m', 'fixture: demonstrate subtotal bug')
    return git(workspace, 'rev-parse', 'HEAD')


def apply_proposal(workspace, proposal, *, actor, permitted):
    operator = validate_proposal(proposal)
    if actor != 'backend' or permitted is not True:
        raise PermissionError('Permission denied: only the assigned backend may edit calculation.py')
    path = workspace / 'calculation.py'
    if path.is_symlink() or path.parent.resolve() != workspace.resolve():
        raise PermissionError('Permission denied: unsafe artifact path')
    path.write_text(SOURCE.format(operator='*' if operator == 'multiply' else '+'))
    git(workspace, 'add', 'calculation.py')
    git(workspace, 'commit', '--allow-empty', '-m', 'worker: propose subtotal operator')
    return git(workspace, 'rev-parse', 'HEAD')


def test_candidate(workspace):
    # This fixed test script imports only code rendered from the two-value enum.
    result = command(workspace, [sys.executable, '-E', '-s', '-B', 'test_calculation.py'], check=False)
    return result.returncode, result.stdout + result.stderr
