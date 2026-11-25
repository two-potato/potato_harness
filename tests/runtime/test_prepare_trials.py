"""Regression: trial preparation must install marketplace dev requirements, without real installs."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import prepare_trials


class PreparationTests(unittest.TestCase):
    def test_install_includes_marketplace_requirements_before_sdk_bootstrap(self):
        calls = []

        def fake_call(argv, cwd=None, env=None):
            argv = [str(x) for x in argv]
            calls.append(argv)
            if '-c' in argv and any('harness.isolation' in arg for arg in argv):
                return json.dumps({'available': False, 'reason': 'fixture namespace unavailable'})
            if 'node_modules/@opencode/sdk/package.json' in ' '.join(argv):return '2.4.1'
            if argv[-1]=='--version' and argv[0].endswith('/bun'):return '1.4.4'
            return 'fixture result'

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'report.json'
            with patch.object(prepare_trials, 'ROOT', root), \
                 patch.object(prepare_trials, 'INTEGRATION', root / 'integration'), \
                 patch.object(prepare_trials.sys, 'argv', ['prepare_trials.py', '--install', '--output', str(output)]), \
                 patch.object(prepare_trials, 'call', side_effect=fake_call), \
                 patch.object(prepare_trials.venv, 'EnvBuilder') as builder:
                self.assertEqual(prepare_trials.main(), 1)  # Missing sandbox fails closed.
            builder.assert_called_once_with(with_pip=True)
            self.assertEqual(calls[0], [
                str(root / '.venv-demo/bin/python'), '-m', 'pip', 'install',
                '-r', str(root / 'requirements-validation.txt'),
                '-r', str(root / 'blueprints/marketplace/requirements-dev.txt'),
            ])
            self.assertEqual(calls[1][:2], ['npm', 'ci'])
            self.assertEqual(calls[2], ['node','node_modules/bun/install.js'])
            self.assertFalse(any('src/bootstrap.mjs' in argv for argv in calls))
            report = json.loads(output.read_text())
            self.assertEqual(report['checks']['isolation']['status'], 'BLOCKED_HOST')
            self.assertEqual(report['inference'], 'NOT_RUN')
            self.assertEqual(report['checks']['opencode_sdk'],{'status':'PASS','version':'2.4.1'})
            self.assertEqual(report['checks']['bun'],{'status':'PASS','version':'1.4.4'})

    def test_marketplace_requirement_contains_pyyaml(self):
        required = (Path(__file__).resolve().parents[2] /
                    'blueprints/marketplace/requirements-dev.txt').read_text()
        self.assertIn('PyYAML', required)


if __name__ == '__main__':
    unittest.main()
