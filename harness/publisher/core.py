"""Trusted content-addressed receiver. Workers never mount the object store."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from harness.policy import _parts
from harness.verifier import _date

class PublicationError(ValueError):
    pass

class Publisher:
    def __init__(self,database,store):
        self.database=Path(database).resolve()
        self.store=Path(store).absolute()
        if any(p.is_symlink() for p in (self.store,*self.store.parents)):
            raise PublicationError('Object store cannot contain symlinks')
        self.store.mkdir(mode=0o700,parents=True,exist_ok=True)
        if not self.store.is_dir():raise PublicationError('Private object directory required')
        info=self.store.stat()
        if info.st_uid!=os.getuid() or info.st_mode & 0o022:
            raise PublicationError('Object store must be host-owned and not group/world writable')
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE IF NOT EXISTS artifact_publications (lease_id TEXT NOT NULL, path TEXT NOT NULL, digest TEXT NOT NULL, receipt TEXT NOT NULL, PRIMARY KEY(lease_id,path,digest))')

    def publish(self,*,lease_id,worker_session_id,workspace_id,fencing_token,path,artifact,expected_digest):
        try:return self._publish(lease_id,worker_session_id,workspace_id,fencing_token,path,artifact,expected_digest)
        except PublicationError:raise
        except Exception as exc:raise PublicationError('Publication validation or storage failed') from exc

    def _publish(self,lease_id,session,workspace,fence,path,artifact,digest):
        parts=_parts(path)
        if type(artifact) is not bytes or len(artifact)>1048576:raise PublicationError('Artifact must be bounded bytes')
        actual='sha256:'+hashlib.sha256(artifact).hexdigest()
        if digest!=actual or type(fence) is not int:raise PublicationError('Digest/fence mismatch')
        db=sqlite3.connect(self.database.as_uri()+'?mode=rw',uri=True,isolation_level=None,timeout=10);db.row_factory=sqlite3.Row
        directory=None
        try:
            db.execute('BEGIN IMMEDIATE')
            lease=db.execute('SELECT * FROM leases WHERE lease_id=?',(lease_id,)).fetchone()
            if not lease or lease['status']!='ACTIVE' or _date(lease['expires_at'])<=datetime.now(timezone.utc):raise PublicationError('Lease unavailable or expired')
            if (lease['worker_session_id'],lease['workspace_id'],lease['fencing_token'])!=(session,workspace,fence):raise PublicationError('Lease binding mismatch')
            task=db.execute('SELECT * FROM tasks WHERE task_id=?',(lease['task_id'],)).fetchone()
            if not task or task['revision']!=lease['task_revision'] or task['repository_id']!=lease['repository_id'] or task['state']!='EXECUTING':raise PublicationError('Task no longer permits publication')
            snapshot=json.loads(task['task_json'])
            if snapshot['revision']!=task['revision'] or snapshot['status']!=task['state']:raise PublicationError('Corrupt task snapshot')
            claims=[row[0] for row in db.execute("SELECT resource_key FROM lease_claims WHERE lease_id=? AND kind='path'",(lease_id,))]
            if not any(parts[:len(_parts(prefix))]==_parts(prefix) for prefix in claims):raise PublicationError('Artifact outside lease claims')
            if not any(parts[:len(_parts(prefix))]==_parts(prefix) for prefix in snapshot['scope']):raise PublicationError('Artifact outside task scope')
            directory=os.open(self.store,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            name=digest.split(':')[1]
            try:
                fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400,dir_fd=directory)
            except FileExistsError:
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
                with os.fdopen(fd,'rb') as stream:
                    info=os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or stream.read(1048577)!=artifact:raise PublicationError('Existing object is corrupt or unsafe')
            else:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(artifact);stream.flush();os.fsync(stream.fileno())
                os.fsync(directory)
            if _date(lease['expires_at'])<=datetime.now(timezone.utc):
                raise PublicationError('Lease expired while storing artifact')
            receipt={'lease_id':lease_id,'task_id':task['task_id'],'task_revision':task['revision'],'fencing_token':fence,'path':path,'digest':digest,'object_path':str(self.store/name)}
            encoded=json.dumps(receipt,sort_keys=True)
            db.execute('INSERT OR IGNORE INTO artifact_publications VALUES(?,?,?,?)',(lease_id,path,digest,encoded))
            db.commit()
            return receipt
        except BaseException:
            db.rollback();raise
        finally:
            if directory is not None:os.close(directory)
            db.close()
