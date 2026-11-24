"""Safe provider phase logging and timeout behavior; no external model calls."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from harness.runtime import _worker
from harness.runtime.gateway_diagnostics import parse_gateway_events


class GatewayDiagnosticsTests(unittest.TestCase):
    def test_only_allowlisted_fields_survive(self):
        raw = (b'Bearer SECRET_TOKEN\n'
               b'POTATO_GATEWAY_PHASE {"phase":"server","status":"start","elapsed_ms":0}\n'
               b'POTATO_GATEWAY_PHASE {"phase":"server","status":"ok","elapsed_ms":1,"api_key":"SECRET_TOKEN"}\n'
               b'POTATO_GATEWAY_PHASE {"phase":"unknown","status":"ok","elapsed_ms":2}\n'
               b'POTATO_GATEWAY_PHASE {"phase":[],"status":"ok","elapsed_ms":2}\n'
               b'POTATO_GATEWAY_PHASE {"phase":"valera","status":{},"elapsed_ms":2}\n'
               b'POTATO_GATEWAY_PHASE {"phase":"valera","status":"error","elapsed_ms":3}\n')
        self.assertEqual(parse_gateway_events(io.BytesIO(raw)), [
            {'phase': 'server', 'status': 'start', 'elapsed_ms': 0},
            {'phase': 'valera', 'status': 'error', 'elapsed_ms': 3},
        ])

    def test_subprocess_success_persists_only_phase_metadata(self):
        code = ('import sys\n'
                'sys.stderr.write("Bearer PRIVATE\\n")\n'
                'sys.stderr.write(\'POTATO_GATEWAY_PHASE {"phase":"specialist","status":"ok","elapsed_ms":12}\\n\')\n'
                'print(\'{"edits":[],"summary":"fixture"}\')\n')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'gateway-phases.json'
            response = _worker({}, [sys.executable, '-c', code], 5, diagnostics_path=path)
            self.assertEqual(response['summary'], 'fixture')
            record = json.loads(path.read_text())
            self.assertEqual(record['outcome'], 'OK')
            self.assertEqual(record['events'], [{'phase': 'specialist', 'status': 'ok', 'elapsed_ms': 12}])
            self.assertNotIn('PRIVATE', path.read_text())

    def test_timeout_persists_last_phase_without_raw_error_or_replay(self):
        code = ('import sys,time\n'
                'sys.stderr.write(\'POTATO_GATEWAY_PHASE {"phase":"valera","status":"start","elapsed_ms":0}\\n\')\n'
                'sys.stderr.write("SECRET_SENTINEL\\n")\n'
                'sys.stderr.flush()\n'
                'time.sleep(5)\n')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'gateway-phases.json'
            with self.assertRaisesRegex(RuntimeError, 'timed out; outcome uncertain'):
                _worker({}, [sys.executable, '-c', code], 1.2, diagnostics_path=path)
            record = json.loads(path.read_text())
            self.assertEqual(record['outcome'], 'TIMEOUT')
            self.assertEqual(record['events'], [{'phase': 'valera', 'status': 'start', 'elapsed_ms': 0}])
            self.assertNotIn('SECRET_SENTINEL', path.read_text())

    def test_nonzero_exit_remains_generic_and_preserves_phase(self):
        code = ('import sys\n'
                'sys.stderr.write(\'POTATO_GATEWAY_PHASE {"phase":"omo","status":"error","elapsed_ms":7}\\n\')\n'
                'sys.exit(3)\n')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'gateway-phases.json'
            with self.assertRaisesRegex(RuntimeError, 'Provider bridge failed'):
                _worker({}, [sys.executable, '-c', code], 5, diagnostics_path=path)
            record = json.loads(path.read_text())
            self.assertEqual(record['outcome'], 'ERROR')
            self.assertEqual(record['events'][0]['phase'], 'omo')


if __name__ == '__main__':
    unittest.main()
