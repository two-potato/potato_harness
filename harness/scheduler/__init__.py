"""Bounded deterministic ready selection, not a worker dispatcher."""
import hashlib
import json
from pathlib import Path
from harness.controller import Controller, ControllerError, ROOT
from jsonschema import Draft202012Validator

# Explore remains optional and is not an execution role in this increment.
SPECIALISTS = frozenset({'architect','backend','frontend','search','ml-recommendations','qa','devops-sre','security'})
MAX_WORKFLOW_NODES = 64


class Scheduler:
    def __init__(self,database,*,dependency_verified=lambda task_id:False,max_ready=64):
        if type(max_ready) is not int or max_ready<1:raise ControllerError('Positive ready bound required')
        self.controller=Controller(database)
        self.dependency_verified=dependency_verified
        self.max_ready=max_ready

    def ready_workflow(self, dag, *, workflow_id, user_turn_id, repository_id,
                       approved_revisions, available_owners):
        """Read-only selection of host-approved tasks in one workflow.

        All keyword bindings come from trusted host state, not a model.
        This is a queue snapshot, not an execution grant; dispatch must still
        revalidate revision, evidence, lease, budget and state guards.
        """
        if not all(type(v) is str and v.strip() for v in (workflow_id,user_turn_id,repository_id)):
            raise ControllerError('Trusted workflow identity required')
        if type(dag) is not dict or type(dag.get('nodes')) is not list or not 1 <= len(dag['nodes']) <= MAX_WORKFLOW_NODES:
            raise ControllerError('Bounded workflow graph required')
        validator = Draft202012Validator(json.loads((ROOT/'schemas/dag.schema.json').read_text()))
        if not validator.is_valid(dag) or dag['workflow_id'] != workflow_id:
            raise ControllerError('Invalid or mismatched workflow graph')
        if type(approved_revisions) is not dict or any(type(k) is not str or not k or type(v) is not int or v < 0 for k,v in approved_revisions.items()):
            raise ControllerError('Trusted task revision map required')
        if {n['task_id'] for n in dag['nodes']} != set(approved_revisions):
            raise ControllerError('Workflow differs from host-approved task set')
        if type(available_owners) not in (list,tuple,set,frozenset) or any(type(v) is not str for v in available_owners) or len(set(available_owners)) != len(available_owners) or not set(available_owners) <= SPECIALISTS:
            raise ControllerError('Unknown or duplicate available specialist')
        available = frozenset(available_owners)

        def validate_tasks(tasks):
            for task in tasks.values():
                if (task['workflow_id'],task['user_turn_id'],task['repository_id']) != (workflow_id,user_turn_id,repository_id):
                    raise ControllerError('Task belongs to a different workflow, turn or repository')
                if task['owner'] not in SPECIALISTS:
                    raise ControllerError('Task owner is not an admitted specialist')
                if task['revision'] != approved_revisions[task['task_id']]:
                    raise ControllerError('Task revision changed; revalidate approved workflow')

        return self._ready(dag, validate_tasks=validate_tasks, available=available)

    def ready(self,dag):
        """Legacy bounded selection; new workflow callers use ready_workflow."""
        return self._ready(dag)

    def _ready(self,dag,*,validate_tasks=None,available=None):
        nodes=dag.get('nodes',[])
        if not nodes:raise ControllerError('Graph empty')
        by_id={n['id']:n for n in nodes}
        if len(by_id)!=len(nodes) or len({n['task_id'] for n in nodes})!=len(nodes):raise ControllerError('Duplicate node or task')
        visited=set();visiting=set()
        def visit(node):
            if node in visiting:raise ControllerError('Graph cycle')
            if node in visited:return
            if node not in by_id:raise ControllerError('Missing dependency')
            visiting.add(node)
            needs=by_id[node]['needs']
            if len(set(needs))!=len(needs):raise ControllerError('Duplicate dependency')
            for need in needs:visit(need)
            visiting.remove(node);visited.add(node)
        for node in by_id:visit(node)
        with self.controller._connection() as db:
            # Read the task and evidence rows from one SQLite snapshot.
            db.execute('BEGIN')
            tasks={key:self.controller._read(db,n['task_id']) for key,n in by_id.items()}
            if validate_tasks is not None:validate_tasks(tasks)
            selected=[]
            for key,node in by_id.items():
                task=tasks[key]
                if set(task['depends_on'])!={by_id[n]['task_id'] for n in node['needs']}:raise ControllerError('Task dependencies disagree with graph')
                if task['status'] not in ('PLANNED','REPAIR'):continue
                if available is not None and task['owner'] not in available:continue
                valid=True
                for need in node['needs']:
                    predecessor=tasks[need]
                    if predecessor['status']!='DONE' or self.dependency_verified(predecessor['task_id']) is not True:
                        valid=False;break
                    evidence=db.execute('SELECT 1 FROM evidence WHERE task_id=? AND task_revision=? AND commit_sha=?',(predecessor['task_id'],predecessor['revision'],predecessor['target_commit']['value'])).fetchone()
                    if not evidence or not self._artifact(db,predecessor):valid=False;break
                if valid:selected.append(task['task_id'])
            return selected[:self.max_ready]

    @staticmethod
    def _artifact(db,task):
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifact_publications'").fetchone():return False
        for row in db.execute('SELECT receipt FROM artifact_publications'):
            receipt=json.loads(row[0])
            if receipt.get('task_id')!=task['task_id']:continue
            # Publications precede target pinning (which increments revision).
            if receipt.get('task_revision') not in (task['revision'],task['revision']-1):continue
            path=Path(receipt['object_path'])
            if path.is_file() and not path.is_symlink() and 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()==receipt['digest']:return True
        return False
