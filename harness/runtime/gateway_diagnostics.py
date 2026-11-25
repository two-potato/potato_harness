"""Allowlisted OpenCode phase events, never raw provider stderr.

This metadata is advisory for troubleshooting; it is not execution evidence.
"""

import json
import os

PREFIX = 'POTATO_GATEWAY_PHASE '
PHASES = frozenset({'request', 'server', 'omo', 'valera', 'specialist', 'usage', 'cleanup'})
STATUSES = frozenset({'start', 'ok', 'error'})
MAX_STDERR_TAIL = 65536
MAX_EVENTS = 64
VALERA_STEPS = frozenset({'unknown', 'coordination', 'session', 'prompt', 'close', 'response', 'json', 'assignment'})
VALERA_CODES = frozenset({'STEP_FAILED', 'DEADLINE', 'ABORTED', 'AUTH', 'RATE_LIMIT', 'RESPONSE_REJECTED', 'INVALID_JSON', 'INVALID_ASSIGNMENT', 'FREE_QUOTA', 'PROVIDER_UNAVAILABLE', 'RETRY_BLOCKED', 'MONITOR_FAILED'})


def safe_gateway_event(event):
    """Accept legacy events or exact allowlisted model-stage error metadata."""
    basic = {'phase', 'status', 'elapsed_ms'}
    if type(event) is not dict or set(event) not in (basic, basic | {'step', 'reason_code'}):
        return None
    phase, status, elapsed = event['phase'], event['status'], event['elapsed_ms']
    if type(phase) is not str or phase not in PHASES:
        return None
    if type(status) is not str or status not in STATUSES:
        return None
    if type(elapsed) is not int or not 0 <= elapsed <= 3_600_000:
        return None
    result = {'phase': phase, 'status': status, 'elapsed_ms': elapsed}
    if set(event) != basic:
        step, code = event['step'], event['reason_code']
        if phase not in ('valera', 'specialist') or status != 'error':
            return None
        if type(step) is not str or step not in VALERA_STEPS:
            return None
        if type(code) is not str or code not in VALERA_CODES:
            return None
        result.update(step=step, reason_code=code)
    return result


def parse_gateway_events(stderr):
    """Read a bounded stderr tail and retain only fixed, non-secret fields."""
    stderr.seek(0, os.SEEK_END)
    size = stderr.tell()
    stderr.seek(max(0, size - MAX_STDERR_TAIL))
    tail = stderr.read(MAX_STDERR_TAIL).decode('utf-8', 'replace')
    if size > MAX_STDERR_TAIL:
        tail = tail.partition('\n')[2]  # discard a possibly truncated line
    events = []
    for line in tail.splitlines():
        if not line.startswith(PREFIX):
            continue
        try:
            event = json.loads(line[len(PREFIX):])
        except (ValueError, TypeError):
            continue
        safe = safe_gateway_event(event)
        if safe is not None:
            events.append(safe)
    return events[-MAX_EVENTS:]
