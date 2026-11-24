"""Allowlisted OpenCode phase events, never raw provider stderr.

This metadata is advisory for troubleshooting; it is not execution evidence.
"""

import json
import os

PREFIX = 'POTATO_GATEWAY_PHASE '
PHASES = frozenset({'request', 'server', 'omo', 'valera', 'specialist', 'usage'})
STATUSES = frozenset({'start', 'ok', 'error'})
MAX_STDERR_TAIL = 65536
MAX_EVENTS = 64


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
        if type(event) is not dict or set(event) != {'phase', 'status', 'elapsed_ms'}:
            continue
        if type(event['phase']) is not str or type(event['status']) is not str:
            continue
        if event['phase'] not in PHASES or event['status'] not in STATUSES:
            continue
        elapsed = event['elapsed_ms']
        if type(elapsed) is not int or not 0 <= elapsed <= 3_600_000:
            continue
        events.append({'phase': event['phase'], 'status': event['status'], 'elapsed_ms': elapsed})
    return events[-MAX_EVENTS:]
