"""Read-only host-side dependency handoff for bounded Git workflows.

The host supplies an explicit path/digest allowlist, current task revisions,
private object store, producer Git object database and trusted evidence resolver.
No agent path, grant, publication, state transition or worker launch is accepted.
The result is inert context data, not permission to modify a dependency.
"""
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from harness.controller import Controller, ControllerError
from harness.policy import _parts
from harness.runtime.workspace import _git, _git_bytes, MAX_BYTES
from harness.scheduler import SPECIALISTS
from harness.verifier import digest_bytes, verify_bundle

MAX_HANDOFF_FILES=32
MAX_HANDOFF_BYTES=2*MAX_BYTES
MAX_EVIDENCE_RECORDS=128


class HandoffError(ControllerError):
    pass


def _read_object(directory,digest):
    name=digest.split(':')[1]
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or
                info.st_uid!=os.getuid() or info.st_mode & 0o022 or info.st_size>MAX_BYTES):
            raise HandoffError('Unsafe dependency object')
        data=stream.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES or digest_bytes(data)!=digest:
        raise HandoffError('Dependency object digest mismatch')
    return data


def _git_blob(repo,commit,path):
    if _git(repo,'cat-file','-t',commit)!='commit':
        raise HandoffError('Dependency target is not a Git commit')
    # Literal pathspec: no wildcard/magic expansion of host-approved names.
    entries=_git_bytes(repo,'--literal-pathspecs','ls-tree','-z',commit,'--',path).split(b'\0')
    if len(entries)!=2 or entries[-1]!=b'':
        raise HandoffError('Expected exactly one tracked dependency file')
    header,name=entries[0].split(b'\t',1)
    mode,kind,blob=header.decode().split()
    if name.decode()!=path or kind!='blob' or mode not in ('100644','100755'):
        raise HandoffError('Dependency must be a regular Git blob')
    if int(_git(repo,'cat-file','-s',blob))>MAX_BYTES:
        raise HandoffError('Dependency Git blob exceeds bound')
    data=_git_bytes(repo,'cat-file','blob',blob)
    if len(data)>MAX_BYTES:
        raise HandoffError('Dependency Git blob exceeds bound')
    return data


def _verify_completed(db,task,collector,trusted_issuers,author_actor,author_session):
    if db.execute("SELECT 1 FROM outbox WHERE task_id=? AND state IN ('PENDING','DISPATCHING','UNKNOWN')",(task['task_id'],)).fetchone():
        raise HandoffError('Dependency has unresolved effects')
    if db.execute("SELECT 1 FROM leases WHERE task_id=? AND status IN ('ACTIVE','SUSPECT')",(task['task_id'],)).fetchone():
        raise HandoffError('Dependency has unreconciled leases')
    rows=db.execute('SELECT * FROM evidence WHERE task_id=? AND task_revision=? LIMIT ?',
                    (task['task_id'],task['revision'],MAX_EVIDENCE_RECORDS+1)).fetchall()
    if not rows or len(rows)>MAX_EVIDENCE_RECORDS:
        raise HandoffError('Missing or excessive dependency evidence')
    records=[]
    for row in rows:
        record=json.loads(row['record_json'])
        if (row['evidence_id'],row['commit_sha'],row['artifact_digest'],row['attestation_ref'])!=(
                record['evidence_id'],record['commit']['value'],record['artifact_digest'],record['attestation_ref']):
            raise HandoffError('Dependency evidence columns disagree')
        records.append(record)
    verify_bundle(records,task,collector,trusted_issuers=trusted_issuers,
                  author_actor=author_actor,author_session=author_session)


def _publication(db,producer,path,digest):
    # This increment supports publication before target pinning, as used by
    # the bounded runtime. Do not accept an arbitrary revision-minus-one row.
    revision=producer['revision']
    pins=db.execute("SELECT payload_json FROM events WHERE task_id=? AND revision=? AND event_type='pin_target'",
                    (producer['task_id'],revision)).fetchall()
    if len(pins)!=1:
        raise HandoffError('Missing exact dependency pin event')
    pin=json.loads(pins[0][0])
    if revision<1 or pin.get('previous_revision')!=revision-1 or pin.get('target_commit')!=producer['target_commit']:
        raise HandoffError('Dependency publication revision not pinned')
    rows=db.execute(
        'SELECT p.receipt,l.* FROM artifact_publications p JOIN leases l ON p.lease_id=l.lease_id '
        'WHERE l.task_id=? AND l.task_revision=? AND p.path=? AND p.digest=? LIMIT 2',
        (producer['task_id'],revision-1,path,digest)).fetchall()
    if len(rows)!=1:
        raise HandoffError('Missing or ambiguous dependency publication')
    row=rows[0]
    receipt=json.loads(row['receipt'])
    expected={'lease_id':row['lease_id'],'task_id':producer['task_id'],
              'task_revision':revision-1,'fencing_token':row['fencing_token'],
              'path':path,'digest':digest}
    if (row['status']!='REVOKED' or row['repository_id']!=producer['repository_id'] or
            any(receipt.get(k)!=v for k,v in expected.items())):
        raise HandoffError('Dependency publication binding mismatch')
    if not db.execute("SELECT 1 FROM lease_claims WHERE lease_id=? AND kind='path' AND resource_key=?",
                      (row['lease_id'],path)).fetchone():
        raise HandoffError('Dependency publication not bound to exact lease path')
    return receipt


