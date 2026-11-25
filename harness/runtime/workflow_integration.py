"""Explicit host-only composition of verified, disjoint completed outputs.

Produce a tested candidate commit in a fresh private repository. Never merge,
push, deploy, modify the source checkout, or use a model.
"""
import json
from pathlib import Path
import time

from harness.controller import Controller, ControllerError, _json
from harness.isolation.backend import BubblewrapBackend
from harness.runtime import _safe_edit, _snapshot, _write
from harness.runtime.handoff import verify_task_outputs, _git_blob
from harness.runtime.workflow_lifecycle import workflow_lock, read_binding
from harness.runtime.workspace import _git, _git_bytes, _source, _private_root, prepare_workspace
from harness.verifier import digest_bytes


def integrate_workflow(database,*,workflow_id,output_root,test_argv,collector,trusted_issuers,timeout=80):
    """Test a new private candidate; refuse overlapping outputs, even identical ones."""
    if (not callable(collector) or type(trusted_issuers) is not frozenset or not trusted_issuers or
            type(timeout) not in (int,float) or not 0<timeout<=120 or
            type(test_argv) is not list or not test_argv or
            any(type(v) is not str or '\0' in v for v in test_argv) or not test_argv[0].startswith('/')):
        raise ControllerError('Explicit trusted integration test, evidence and bounded timeout required')
    deadline=time.monotonic()+timeout
    def remaining():
        seconds=deadline-time.monotonic()
        if seconds<=0:
            raise ControllerError('Integration deadline exhausted')
        return seconds
    with workflow_lock(database):
        c=Controller(database)
        with c._connection() as db:
            db.execute('BEGIN')
            binding,outputs,run,active,completed,tasks=read_binding(c,db,workflow_id)
            if run['status']!='DONE' or active or set(completed)!=set(tasks):
                raise ControllerError('Integration requires fully accepted workflow')
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='budget_reservations'").fetchone():
                for key in tasks:
                    if db.execute('SELECT 1 FROM budget_reservations JOIN budgets USING(budget_id) '
                                  'WHERE task_id=? AND settlement IS NULL',(key,)).fetchone():
                        raise ControllerError('Integration requires reconciled budget reservations')
        bases={task['base_commit']['value'] for task in tasks.values()}
        if len(bases)!=1:
            raise ControllerError('Integration requires one common pinned base')
        base=bases.pop()
        source=_source(binding['source_repo'],base)
        root=_private_root(output_root,source)
        if any(root.iterdir()) or any(root.is_relative_to(Path(binding[k])) or
                Path(binding[k]).is_relative_to(root) for k in ('workspace_root','object_store')):
            raise ControllerError('Fresh isolated integration output root required')
        edits={}
        def recheck():
            for key in sorted(outputs):
                remaining()
                receipt=outputs[key]
                verify_task_outputs(database,producer_id=key,producer_revision=receipt['revision'],
                    producer_repo=receipt['repo'],object_store=binding['object_store'],
                    expected_artifacts=receipt['artifacts'],collector=collector,trusted_issuers=trusted_issuers)
        recheck()
        for key,receipt in sorted(outputs.items()):
            remaining()
            repo=receipt['repo']
            target=receipt['commit']
            if _git(repo,'rev-list','--parents','-n','1',target).split()!=[target,base]:
                raise ControllerError('Task candidate must have exact common base parent')
            diff={v.decode() for v in _git_bytes(repo,'diff-tree','--no-commit-id','--name-only','-r','-z',base,target).split(b'\0') if v}
            if diff!=set(receipt['artifacts']):
                raise ControllerError('Task candidate contains unapproved Git changes')
            for path,digest in receipt['artifacts'].items():
                if path in edits:
                    raise ControllerError('Conflicting workflow output path: '+path)
                base_mode=_git(repo,'--literal-pathspecs','ls-tree',base,'--',path).split()[0]
                mode=_git(repo,'--literal-pathspecs','ls-tree',target,'--',path).split()[0]
                data=_git_blob(repo,target,path)
                if mode!=base_mode or mode not in ('100644','100755') or digest_bytes(data)!=digest:
                    raise ControllerError('Task output mode or digest changed')
                edits[path]=(data,mode)
        with c._connection(write=True) as db:
            db.execute("CREATE TABLE IF NOT EXISTS workflow_integrations("
                       "workflow_id TEXT PRIMARY KEY REFERENCES sequential_workflows(workflow_id),"
                       "status TEXT NOT NULL CHECK(status IN ('RUNNING','HOLD','DONE')),"
                       "receipt_json TEXT NOT NULL CHECK(json_valid(receipt_json)))")
            if db.execute('SELECT 1 FROM workflow_integrations WHERE workflow_id=?',(workflow_id,)).fetchone():
                raise ControllerError('Integration already attempted; inspect, never replay')
            db.execute('INSERT INTO workflow_integrations VALUES(?,?,?)',
                       (workflow_id,'RUNNING',_json({'root':str(root),'base':base})))
        def save(status,receipt):
            with c._connection(write=True) as db:
                db.execute('UPDATE workflow_integrations SET status=?,receipt_json=? WHERE workflow_id=?',
                           (status,_json(receipt),workflow_id))
            return {'status':status,**receipt}
        try:
            remaining()
            layout=prepare_workspace(source,base,sorted(edits),root)
            workspace=Path(layout['workspace'])
            candidate=Path(layout['integration_repo'])
            for path,(data,mode) in sorted(edits.items()):
                remaining()
                _safe_edit(workspace,path,data)
                _safe_edit(candidate,path,data)
                blob=_git(candidate,'hash-object','-w','--no-filters','--',path)
                _git(candidate,'update-index','--cacheinfo',mode,blob,path)
            before=_snapshot(workspace)
            tree=_git(candidate,'write-tree')
            test=BubblewrapBackend().run(workspace,test_argv,timeout=remaining())
            test_bytes=_json(test).encode()
            (root/'integration-test.json').write_bytes(test_bytes)
            after=_snapshot(workspace)
            if test.get('returncode')!=0 or test.get('timed_out') is not False or any(after.get(k)!=v for k,v in before.items()):
                raise ControllerError('Integration test failed or changed pinned inputs')
            recheck()
            _source(source,base)
            remaining()
            target=_git(candidate,'-c','user.name=Potato Integration Host','-c','user.email=integration@localhost.invalid',
                        'commit-tree',tree,'-p',base,'-m','Verified workflow candidate')
            for path,(data,_) in edits.items():
                if _git_blob(candidate,target,path)!=data:
                    raise ControllerError('Integrated candidate does not match tested output')
            remaining()
            _git(candidate,'update-ref','--no-deref','HEAD',target)
            receipt={'workflow_id':workflow_id,'root':str(root),'candidate_repo':str(candidate),'base':base,
                     'candidate_sha':target,'test_digest':digest_bytes(test_bytes),
                     'tasks':sorted(tasks),'paths':sorted(edits),'merged':False}
            _write(root/'integration-result.json',receipt)
            remaining()
            return save('DONE',receipt)
        except Exception:
            return save('HOLD',{'workflow_id':workflow_id,'root':str(root),'base':base,
                                'reason':'INTEGRATION_NOT_ACCEPTED','merged':False})
