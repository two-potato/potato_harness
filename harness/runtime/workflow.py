"""Bounded sequential orchestration, with an explicitly trusted host executor.

This is not a provider adapter or CLI. The executor must own grants, leases,
budget, isolation, publication and state transitions. No model or task data
may supply the executor, collector or trust roots. A workflow starts once;
crash recovery and automatic replay are deliberately not implemented.
"""
from copy import deepcopy
import json

from harness.controller import Controller, ControllerError, _json
from harness.runtime.handoff import dependency_segments, verify_task_outputs
from harness.runtime.workspace import prepare_task_workspace, repository_identity
from harness.scheduler import Scheduler


def run_sequential_workflow(database, *, dag, workflow_id, user_turn_id, repository_id,
                            approved_revisions, available_owners, repo, workspace_root,
                            object_store, output_paths, collector, trusted_issuers, execute):
    """Run one bounded workflow via a trusted host callback, never a worker tool.

    execute(task, layout, dependency_segments) returns a host-verified candidate
    path/digest map after completing the task through its normal gates. This
    coordinator independently rechecks persisted completion and output bytes.
    The callback must compile its final scoped context and authorize dispatch;
    no automatic merge or filesystem access to producer workspaces is granted.
    """
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
    scheduler=Scheduler(database,dependency_verified=lambda task_id:task_id in completed,max_ready=1)

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
        db.execute('INSERT INTO sequential_workflows VALUES(?,?,?,?)',(workflow_id,'RUNNING',None,'[]'))

    active=None
    def save(status):
        with c._connection(write=True) as db:
            db.execute('UPDATE sequential_workflows SET status=?,active_task=?,completed_json=? WHERE workflow_id=?',
                       (status,active,_json(list(completed)),workflow_id))
        return {'status':status,'active_task':active,'completed':list(completed)}

    def check_output(task_id):
        previous=completed[task_id]
        verify_task_outputs(database,producer_id=task_id,producer_revision=revisions[task_id],
                            producer_repo=previous['repo'],object_store=object_store,
                            expected_artifacts=previous['artifacts'],collector=collector,
                            trusted_issuers=trusted_issuers)

    try:
        while len(completed)<len(initial):
            candidates=ready()
            if not candidates:
                return save('HOLD')
            active=candidates[0]
            save('RUNNING')
            task=c.get_task(active)
            if task!=initial[active]:
                raise ControllerError('Unexpected task change before execution')
            layout=prepare_task_workspace(database,workspace_root,repo,active,revisions[active])
            segments=[]
            for predecessor in task['depends_on']:
                entry=completed[predecessor]
                segments.extend(dependency_segments(database,receiver_id=active,receiver_revision=revisions[active],
                    producer_id=predecessor,producer_revision=revisions[predecessor],producer_repo=entry['repo'],
                    object_store=object_store,expected_artifacts=entry['artifacts'],
                    collector=collector,trusted_issuers=trusted_issuers))
            if c.get_task(active)!=task:
                raise ControllerError('Task changed during preparation')
            result=execute(deepcopy(task),deepcopy(layout),deepcopy(segments))
            after=c.get_task(active)
            # Only the normal single target-pin revision is admitted. Changes
            # to scope/owner/plan require a new host-approved workflow.
            mutable={'status','revision','row_version','target_commit'}
            if (after['status']!='DONE' or after['revision']!=task['revision']+1 or
                    {k:v for k,v in after.items() if k not in mutable}!={k:v for k,v in task.items() if k not in mutable} or
                    type(result) is not dict or set(result)!=set(paths[active])):
                raise ControllerError('Executor did not complete the exact approved task')
            verify_task_outputs(database,producer_id=active,producer_revision=after['revision'],
                producer_repo=layout['integration_repo'],object_store=object_store,
                expected_artifacts=result,collector=collector,trusted_issuers=trusted_issuers)
            revisions[active]=after['revision']
            completed[active]={'repo':layout['integration_repo'],'artifacts':deepcopy(result)}
            active=None
            save('RUNNING')
        for key in completed:
            check_output(key)
        return save('DONE')
    except Exception:
        # Keep a durable HOLD and never infer that an effect was not sent.
        # Existing task recovery owns the external effect and lease ledger.
        return save('HOLD')
