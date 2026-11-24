"""Safe, read-only trial reporting: never dump prompt, token or provider stderr."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import trial_diagnostics


class TrialDiagnosticTests(unittest.TestCase):
    def test_no_provider_call_and_no_sensitive_state_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'gateway-phases.json').write_text(json.dumps({
                'outcome': 'TIMEOUT',
                'raw_stderr': 'Bearer TOP_SECRET',
                'events': [
                    {'phase': 'valera', 'status': 'start', 'elapsed_ms': 20},
                    {'phase': 'cleanup', 'status': 'ok', 'elapsed_ms': 4},
                    {'phase': 'usage', 'status': 'error', 'elapsed_ms': 1,
                     'api_key': 'TOP_SECRET'},
                    {'phase': 'SECRET_PHASE', 'status': 'ok', 'elapsed_ms': 1},
                ],
            }))
            supplied = {
                'state': 'HOLD', 'task_status': 'BLOCKED',
                'unresolved_effects': ['provider-secret-id'],
                'reason': 'Bearer TOP_SECRET',
                'prompt': 'TOP_SECRET',
            }
            with patch.object(trial_diagnostics, 'status', return_value=supplied) as read:
                summary = trial_diagnostics.summarize(root)
            read.assert_called_once_with(root.absolute())
            self.assertEqual(summary['unresolved_effect_count'], 1)
            self.assertEqual(summary['gateway']['outcome'], 'TIMEOUT')
            self.assertEqual(len(summary['gateway']['events']), 2)
            self.assertNotIn('TOP_SECRET', json.dumps(summary))
            self.assertNotIn('provider-secret-id', json.dumps(summary))

    def test_missing_phase_file_is_not_an_invented_success(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(trial_diagnostics, 'status',
                              return_value={'state': 'INITIALIZED',
                                            'task_status': 'NEW',
                                            'unresolved_effects': []}):
                value = trial_diagnostics.summarize(temp)
            self.assertIsNone(value['gateway'])

    def test_invalid_phase_file_is_not_echoed(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'gateway-phases.json'
            p.write_text('Bearer SECRET: invalid JSON')
            with patch.object(trial_diagnostics, 'status',
                              return_value={'state': 'HOLD',
                                            'task_status': 'BLOCKED',
                                            'unresolved_effects': []}):
                value = trial_diagnostics.summarize(temp)
            self.assertEqual(value['gateway'], {'outcome': 'INVALID', 'events': []})
            self.assertNotIn('SECRET', json.dumps(value))


if __name__ == '__main__':
    unittest.main()
