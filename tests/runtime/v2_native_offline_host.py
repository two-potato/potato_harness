"""Hosted diagnostic: real CLI, no external inference, injected sandbox probe."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from harness.runtime import init, run, halo, recover


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / 'trial'
        subprocess.run([sys.executable, 'tools/create_trial.py', '--directory', str(root),
                        '--adapter', 'opencode-v2-native-free-offline',
                        '--model', 'opencode/beam-free'], check=True)
        config = json.loads((root / 'config.json').read_text())
        state = root / 'state'
        init(config, state)
        result = run(state, sandbox_probe=lambda: {'available': True, 'reason': 'CI injected sandbox seam'},
                     sandbox_run=lambda *a, **k: (_ for _ in ()).throw(AssertionError('unexpected sandbox execution')))
        assert result['state'] == 'HOLD'
        assert result['task_status'] == 'BLOCKED'
        assert result['provider_mode'] == 'offline'
        assert len(result['unresolved_effects']) == 1
        assert result['grant']['status'] == 'REVOKED'
        assert result['lease_id'] is None
        assert not (state / 'result.json').exists()
        assert not (root / 'result').exists()
        assert (state / 'workspace/calculation.py').read_text().endswith('unit_cents + quantity\n')
        with sqlite3.connect(state / 'state.db') as db:
            assert db.execute('SELECT state FROM outbox').fetchall() == [('UNKNOWN',)]
            assert db.execute('SELECT count(*) FROM budget_reservations WHERE settlement IS NULL').fetchone()[0] == 1
        report = json.loads((state / 'gateway-phases.json').read_text())
        assert report['outcome'] == 'ERROR'
        assert report['events'][-1] == {'phase': 'offline_boundary', 'status': 'ok', 'elapsed_ms': 0}, report
        assert not any(e['phase'] == 'specialist' for e in report['events'])
        assert recover(state)['state'] == 'HOLD'
        assert halo(state)['status'] == 'HOLD'
        print(json.dumps({'status': 'PASS', 'layer': 'actual-native-offline-runtime',
                          'runtime': 'HOLD', 'offline_boundary': True,
                          'external_inference': False, 'unresolved_effect_count': 1,
                          'sandbox': 'injected-seam'}))


if __name__ == '__main__':
    main()
