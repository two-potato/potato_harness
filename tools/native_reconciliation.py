"""Read-only, secret-safe local reconciliation dossier. Never authorizes inference."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.runtime.gateway_diagnostics import safe_gateway_event

MODES = frozenset({'external', 'synthetic', 'offline'})
EFFECT_STATES = frozenset({'PENDING', 'DISPATCHING', 'SUCCEEDED', 'FAILED', 'UNKNOWN'})
TASK_STATES = frozenset({'NEW','CLASSIFIED','PLANNED','ASSIGNED','EXECUTING','REVIEWING',
    'VERIFYING','COMPLETION_AUDITING','REREVIEW','REPAIR','ACCEPTED','DONE','BLOCKED',
    'NEEDS_HUMAN_APPROVAL','CANCELLED'})
UNRESOLVED = frozenset({'PENDING','DISPATCHING','UNKNOWN'})
MAX_JSON = 1024 * 1024

def _file(path):
    info = path.lstat()
    if (path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid() or info.st_nlink != 1):
        raise ValueError('Unsafe state file')
    return path

def _read_json(path):
    _file(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        info = os.fstat(f.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_size > MAX_JSON):
            raise ValueError('Unsafe JSON input')
        raw = f.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise ValueError('Oversize JSON')
    result = json.loads(raw)
    if type(result) is not dict:
        raise ValueError('Invalid state')
    return result

def _enum(value, allowed):
    return value if type(value) is str and value in allowed else 'UNRECOGNIZED'

def _time(value):
    try:
        if type(value) is not str or len(value) > 40:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        return None

def inspect_trial(state):
    """One bounded SQLite read snapshot, plus advisory on-disk metadata.

    Operator must stop old processes first. This does not prove completeness
    of the local history or authenticate provider delivery/billing.
    """
    root = Path(state).absolute()
    if root.resolve(strict=True) != root or not root.is_dir() or root.stat().st_uid != os.getuid():
        raise ValueError('Unsafe trial directory')
    run = _read_json(root/'run.json')
    task_id = run.get('task_id')
    if type(task_id) is not str or not 1 <= len(task_id) <= 256:
        raise ValueError('Missing task binding')
    database = _file(root/'state.db')
    for suffix in ('-wal','-shm','-journal'):
        sidecar = root/('state.db'+suffix)
        if sidecar.exists() or sidecar.is_symlink():
            _file(sidecar)
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True, timeout=3)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('BEGIN')
        if [r[0] for r in db.execute('SELECT version FROM schema_migrations ORDER BY version LIMIT 2')] != [1]:
            raise ValueError('Unsupported schema')
        task = db.execute('SELECT state FROM tasks WHERE task_id=?', (task_id,)).fetchone()
        if task is None:
            raise ValueError('Missing task')
        rows = db.execute(
            'SELECT state, CASE WHEN provider_operation_id IS NOT NULL AND '
            'length(trim(provider_operation_id))>0 THEN 1 ELSE 0 END, created_at, updated_at '
            'FROM outbox WHERE task_id=? ORDER BY effect_id LIMIT 1001', (task_id,)).fetchall()
        if len(rows)>1000:
            raise ValueError('Effect history exceeds report bound')
        db.rollback()
    gateway = None
    p = root/'gateway-phases.json'
    if p.exists() or p.is_symlink():
        raw = _read_json(p)
        events = raw.get('events')
        if type(events) is not list or len(events)>64:
            raise ValueError('Invalid gateway history')
        gateway = {'outcome':_enum(raw.get('outcome'), {'OK','ERROR','TIMEOUT'}),
                   'errors':[safe for event in events
                             if (safe := safe_gateway_event(event)) and safe['status']=='error'],
                   'legacy_omo_observed':any(
                       safe and safe['phase']=='omo' for safe in map(safe_gateway_event,events))}
    mode = _enum(run.get('provider_mode'), MODES)
    if mode=='UNRECOGNIZED':
        mode='UNSPECIFIED_LEGACY' if gateway and gateway['legacy_omo_observed'] else 'UNSPECIFIED'
    effects = [{'state':_enum(s,EFFECT_STATES), 'provider_operation_id_recorded':bool(has),
                'created_utc':_time(created), 'updated_utc':_time(updated)}
               for s,has,created,updated in rows]
    unknown = [e for e in effects if e['state'] in UNRESOLVED or e['state']=='UNRECOGNIZED']
    result = {'provider_mode':mode,'run_state':_enum(run.get('state'), {'INITIALIZED','RUNNING','HOLD','DONE'}),
        'task_state':_enum(task[0],TASK_STATES), 'effect_count':len(effects),
        'unresolved_effect_count':len(unknown),
        'unresolved_with_provider_id':sum(e['provider_operation_id_recorded'] for e in unknown),
        'unresolved_effects':unknown, 'gateway':gateway,
        'local_finding':'UNRESOLVED_EFFECTS' if unknown else 'NO_LOCAL_UNRESOLVED_EFFECTS',
        'provider_outcome_verified':False,'billing_verified':False,'runtime_admission':False}
    # A digest of this sanitized report, not of source DB or external evidence.
    result['report_sha256'] = hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', action='append', type=Path, required=True)
    args=parser.parse_args(argv)
    reports=[]
    if len(args.state)>32:
        parser.error('At most 32 explicit trial directories')
    for index,state in enumerate(args.state,1):
        try:
            reports.append({'index':index,'report':inspect_trial(state)})
        except Exception:
            reports.append({'index':index,'status':'UNAVAILABLE'})
    print(json.dumps({'status':'HOLD','reports':reports,'runtime_admission':False},indent=2))
    return 2

if __name__=='__main__':
    raise SystemExit(main())
