"""Bounded sequential orchestration, with an explicitly trusted host executor.

This is not a provider adapter or CLI. The executor must own grants, leases,
budget, isolation, publication and state transitions. No model or task data
may supply the executor, collector or trust roots. A workflow starts once;
recovery is conservative and never automatically replays a task.
"""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from datetime import datetime, timezone
from time import monotonic

from harness.controller import Controller, ControllerError, _json
from harness.leases import _overlap
from harness.runtime.handoff import dependency_segments, verify_task_outputs
from harness.runtime.workflow_lifecycle import workflow_lock
from harness.runtime.workspace import prepare_task_workspace, repository_identity
from harness.scheduler import Scheduler


class WorkflowDeadline:
    """Trusted host monotonic admission bound, not forcible thread cancellation."""

    def __init__(self, seconds=300):
        if type(seconds) not in (int,float) or not 0<seconds<=3600:
            raise ControllerError('Workflow wall time must be finite and in (0, 3600] seconds')
        self.seconds=seconds
        self.started_utc=datetime.now(timezone.utc).isoformat()
        self._end=monotonic()+seconds

    def expired(self):
        return monotonic()>=self._end

    def remaining(self):
        seconds=self._end-monotonic()
        if seconds<=0:
            raise ControllerError('Workflow deadline exhausted')
        return seconds


def run_sequential_workflow(database, **bindings):
    with workflow_lock(database):
        return _run_workflow(database,max_parallel=1,**bindings)


def run_parallel_workflow(database, *, max_parallel, **bindings):
    """Bounded batch execution for trusted thread-safe synthetic callbacks."""
    if type(max_parallel) is not int or not 2<=max_parallel<=8:
        raise ControllerError('Parallel width must be an integer from 2 to 8')
    with workflow_lock(database):
        return _run_workflow(database,max_parallel=max_parallel,**bindings)


