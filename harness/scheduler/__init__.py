"""Bounded deterministic ready selection, not a worker dispatcher."""
import hashlib
import json
from pathlib import Path
from harness.controller import Controller, ControllerError


class Scheduler:
    def __init__(self,database,*,dependency_verified=lambda task_id:False,max_ready=64):
        if type(max_ready) is not int or max_ready<1:raise ControllerError('Positive ready bound required')
        self.controller=Controller(database)
        self.dependency_verified=dependency_verified
        self.max_ready=max_ready

    def ready(self,dag):
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
            tasks={key:self.controller._read(db,n['task_id']) for key,n in by_id.items()}
            selected=[]
            for key,node in by_id.items():
                task=tasks[key]
                if set(task['depends_on'])!={by_id[n]['task_id'] for n in node['needs']}:raise ControllerError('Task dependencies disagree with graph')
                if task['status'] not in ('PLANNED','REPAIR'):continue
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
