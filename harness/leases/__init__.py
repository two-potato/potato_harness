"""Trusted-host SQLite lease reservations; no worker or filesystem isolation."""
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import uuid
from jsonschema import Draft202012Validator, FormatChecker
from harness.controller import Controller, ControllerError

ROOT=Path(__file__).resolve().parents[2]

class LeaseError(ControllerError):
    """Lease request rejected without changing claims."""


def _text(value):
    if not isinstance(value,str) or not value.strip():
        raise LeaseError('nonblank binding required')


def _resources(resources):
    if not isinstance(resources,(list,tuple)) or not resources:
        raise LeaseError('nonempty resources required')
    result=[]
    for resource in resources:
        if not isinstance(resource,dict) or set(resource)!={'kind','key'} or resource['kind'] not in ('path','logical'):
            raise LeaseError('unknown resource fields/kind')
        key=resource['key']
        if not isinstance(key,str) or not key or key.strip()!=key or re.search(r'[\\*?\x00-\x20\x7f:]',key) or any(part in ('','.','..') for part in key.split('/')):
            raise LeaseError('resource key must be canonical relative prefix')
        pair={'kind':resource['kind'],'key':key}
        if pair in result:
            raise LeaseError('duplicate resource')
        result.append(pair)
    return result


def _overlap(a,b):
    if a['kind']!=b['kind']:
        return False
    x,y=a['key'],b['key']
    return x==y or (a['kind']=='path' and (x.startswith(y+'/') or y.startswith(x+'/')))


class LeaseManager:
    def __init__(self,database):
        self.controller=Controller(database)
        self.validator=Draft202012Validator(json.loads((ROOT/'schemas/lease.schema.json').read_text()),format_checker=FormatChecker())

    def _read(self,db,lease_id):
        row=db.execute('SELECT * FROM leases WHERE lease_id=?',(lease_id,)).fetchone()
        if row is None:
            raise LeaseError('lease not found')
        lease=dict(row)
        lease.update(schema_version='3.0.1',mode='exclusive_write',resources=[{'kind':r['kind'],'key':r['resource_key']} for r in db.execute('SELECT kind,resource_key FROM lease_claims WHERE lease_id=? ORDER BY kind,resource_key',(lease_id,))])
        self.validator.validate(lease)
        _resources(lease['resources'])
        return lease

    def acquire(self,task_id,expected_row_version,worker_session_id,workspace_id,resources,ttl=90):
        for value in (task_id,worker_session_id,workspace_id):_text(value)
        if type(expected_row_version) is not int or type(ttl) not in (int,float) or not math.isfinite(ttl) or not 0<ttl<=90:
            raise LeaseError('invalid CAS version or TTL (maximum 90 seconds)')
        claims=_resources(resources)
        with self.controller._connection(write=True) as db:
            task=self.controller._read(db,task_id)
            if task['row_version']!=expected_row_version or task['status'] not in ('ASSIGNED','EXECUTING'):
                raise LeaseError('stale row version or task not ASSIGNED/EXECUTING')
            # An ASSIGNED lease is only a prospective reservation. validate()
            # rejects all worker access until trusted state becomes EXECUTING.
            repo=task['repository_id']
            existing=db.execute("SELECT c.kind,c.resource_key FROM leases l JOIN lease_claims c USING(lease_id) WHERE l.repository_id=? AND l.status IN ('ACTIVE','SUSPECT')",(repo,))
            for row in existing:
                if any(_overlap(claim,{'kind':row['kind'],'key':row['resource_key']}) for claim in claims):
                    raise LeaseError('resource conflicts with ACTIVE/SUSPECT lease; expiry does not authorize reassignment')
            db.execute('INSERT INTO resource_fences(repository_id,token) VALUES (?,1) ON CONFLICT(repository_id) DO UPDATE SET token=token+1',(repo,))
            token=db.execute('SELECT token FROM resource_fences WHERE repository_id=?',(repo,)).fetchone()[0]
            lease_id=str(uuid.uuid4())
            expiry=(datetime.now(timezone.utc)+timedelta(seconds=ttl)).isoformat()
            db.execute("INSERT INTO leases VALUES (?,?,?,?,?,?,?,?,?)",(lease_id,repo,task_id,task['revision'],worker_session_id,workspace_id,token,expiry,'ACTIVE'))
            db.executemany('INSERT INTO lease_claims VALUES (?,?,?)',[(lease_id,c['kind'],c['key']) for c in claims])
            return self._read(db,lease_id)

    def validate(self,lease_id,task_id,revision,session,workspace):
        for value in (lease_id,task_id,session,workspace):_text(value)
        if type(revision) is not int:
            raise LeaseError('invalid revision')
        with self.controller._connection() as db:
            # A read transaction makes lease and task validation one SQLite snapshot.
            db.execute('BEGIN')
            lease=self._read(db,lease_id)
            task=self.controller._read(db,task_id)
            if (lease['task_id'],lease['task_revision'],lease['worker_session_id'],lease['workspace_id'])!=(task_id,revision,session,workspace):
                raise LeaseError('lease bindings mismatch')
            if task['status']!='EXECUTING' or task['revision']!=revision or task['repository_id']!=lease['repository_id']:
                raise LeaseError('stale task/repository binding')
            if lease['status']!='ACTIVE' or datetime.fromisoformat(lease['expires_at'])<=datetime.now(timezone.utc):
                raise LeaseError('lease not fresh ACTIVE')
            # Repository sequence allocation does not invalidate unrelated leases.
            return lease

    def suspect(self,lease_id):
        with self.controller._connection(write=True) as db:
            lease=self._read(db,lease_id)
            if lease['status'] not in ('ACTIVE','SUSPECT'):
                raise LeaseError('cannot suspect released lease')
            db.execute("UPDATE leases SET status='SUSPECT' WHERE lease_id=?",(lease_id,))
            return self._read(db,lease_id)

    def release(self,lease_id,*,reconcile=False):
        if reconcile is not True:
            raise LeaseError('trusted host reconciliation required before release')
        with self.controller._connection(write=True) as db:
            self._read(db,lease_id)
            db.execute("UPDATE leases SET status='REVOKED' WHERE lease_id=?",(lease_id,))
            return self._read(db,lease_id)

    def revoke(self,lease_id,*,reconcile=False):
        return self.release(lease_id,reconcile=reconcile)
