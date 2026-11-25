"""Host-only task workspace preparation from pinned Git blobs.

No model calls, grants, task transitions or worker execution. Distinct copies
are not OS isolation; the caller must still enforce the existing sandbox and
revalidate task/lease bindings before dispatch.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from harness.controller import Controller, _json
from harness.policy import _parts
from harness.scheduler import SPECIALISTS

MAX_BYTES=1024*1024
MAX_SOURCE_BYTES=32*MAX_BYTES
MAX_SOURCE_FILES=4096
GIT_ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1',
         'GIT_CONFIG_GLOBAL':'/dev/null','GIT_NO_REPLACE_OBJECTS':'1'}


def _git_bytes(repo,*args):
    return subprocess.check_output(['/usr/bin/git','-c','core.hooksPath=/dev/null',
                                    '-c','core.fsmonitor=false','-C',str(repo),*args],
                                   env=GIT_ENV)


def _git(repo,*args):
    return _git_bytes(repo,*args).decode().strip()


def repository_identity(repo):
    return 'sha256:'+hashlib.sha256(str(Path(repo).resolve(strict=True)).encode()).hexdigest()


def _private_root(root,repo):
    root=Path(root).absolute()
    if (not root.is_dir() or root.resolve(strict=True)!=root or
            root.stat().st_uid!=os.getuid() or root.stat().st_mode & 0o077):
        raise ValueError('Existing private nonsymlink workspace root required')
    if root.is_relative_to(repo):
        raise ValueError('Workspace root must be outside repository')
    return root


def _source(repo,base):
    repo=Path(repo).resolve(strict=True)
    if type(base) is not str or not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}',base):
        raise ValueError('Pinned base SHA required')
    if Path(_git(repo,'rev-parse','--show-toplevel')).resolve()!=repo:
        raise ValueError('Exact repository root required')
    if _git(repo,'status','--porcelain') or _git(repo,'rev-parse','HEAD')!=base:
        raise ValueError('Trusted repository must be clean at pinned base SHA')
    return repo


def prepare_workspace(repo,base,scope,root):
    """Populate a new, empty private host-owned layout. Retain failures for inspection."""
    repo=_source(repo,base)
    root=_private_root(root,repo)
    if any(root.iterdir()):
        raise ValueError('Workspace layout must be empty; never reuse partial preparation')
    if type(scope) is not list or not scope:
        raise ValueError('Exact file scope required')
    for name in scope:
        _parts(name)
    if len(scope)!=len(set(scope)):
        raise ValueError('Duplicate scope path')
    # First inspect all tracked entries. No Git checkout, filters, symlinks,
    # hardlinks, submodules or ignored/untracked files reach the workspace.
    entries=_git_bytes(repo,'ls-tree','-rz','--full-tree',base).split(b'\0')
    if len(entries)-1>MAX_SOURCE_FILES:
        raise ValueError('Source exceeds trial file count')
    blobs=[]
    total=0
    for entry in entries:
        if not entry:
            continue
        header,encoded_name=entry.split(b'\t',1)
        mode,kind,blob=header.decode().split()
        name=encoded_name.decode('utf-8')
        parts=_parts(name)
        if kind!='blob' or mode not in ('100644','100755'):
            raise ValueError('Only regular tracked source files allowed')
        size=int(_git(repo,'cat-file','-s',blob))
        total+=size
        if size>MAX_BYTES or total>MAX_SOURCE_BYTES:
            raise ValueError('Source exceeds trial byte bounds')
        blobs.append((name,parts,mode,blob,size))
    if not set(scope)<={entry[0] for entry in blobs}:
        raise ValueError('Trial scope must name existing tracked files')
    workspace=root/'workspace'
    integration=root/'integration-repo'
    workspace.mkdir(mode=0o700)
    integration.mkdir(mode=0o700)
    for _,parts,mode,blob,size in blobs:
        content=_git_bytes(repo,'cat-file','blob',blob)
        if len(content)!=size:
            raise ValueError('Git blob size changed during preparation')
        target=workspace.joinpath(*parts)
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as output:
            output.write(content)
        target.chmod(0o755 if mode=='100755' else 0o644)
        other=integration.joinpath(*parts)
        other.parent.mkdir(parents=True,exist_ok=True)
        # Physical copy, not a hardlink or shared writable checkout.
        shutil.copyfile(target,other)
        other.chmod(0o755 if mode=='100755' else 0o644)
    _git(repo,'bundle','create',str(root/'base.bundle'),'HEAD')
    _git(integration,'init','--object-format='+('sha1' if len(base)==40 else 'sha256'))
    _git(integration,'fetch',str(root/'base.bundle'),'HEAD')
    if _git(integration,'rev-parse','FETCH_HEAD')!=base:
        raise ValueError('Source HEAD changed during workspace preparation')
    # Index and detached HEAD are pinned without checking out filtered files.
    _git(integration,'read-tree',base)
    _git(integration,'update-ref','--no-deref','HEAD',base)
    _source(repo,base)
    return {'workspace':str(workspace),'integration_repo':str(integration),'base_sha':base}


def prepare_task_workspace(database,root,repo,task_id,revision):
    """Prepare one immutable task/revision layout from trusted persisted metadata.

    Root is host-managed, never a model path. No automatic reuse or repair.
    The binding receipt is descriptive, not a capability or an approval.
    """
    if type(task_id) is not str or not task_id.strip() or type(revision) is not int or revision<0:
        raise ValueError('Exact task identity and revision required')
    controller=Controller(database)
    task=controller.get_task(task_id)
    if (task['revision']!=revision or task['status'] not in ('PLANNED','REPAIR','ASSIGNED') or
            task['owner'] not in SPECIALISTS or task['repository_id']!=repository_identity(repo)):
        raise ValueError('Task is not eligible for workspace preparation')
    base=task['base_commit']['value']
    repo=_source(repo,base)
    root=_private_root(root,repo)
    binding={key:task[key] for key in ('task_id','revision','owner','repository_id','workflow_id','scope','base_commit')}
    workspace_id='task-'+hashlib.sha256(_json(binding).encode()).hexdigest()
    directory=root/workspace_id
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError as error:
        raise ValueError('Task workspace already exists; inspect or reconcile, never reuse') from error
    layout=prepare_workspace(repo,base,task['scope'],directory)
    # No dispatch follows this check automatically. If state changed during
    # Git work, retain the incomplete directory without a prepared receipt.
    if controller.get_task(task_id)!=task:
        raise ValueError('Task changed during workspace preparation')
    receipt={**binding,**layout,'workspace_id':workspace_id}
    with (directory/'binding.json').open('x') as output:
        output.write(_json(receipt))
        output.flush()
        os.fsync(output.fileno())
    return receipt
