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

    def test_valera_failure_detail_survives_only_fixed_allowlists(self):
        event = {'phase': 'valera', 'status': 'error', 'elapsed_ms': 5,
                 'step': 'json', 'reason_code': 'INVALID_JSON'}
        entries = [event, {**event, 'reason_code': 'PRIVATE'},
                   {**event, 'step': 'PRIVATE'}, {**event, 'status': 'ok'},
                   {**event, 'phase': 'server'}, {**event, 'extra': 'PRIVATE'}]
        raw = ''.join('POTATO_GATEWAY_PHASE ' + json.dumps(e) + '\n' for e in entries)
        self.assertEqual(parse_gateway_events(io.BytesIO(raw.encode())), [event])

    def test_host_passes_bounded_bridge_deadline(self):
        code = 'import json,sys;print(json.dumps({"bridge_timeout_ms":json.loads(sys.stdin.read())["bridge_timeout_ms"]}))'
        response = _worker({}, [sys.executable, '-c', code], 8)
        self.assertGreaterEqual(response['bridge_timeout_ms'], 4001)
        self.assertLess(response['bridge_timeout_ms'], 8000)

    def test_cleanup_marker_is_allowed(self):
        message = b'POTATO_GATEWAY_PHASE {"phase":"cleanup","status":"error","elapsed_ms":19}\n'
        self.assertEqual(parse_gateway_events(io.BytesIO(message)),
                         [{'phase':'cleanup','status':'error','elapsed_ms':19}])

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