def _run_workflow(database, *, dag, workflow_id, user_turn_id, repository_id,
                  approved_revisions, available_owners, repo, workspace_root,
                  object_store, output_paths, collector, trusted_issuers, execute,max_parallel,deadline=None):
    """Run one bounded workflow via a trusted host callback, never a worker tool.

    execute(task, layout, dependency_segments) returns a host-verified candidate
    path/digest map after completing the task through its normal gates. This
    coordinator independently rechecks persisted completion and output bytes.
    The callback must compile its final scoped context and authorize dispatch;
    no automatic merge or filesystem access to producer workspaces is granted.
    """
    deadline=WorkflowDeadline() if deadline is None else deadline
    if type(deadline) is not WorkflowDeadline:
        raise ControllerError('Trusted workflow deadline required')
    if not callable(execute) or not callable(collector) or type(trusted_issuers) is not frozenset or not trusted_issuers:
        raise ControllerError('Trusted host executor and evidence resolver required')
    if repository_identity(repo)!=repository_id:
        raise ControllerError('Source repository binding mismatch')
    dag=deepcopy(dag)
    revisions=deepcopy(approved_revisions)
    paths=deepcopy(output_paths)
    owners=tuple(available_owners) if type(available_owners) in (list,tuple,set,frozenset) else available_owners
    c=Controller(database)
    completed={}
    scheduler=Scheduler(database,dependency_verified=lambda task_id:task_id in completed,max_ready=64)

    def ready():
        return scheduler.ready_workflow(dag,workflow_id=workflow_id,user_turn_id=user_turn_id,
                repository_id=repository_id,approved_revisions=revisions,available_owners=owners)

    ready()  # Existing schema, graph and identity checks before recording a run.
    if type(paths) is not dict or set(paths)!=set(revisions):
        raise ControllerError('Exact host output path map required')
    initial={}
    for key in revisions:
        task=c.get_task(key)
        names=paths[key]
        if (task['status']!='PLANNED' or task['revision']!=revisions[key] or
                type(names) is not list or not names or len(names)>32 or
                any(type(p) is not str for p in names) or len(names)!=len(set(names)) or
                not set(names)<=set(task['scope'])):
            raise ControllerError('Fresh planned tasks and exact approved output paths required')
        initial[key]=task
    with c._connection(write=True) as db:
        db.execute("CREATE TABLE IF NOT EXISTS sequential_workflows(workflow_id TEXT PRIMARY KEY,"
                   "status TEXT NOT NULL CHECK(status IN ('RUNNING','HOLD','DONE')),"
                   "active_task TEXT,completed_json TEXT NOT NULL CHECK(json_valid(completed_json)))")
        if db.execute('SELECT 1 FROM sequential_workflows WHERE workflow_id=?',(workflow_id,)).fetchone():
            raise ControllerError('Workflow already started; inspect and reconcile, never replay')
        for key,task in initial.items():
            if c._read(db,key)!=task:
                raise ControllerError('Task changed before workflow claim')
        if max_parallel>1:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_budget_limits'").fetchone():
                raise ControllerError('Parallel workflow requires configured aggregate budget')
            limit=db.execute('SELECT * FROM workflow_budget_limits WHERE workflow_id=?',(workflow_id,)).fetchone()
            if (not limit or (limit['repository_id'],limit['user_turn_id'])!=(repository_id,user_turn_id) or
                    json.loads(limit['members_json'])!=revisions or limit['max_in_flight']<max_parallel):
                raise ControllerError('Parallel workflow requires matching aggregate budget and slots')
        db.execute("CREATE TABLE IF NOT EXISTS workflow_active_batches(workflow_id TEXT PRIMARY KEY REFERENCES sequential_workflows(workflow_id),active_json TEXT NOT NULL CHECK(json_valid(active_json)))")
        db.execute('INSERT INTO sequential_workflows VALUES(?,?,?,?)',(workflow_id,'RUNNING',None,'[]'))
        db.execute('INSERT INTO workflow_active_batches VALUES(?,?)',(workflow_id,'[]'))
        db.execute("CREATE TABLE IF NOT EXISTS workflow_deadlines("
                   "workflow_id TEXT PRIMARY KEY REFERENCES sequential_workflows(workflow_id),"
                   "limit_s REAL NOT NULL,started_utc TEXT NOT NULL,expired INTEGER NOT NULL CHECK(expired IN (0,1)))")
        db.execute('INSERT INTO workflow_deadlines VALUES(?,?,?,0)',
                   (workflow_id,deadline.seconds,deadline.started_utc))
        db.execute("CREATE TABLE IF NOT EXISTS workflow_bindings("
                   "workflow_id TEXT PRIMARY KEY REFERENCES sequential_workflows(workflow_id),"
                   "binding_json TEXT NOT NULL CHECK(json_valid(binding_json)),"
                   "outputs_json TEXT NOT NULL CHECK(json_valid(outputs_json)))")
        binding={'repository_id':repository_id,'user_turn_id':user_turn_id,
                 'members':initial,'paths':paths,'source_repo':str(Path(repo).resolve(strict=True)),
                 'workspace_root':str(Path(workspace_root).absolute()),
                 'object_store':str(Path(object_store).absolute())}
        db.execute('INSERT INTO workflow_bindings VALUES(?,?,?)',(workflow_id,_json(binding),'{}'))

    active=[]
    def save(status):
        first=active[0] if active else None
        with c._connection(write=True) as db:
            expired=deadline.expired()
            if expired:
                status='HOLD'
            db.execute('UPDATE workflow_deadlines SET expired=? WHERE workflow_id=?',
                       (int(expired),workflow_id))
            db.execute('UPDATE sequential_workflows SET status=?,active_task=?,completed_json=? WHERE workflow_id=?',
                       (status,first,_json(list(completed)),workflow_id))
            db.execute('UPDATE workflow_active_batches SET active_json=? WHERE workflow_id=?',
                       (_json(active),workflow_id))
            db.execute('UPDATE workflow_bindings SET outputs_json=? WHERE workflow_id=?',
                       (_json(completed),workflow_id))
        return {'status':status,'active_task':first,'active_tasks':list(active),'completed':list(completed),**({'reason':'WORKFLOW_DEADLINE'} if expired else {})}

    def check_output(task_id):
        previous=completed[task_id]
        verify_task_outputs(database,producer_id=task_id,producer_revision=revisions[task_id],
                            producer_repo=previous['repo'],object_store=object_store,
                            expected_artifacts=previous['artifacts'],collector=collector,
                            trusted_issuers=trusted_issuers)

    def select(candidates):
        batch=[]
        resources=[]
        for key in candidates:
            claims=[{'kind':'path','key':p} for p in initial[key]['scope']]
            if any(_overlap(a,b) for a in claims for b in resources):
                continue
            batch.append(key)
            resources.extend(claims)
            if len(batch)==max_parallel:
                break
        return batch

    def prepare(key):
        deadline.remaining()
        task=c.get_task(key)
        if task!=initial[key]:
            raise ControllerError('Unexpected task change before execution')
        layout=prepare_task_workspace(database,workspace_root,repo,key,revisions[key])
        segments=[]
        for predecessor in task['depends_on']:
            entry=completed[predecessor]
            segments.extend(dependency_segments(database,receiver_id=key,receiver_revision=revisions[key],
                producer_id=predecessor,producer_revision=revisions[predecessor],producer_repo=entry['repo'],
                object_store=object_store,expected_artifacts=entry['artifacts'],
                collector=collector,trusted_issuers=trusted_issuers))
        if c.get_task(key)!=task:
            raise ControllerError('Task changed during preparation')
        return task,layout,segments

    def accept(key,prepared,result):
        deadline.remaining()
        task,layout,_=prepared
        after=c.get_task(key)
        mutable={'status','revision','row_version','target_commit'}
        if (after['status']!='DONE' or after['revision']!=task['revision']+1 or
                {k:v for k,v in after.items() if k not in mutable}!={k:v for k,v in task.items() if k not in mutable} or
                type(result) is not dict or set(result)!=set(paths[key])):
            raise ControllerError('Executor did not complete the exact approved task')
        verify_task_outputs(database,producer_id=key,producer_revision=after['revision'],
            producer_repo=layout['integration_repo'],object_store=object_store,
            expected_artifacts=result,collector=collector,trusted_issuers=trusted_issuers)
        deadline.remaining()
        revisions[key]=after['revision']
        completed[key]={'repo':layout['integration_repo'],'artifacts':deepcopy(result),
                        'revision':after['revision'],'commit':after['target_commit']['value']}

    try:
        while len(completed)<len(initial):
            deadline.remaining()
            batch=select(ready())
            deadline.remaining()
            if not batch:
                return save('HOLD')
            active=list(batch)
            save('RUNNING')
            # Persist the entire admission set before touching any workspace.
            # All dependency reads and preparation happen on the coordinator.
            prepared={key:prepare(key) for key in batch}
            for key in batch:
                if c.get_task(key)!=prepared[key][0]:
                    raise ControllerError('Batch task changed before execution')
            def invoke(key):
                deadline.remaining()
                return execute(*deepcopy(prepared[key]))
            deadline.remaining()
            outcomes={}
            if len(batch)==1:
                key=batch[0]
                outcomes[key]=invoke(key)
            else:
                # No new batch while any admitted callback is running.
                # BaseException leaves the durable active list for reconciliation.
                with ThreadPoolExecutor(max_workers=max_parallel) as pool:
                    futures={key:pool.submit(invoke,key) for key in batch}
                    for key in batch:
                        try:
                            outcomes[key]=futures[key].result()
                        except Exception:
                            continue
            # Do not accept a late batch. Retain all unresolved admission IDs
            # even if a callback persisted DONE, for explicit recovery.
            deadline.remaining()
            # Only coordinator mutates completed and revisions, in DAG order.
            for key in batch:
                if key not in outcomes:
                    continue
                try:
                    accept(key,prepared[key],outcomes[key])
                except Exception:
                    continue
                active.remove(key)
            if active:
                return save('HOLD')
            save('RUNNING')
        for key in completed:
            deadline.remaining()
            check_output(key)
        deadline.remaining()
        return save('DONE')
    except Exception:
        # Never infer that an interrupted effect was not sent or replay it.
        return save('HOLD')
