#!/usr/bin/env python3
"""Read-only, secret-safe status snapshot for one Potato Harness trial."""
import argparse
import json
from pathlib import Path
import sys

from harness.runtime import status
from harness.runtime.gateway_diagnostics import PHASES, STATUSES

RUN_STATES = frozenset({'INITIALIZED', 'RUNNING', 'HOLD', 'DONE'})
TASK_STATES = frozenset({
    'NEW', 'CLASSIFIED', 'PLANNED', 'ASSIGNED', 'EXECUTING',
    'REVIEWING', 'VERIFYING', 'COMPLETION_AUDITING', 'ACCEPTED',
    'DONE', 'BLOCKED', 'CANCELLED', 'NEEDS_HUMAN_APPROVAL',
    'REREVIEW',
})
OUTCOMES = frozenset({'OK', 'ERROR', 'TIMEOUT'})


def _safe_state(value, allowed):
    return value if type(value) is str and value in allowed else 'UNRECOGNIZED'


def _safe_events(value):
    events = []
    if type(value) is not list:
        return events
    for item in value[-64:]:
        if type(item) is not dict or set(item) != {'phase', 'status', 'elapsed_ms'}:
            continue
        phase, stage, ms = item['phase'], item['status'], item['elapsed_ms']
        if type(phase) is not str or phase not in PHASES:
            continue
        if type(stage) is not str or stage not in STATUSES:
            continue
        if type(ms) is not int or not 0 <= ms <= 3_600_000:
            continue
        events.append({'phase': phase, 'status': stage, 'elapsed_ms': ms})
    return events


def summarize(state):
    """Inspect existing state; never create an effect, invoke a provider, or print prompts."""
    state = Path(state).absolute()
    run = status(state)
    result = {
        'run_state': _safe_state(run.get('state'), RUN_STATES),
        'task_status': _safe_state(run.get('task_status'), TASK_STATES),
        'unresolved_effect_count': len(run['unresolved_effects'])
            if type(run.get('unresolved_effects')) is list else None,
        'gateway': None,
    }
    phases = state / 'gateway-phases.json'
    if phases.is_file():
        # Limit disk input, and keep arbitrary file content out of stdout.
        if phases.stat().st_size > 65536:
            result['gateway'] = {'outcome': 'INVALID', 'events': []}
        else:
            try:
                record = json.loads(phases.read_text(encoding='utf-8'))
                if type(record) is not dict:
                    raise ValueError('Not an object')
            except (OSError, UnicodeError, ValueError):
                result['gateway'] = {'outcome': 'INVALID', 'events': []}
            else:
                result['gateway'] = {
                    'outcome': _safe_state(record.get('outcome'), OUTCOMES),
                    'events': _safe_events(record.get('events')),
                }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = summarize(args.state)
    except Exception as error:
        # Deliberately do not echo exception text, paths, credentials or raw state.
        print('Cannot read trial state safely: ' + type(error).__name__, file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
