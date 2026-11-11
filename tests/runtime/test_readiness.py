"""No provider/model calls and no untrusted project execution in these tests."""

from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from harness.isolation.backend import BubblewrapBackend
from harness.readiness import check_readiness


class ReadinessTests(unittest.TestCase):
    def test_development_never_probes_isolation(self):
        with patch('harness.readiness.BubblewrapBackend', side_effect=AssertionError('Sandbox probe called')):
            with patch('harness.readiness.shutil.which', return_value='/usr/bin/git'):
                report = check_readiness('development')
        self.assertTrue(report['ready'])
        self.assertFalse(report['can_execute_untrusted_code'])
        self.assertFalse(report['checks']['isolation']['checked'])

    def test_execution_denied_when_profile_unavailable(self):
        class Unavailable:
            def probe(self):
                return {'available': False, 'reason': 'namespace denied', 'version': 'test'}

        with patch('harness.readiness.shutil.which', return_value='/usr/bin/git'):
            report = check_readiness('execution', backend=Unavailable())
        self.assertFalse(report['ready'])
        self.assertFalse(report['can_execute_untrusted_code'])
        self.assertIn('namespace denied', report['checks']['isolation']['reason'])

    def test_execution_accepts_only_literal_true_from_probe(self):
        class Malformed:
            def probe(self):
                return {'available': 1, 'reason': 'incorrectly truthy'}

        with patch('harness.readiness.shutil.which', return_value='/usr/bin/git'):
            report = check_readiness('execution', backend=Malformed())
        self.assertFalse(report['ready'])

    def test_execution_probes_and_reports_verified_backend(self):
        class Available:
            def probe(self):
                return {'available': True, 'reason': 'isolated', 'version': 'test'}

        with patch('harness.readiness.shutil.which', return_value='/usr/bin/git'):
            report = check_readiness('execution', backend=Available())
        self.assertTrue(report['ready'])
        self.assertTrue(report['can_execute_untrusted_code'])
        self.assertEqual(report['checks']['isolation']['version'], 'test')

    def test_probe_exceptions_fail_closed(self):
        class Broken:
            def probe(self):
                raise OSError('do not trust the environment')

        with patch('harness.readiness.shutil.which', return_value='/usr/bin/git'):
            report = check_readiness('execution', backend=Broken())
        self.assertFalse(report['ready'])
        self.assertNotIn('do not trust the environment', report['checks']['isolation']['reason'])

    def test_missing_git_blocks_both_modes(self):
        class Available:
            def probe(self):
                return {'available': True}

        with patch('harness.readiness.shutil.which', return_value=None):
            self.assertFalse(check_readiness('development')['ready'])
            self.assertFalse(check_readiness('execution', backend=Available())['ready'])

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            check_readiness('unsafe')

    def test_bubblewrap_adapter_delegates_to_existing_functions(self):
        backend = BubblewrapBackend()
        with patch('harness.isolation.backend.bubblewrap_probe', return_value={'available': False}) as probe:
            self.assertFalse(backend.probe()['available'])
            probe.assert_called_once_with()
        with patch('harness.isolation.backend.bubblewrap_run_private', return_value={'returncode': 0}) as run:
            self.assertEqual(backend.run(Path('/work'), ['/usr/bin/true'], timeout=4), {'returncode': 0})
            run.assert_called_once_with(Path('/work'), ['/usr/bin/true'], timeout=4)

    def test_development_cli_runs_without_bubblewrap(self):
        result = subprocess.run([sys.executable, '-m', 'harness.readiness', '--mode', 'development'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('"can_execute_untrusted_code": false', result.stdout)
        self.assertIn('"checked": false', result.stdout)


if __name__ == '__main__':
    unittest.main()