def dependency_segments(database,*,receiver_id,receiver_revision,producer_id,
                        producer_revision,producer_repo,object_store,expected_artifacts,
                        collector,trusted_issuers,author_actor=None,author_session=None):
    """Return bounded mandatory untrusted segments for one direct dependency.

    This is a read snapshot, not a dispatch authorization. Revalidate at use.
    No automatic merge or working-tree write occurs. All paths, identities,
    allowlists and trust roots are host inputs, not model claims.
    """
    try:
        return _segments(database,receiver_id,receiver_revision,producer_id,producer_revision,
                         producer_repo,object_store,expected_artifacts,collector,trusted_issuers,
                         author_actor,author_session)
    except HandoffError:
        raise
    except (ValueError,TypeError,KeyError,OSError,subprocess.SubprocessError) as exc:
        raise HandoffError('Dependency handoff verification failed') from exc
    except Exception as exc:
        raise HandoffError('Dependency handoff unavailable') from exc


def _segments(database,receiver_id,receiver_revision,producer_id,producer_revision,
              producer_repo,object_store,expected,collector,issuers,author_actor,author_session):
    if (not all(type(v) is str and v.strip() for v in (receiver_id,producer_id)) or receiver_id==producer_id or
            any(type(v) is not int or v<0 for v in (receiver_revision,producer_revision)) or
            type(expected) is not dict or not 1<=len(expected)<=MAX_HANDOFF_FILES or
            not callable(collector) or type(issuers) is not frozenset or not issuers):
        raise HandoffError('Explicit trusted dependency bindings required')
    for path,digest in expected.items():
        _parts(path)
        if type(digest) is not str or not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):
            raise HandoffError('Expected dependency digest required')
    store=Path(object_store).absolute()
    if (store.resolve(strict=True)!=store or not store.is_dir() or
            store.stat().st_uid!=os.getuid() or store.stat().st_mode & 0o077):
        raise HandoffError('Private host object store required')
    repo=Path(producer_repo).absolute()
    if repo.resolve(strict=True)!=repo or not repo.is_dir():
        raise HandoffError('Trusted producer Git directory required')
    c=Controller(database)
    with c._connection() as db:
        db.execute('BEGIN')
        receiver=c._read(db,receiver_id)
        producer=c._read(db,producer_id)
        if (receiver['revision']!=receiver_revision or producer['revision']!=producer_revision or
                receiver['status'] not in ('PLANNED','REPAIR','ASSIGNED') or producer['status']!='DONE' or
                receiver['owner'] not in SPECIALISTS or producer['owner'] not in SPECIALISTS or
                producer_id not in receiver['depends_on'] or
                any(receiver[k]!=producer[k] for k in ('workflow_id','user_turn_id','repository_id')) or
                not set(expected)<=set(producer['scope'])):
            raise HandoffError('Dependency is not approved for this receiver')
        _verify_completed(db,producer,collector,issuers,author_actor,author_session)
        directory=os.open(store,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            result=[]
            total=0
            commit=producer['target_commit']['value']
            for path,digest in sorted(expected.items()):
                receipt=_publication(db,producer,path,digest)
                if receipt.get('object_path')!=str(store/digest.split(':')[1]):
                    raise HandoffError('Dependency object store binding mismatch')
                data=_read_object(directory,digest)
                if _git_blob(repo,commit,path)!=data:
                    raise HandoffError('Published dependency differs from verified Git target')
                total+=len(data)
                if total>MAX_HANDOFF_BYTES:
                    raise HandoffError('Dependency context exceeds byte bound')
                # compile_context treats this JSON as opaque data and redacts it.
                payload={'producer_id':producer_id,'producer_revision':producer_revision,
                         'commit':commit,'path':path,'digest':digest,'content':data.decode('utf-8')}
                result.append({'name':'dependency:'+producer_id+':'+path,
                               'text':json.dumps(payload,sort_keys=True,ensure_ascii=False),
                               'mandatory':True,'trust':'untrusted'})
            return result
        finally:
            os.close(directory)
