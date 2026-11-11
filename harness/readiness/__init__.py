"""Local host readiness checks; no model, project code, or tests are executed."""

import shutil
import sys

from harness.isolation.backend import BubblewrapBackend

MODES = ('development', 'execution')


def check_readiness(mode: str = 'development', *, backend=None) -> dict:
    """Report prerequisites without weakening production isolation.

    `backend` is a host-test seam, not a setting from a task or model response.
    Development checks never probe a sandbox or authorize untrusted execution.
    """
    if mode not in MODES:
        raise ValueError('Unknown readiness mode')

    python_ok = sys.version_info >= (3, 12)
    git_path = shutil.which('git')
    checks = {
        'python': {'ok': python_ok,
                   'version': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}',
                   'required': '3.12+'},
        'git': {'ok': bool(git_path), 'path': git_path},
    }

    isolation_ok = False
    if mode == 'execution':
        selected = backend if backend is not None else BubblewrapBackend()
        try:
            result = selected.probe()
            if type(result) is not dict:
                raise TypeError('Unexpected isolation probe response')
        except Exception as error:
            result = {'available': False, 'reason': 'Isolation probe error: ' + type(error).__name__}
        isolation_ok = result.get('available') is True
        checks['isolation'] = {'required': True, 'checked': True,
                               'available': isolation_ok,
                               'reason': str(result.get('reason', '')),
                               'version': result.get('version')}
    else:
        checks['isolation'] = {'required': False, 'checked': False,
                               'available': None,
                               'reason': 'Not required for trusted development and unit tests'}

    ready = python_ok and bool(git_path) and (mode == 'development' or isolation_ok)
    return {
        'mode': mode,
        'ready': bool(ready),
        'can_execute_untrusted_code': bool(ready and mode == 'execution'),
        'checks': checks,
    }
