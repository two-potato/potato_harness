"""Single-host workflow recovery. No provider calls, release or replay."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import stat

from harness.controller import Controller, ControllerError, _json
from harness.verifier import TrustedEvidence


@contextmanager
def workflow_lock(database):
    """Serialize cooperating coordinators, recovery and integration on one DB.

    Use the database inode, not a replaceable lock-file name. This is advisory
    flock, separate from SQLite's byte-range locks; legacy or uncooperative
    processes are not fenced by it. The operator must stop those processes.
    """
    path=Path(database).resolve(strict=True)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.getuid():
            raise ControllerError('Trusted single-owner workflow database required')
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ControllerError('Workflow coordinator or recovery is active') from exc
        yield
    finally:
        os.close(fd)


def read_binding(controller,db,workflow_id):
    """Read the durable exact membership and accepted output map in one snapshot."""
    if type(workflow_id) is not str or not workflow_id:
        raise ControllerError('Workflow identity required')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_bindings'").fetchone():
        raise ControllerError('Legacy workflow lacks recoverable binding; inspect manually')
    row=db.execute('SELECT * FROM workflow_bindings WHERE workflow_id=?',(workflow_id,)).fetchone()
    run=db.execute('SELECT * FROM sequential_workflows WHERE workflow_id=?',(workflow_id,)).fetchone()
    batch=db.execute('SELECT active_json FROM workflow_active_batches WHERE workflow_id=?',(workflow_id,)).fetchone()
    if not row or not run or not batch:
        raise ControllerError('Exact durable workflow binding required; no legacy migration')
    binding=json.loads(row['binding_json'])
    outputs=json.loads(row['outputs_json'])
    active=json.loads(batch['active_json'])
    completed=json.loads(run['completed_json'])
    members=binding['members']
    if (type(members) is not dict or not 1<=len(members)<=64 or
            set(binding['paths'])!=set(members) or type(active) is not list or
            type(completed) is not list or len(active)!=len(set(active)) or
            len(completed)!=len(set(completed)) or set(active)&set(completed) or
            not set(active+completed)<=set(members) or set(outputs)!=set(completed) or
            run['active_task']!=(active[0] if active else None)):
        raise ControllerError('Inconsistent durable workflow membership')
    tasks={}
    mutable={'status','revision','row_version','target_commit'}
    for key,initial in members.items():
        current=controller._read(db,key)
        if (current['workflow_id'],current['repository_id'],current['user_turn_id'])!=(
                workflow_id,binding['repository_id'],binding['user_turn_id']) or (
                {k:v for k,v in current.items() if k not in mutable}!=
                {k:v for k,v in initial.items() if k not in mutable}):
            raise ControllerError('Workflow member identity changed; manual inspection required')
        if key in outputs:
            receipt=outputs[key]
            if (current['status']!='DONE' or current['revision']!=receipt['revision'] or
                    current['target_commit']['value']!=receipt['commit'] or
                    set(receipt['artifacts'])!=set(binding['paths'][key])):
                raise ControllerError('Accepted output binding changed')
        tasks[key]=current
    return binding,outputs,dict(run),active,completed,tasks


def recover_workflow(database,*,workflow_id,collector=None,trusted_issuers=None):
    """Fence interrupted work without making uncertain delivery claims.

    All ledger mutations commit atomically. Never settle reservations,
    revoke suspect leases, promote late DONE, resume or run code. Completed
    artifacts can be reverified with an explicit trusted evidence resolver.
    """
    if (collector is None)!=(trusted_issuers is None) or (collector is not None and
            (not callable(collector) or type(trusted_issuers) is not frozenset or not trusted_issuers)):
        raise ControllerError('Explicit evidence resolver and trust roots required together')
    with workflow_lock(database):
        c=Controller(database)
        with c._connection(write=True) as db:
            binding,outputs,run,active,completed,tasks=read_binding(c,db,workflow_id)
            if run['status']=='DONE':
                raise ControllerError('Completed workflow is not a recovery target')
            now=datetime.now(timezone.utc).isoformat()
            keys=sorted(tasks)
            marks=','.join('?' for _ in keys)
            db.execute("UPDATE outbox SET state='UNKNOWN',row_version=row_version+1,updated_at=? "
                       "WHERE state='DISPATCHING' AND task_id IN ("+marks+")",(now,*keys))
            db.execute("UPDATE leases SET status='SUSPECT' WHERE status='ACTIVE' AND task_id IN ("+marks+")",keys)
            for row in db.execute("SELECT idempotency_key,result_json FROM provider_attempts "
                                  "WHERE state IN ('RESERVED','SENT') AND task_id IN ("+marks+")",keys).fetchall():
                envelope=json.loads(row['result_json'])
                envelope['result'].update(verdict='UNAVAILABLE',attempt_state='UNKNOWN',
                    gaps=['Interrupted workflow; automatic retry forbidden'])
                db.execute("UPDATE provider_attempts SET state='UNKNOWN',result_json=? WHERE idempotency_key=?",
                           (_json(envelope),row['idempotency_key']))
            db.execute("UPDATE sequential_workflows SET status='HOLD' WHERE workflow_id=?",(workflow_id,))
            has_reservations=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='budget_reservations'").fetchone()
            reports={}
            for key,t in tasks.items():
                reports[key]={
                    'status':t['status'],'revision':t['revision'],'target_commit':t['target_commit'],
                    'effects':[dict(r) for r in db.execute('SELECT effect_id,state FROM outbox WHERE task_id=? ORDER BY effect_id',(key,))],
                    'leases':[dict(r) for r in db.execute("SELECT lease_id,status FROM leases WHERE task_id=? AND status IN ('ACTIVE','SUSPECT','EXPIRED') ORDER BY lease_id",(key,))],
                    'budgets':[dict(r) for r in db.execute('SELECT budget_id,used_tokens,reserved_tokens,used_cost,reserved_cost FROM budgets WHERE task_id=? ORDER BY budget_id',(key,))],
                    'reservations':[dict(r) for r in db.execute('SELECT attempt_id,tokens,cost FROM budget_reservations JOIN budgets USING(budget_id) WHERE task_id=? AND settlement IS NULL ORDER BY attempt_id',(key,))] if has_reservations else [],
                    'evidence_ids':[r[0] for r in db.execute('SELECT evidence_id FROM evidence WHERE task_id=? ORDER BY evidence_id',(key,))],
                    'output_check':'NOT_RUN'}
        # Verification errors must not undo the conservative fencing transaction.
        if collector is not None:
            from harness.runtime.handoff import verify_task_outputs
            for key,receipt in outputs.items():
                try:
                    verify_task_outputs(database,producer_id=key,producer_revision=receipt['revision'],
                        producer_repo=receipt['repo'],object_store=binding['object_store'],
                        expected_artifacts=receipt['artifacts'],collector=collector,trusted_issuers=trusted_issuers)
                    reports[key]['output_check']='PASS'
                except Exception:
                    reports[key]['output_check']='HOLD'
        return {'status':'HOLD','reason':'RECOVERY_REQUIRES_RECONCILIATION','workflow_id':workflow_id,
                'active_tasks':active,'completed':completed,'tasks':reports,'automatic_replay':False}


def fixture_evidence_collector(database,*,workflow_id):
    """Resolve local synthetic host attestations after a restart.

    Only accepted task receipts in the trusted private layout are eligible.
    This is not an independent or cryptographically authenticated issuer.
    Production callers must supply a separately trusted resolver.
    """
    c=Controller(database)
    with c._connection() as db:
        db.execute('BEGIN')
        binding,outputs,_,_,_,_=read_binding(c,db,workflow_id)
    root=Path(binding['workspace_root'])
    checks=('relevant_checks','basic_review','acceptance_coverage')
    locations={}
    for key,receipt in outputs.items():
        state=Path(receipt['repo']).parent
        if (state.parent!=root or Path(receipt['repo']).name!='integration-repo' or
                state.resolve(strict=True)!=state or state.stat().st_uid!=os.getuid() or
                state.stat().st_mode & 0o077):
            raise ControllerError('Invalid private fixture attestation location')
        for check in checks:
            ref='host:'+key+':'+check
            if ref in locations:
                raise ControllerError('Ambiguous local attestation reference')
            locations[ref]=(state,key,check)

    def read_private(state,name):
        if state.resolve(strict=True)!=state:
            raise ControllerError('Fixture attestation path changed')
        directory=os.open(state,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or
                        info.st_uid!=os.getuid() or info.st_mode & 0o022 or info.st_size>4*1024*1024):
                    raise ControllerError('Unsafe fixture attestation file')
                data=stream.read(4*1024*1024+1)
                if len(data)>4*1024*1024:
                    raise ControllerError('Oversized fixture attestation')
                return data
        finally:
            os.close(directory)

    def collect(reference):
        state,key,check=locations[reference]
        records=json.loads(read_private(state,'evidence.json'))
        matches=[r for r in records if r.get('attestation_ref')==reference]
        if (len(matches)!=1 or matches[0]['task_id']!=key or
                matches[0]['check_id']!=check or matches[0]['issuer_id']!='trial-host'):
            raise ControllerError('Invalid local fixture attestation binding')
        return TrustedEvidence(matches[0],read_private(state,check+'.artifact'))
    return collect
