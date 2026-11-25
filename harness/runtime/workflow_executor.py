"""Synthetic-only workflow binding to the existing bounded task runtime.

The caller supplies a trusted in-process worker and host-approved test argv.
No CLI, external model adapter, independent reviewer or automatic merge is
introduced. Sandbox seams are explicit; the default is the existing Bubblewrap.
"""
from copy import deepcopy
import json
from pathlib import Path

from harness.controller import Controller, ControllerError
from harness.isolation.backend import BubblewrapBackend
from harness.runtime import _config, _lock, _run, _write
from harness.runtime.workflow import run_sequential_workflow
from harness.verifier import TrustedEvidence

CHECKS=['relevant_checks','basic_review','acceptance_coverage']


def run_fixture_workflow(database,*,dag,workflow_id,user_turn_id,repository_id,
                         approved_revisions,available_owners,repo,workspace_root,
                         object_store,test_argv_by_task,worker,sandbox_probe=None,sandbox_run=None):
    """Bind one fresh sequential workflow to the real host pipeline.

    This fixture API accepts no external provider configuration. Every task is
    LOW/BOUNDED, uses the existing configured-tests gate and must publish exactly
    its own scope. The trusted callback substitutes only the proposal source.
    """
    if (not callable(worker) or type(approved_revisions) is not dict or
            type(test_argv_by_task) is not dict or set(test_argv_by_task)!=set(approved_revisions)):
        raise ControllerError('Explicit fixture worker and task test commands required')
    database=Path(database).resolve(strict=True)
    root=Path(workspace_root).absolute()
    store=Path(object_store).absolute()
    c=Controller(database)
    configs={}
    initial={}
    output_paths={}
    with c._connection() as db:
        db.execute('BEGIN')
        for key,revision in approved_revisions.items():
            task=c._read(db,key)
            if (task['status']!='PLANNED' or task['revision']!=revision or
                    task['owner'] not in ('backend','frontend') or task['risk']!='LOW' or
                    task['task_class']!='BOUNDED' or task['policy_version']!='bounded-trial-3.0' or
                    task['required_checks']!=CHECKS or task['acceptance']!=[
                        {'id':'configured-tests','expected':task['objective'],'requires':CHECKS}]):
                raise ControllerError('Unsupported bounded workflow task')
            row=db.execute('SELECT * FROM budgets WHERE budget_id=?',(task['budget_id'],)).fetchone()
            if not row or row['task_id']!=key or row['revision']!=revision:
                raise ControllerError('Current task budget required')
            budget=json.loads(row['budget_json'])
            if budget['status']!='ACTIVE' or row['used_tokens'] or row['reserved_tokens'] or row['used_cost'] or row['reserved_cost']:
                raise ControllerError('Fresh task budget required')
            config=_config({'repo':str(Path(repo).resolve(strict=True)),'base_sha':task['base_commit']['value'],
                'model':'fixture/workflow','worker_command':['/usr/bin/false'],'scope':task['scope'],
                'test_argv':deepcopy(test_argv_by_task[key]),'objective':task['objective'],
                'budget':{'tokens':budget['token_hard'],'cost_usd':budget['cost_usd_hard'],
                          'estimate_cost_usd':budget['cost_usd_hard'],'wall_time_s':budget['wall_time_s_hard']},
                'output':str(root/'unused-fixture-output')})
            configs[key]=config
            initial[key]=task
            output_paths[key]=list(task['scope'])
    backend=BubblewrapBackend()
    probe=backend.probe if sandbox_probe is None else sandbox_probe
    sandbox=backend.run if sandbox_run is None else sandbox_run
    attestations={}

    def execute(task,layout,segments):
        key=task['task_id']
        if task!=initial[key]:
            raise ControllerError('Task changed since fixture configuration')
        state=Path(layout['workspace']).parent
        if (state.parent!=root or state.name!=layout['workspace_id'] or
                json.loads((state/'binding.json').read_text())!=layout):
            raise ControllerError('Prepared layout binding mismatch')
        config=deepcopy(configs[key])
        config['output']=str(state/'export')
        _write(state/'config.json',config)
        _write(state/'run.json',{'task_id':key,'state':'INITIALIZED','reason':'Workflow fixture',
                'trace':[],'lease_id':None,'grant':None,'provider_mode':'synthetic'})
        with _lock(state):
            result=_run(state,worker,probe,sandbox,workflow_binding={
                'database':database,'layout':layout,'task':task,'segments':segments,'object_store':store})
        if result['state']!='DONE' or result['task_status']!='DONE':
            raise ControllerError('Bounded runtime did not complete task')
        # The actual task runtime produced and verified these records. Resolve
        # bytes from host-only files; do not accept any worker attestations.
        records=json.loads((state/'evidence.json').read_text())
        for record in records:
            check=record['check_id']
            if check not in CHECKS or record['task_id']!=key:
                raise ControllerError('Unexpected evidence binding')
            ref=record['attestation_ref']
            if ref in attestations:
                raise ControllerError('Duplicate evidence reference')
            attestations[ref]=TrustedEvidence(record,(state/(check+'.artifact')).read_bytes())
        return {r['path']:r['digest'] for r in result['publications']}

    result=run_sequential_workflow(database,dag=dag,workflow_id=workflow_id,user_turn_id=user_turn_id,
            repository_id=repository_id,approved_revisions=approved_revisions,available_owners=available_owners,
            repo=repo,workspace_root=root,object_store=store,output_paths=output_paths,
            collector=attestations.__getitem__,trusted_issuers=frozenset({'trial-host'}),execute=execute)
    return {**result,'provider_mode':'synthetic'}
