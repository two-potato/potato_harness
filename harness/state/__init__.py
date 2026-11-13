"""Host-only durable effect ledger; this module never executes effects."""
import uuid
from harness.controller import Controller, ControllerError, _json, _now, _text
from harness.verifier import action_digest


class Outbox:
    def __init__(self, database):
        self.controller = Controller(database)

    def reserve(self, task_id, revision, action, key, approval_id=None):
        _text(key)
        if type(action) is not dict or type(revision) is not int:
            raise ControllerError('Action object and integer revision required')
        payload = _json(action)
        digest = action_digest(action)
        with self.controller._connection(write=True) as db:
            task = self.controller._read(db, task_id)
            if task['revision'] != revision or task['status'] in ('DONE', 'CANCELLED'):
                raise ControllerError('Stale or terminal task')
            prior = db.execute('SELECT * FROM outbox WHERE idempotency_key=?', (key,)).fetchone()
            if prior:
                if (prior['task_id'], prior['task_revision'], prior['action_digest'], prior['approval_id']) != (task_id, revision, digest, approval_id):
                    raise ControllerError('Idempotency identity substituted')
                return prior['effect_id']
            if approval_id is not None:
                self._approval(db,approval_id,task_id,revision,digest)
            effect = str(uuid.uuid4()); now = _now()
            db.execute('INSERT INTO outbox(effect_id,task_id,task_revision,idempotency_key,action_digest,approval_id,state,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?, ?,?,?)',
                       (effect, task_id, revision, key, digest, approval_id, 'PENDING', payload, now, now))
            return effect

    @staticmethod
    def _approval(db,approval_id,task_id,revision,digest):
        from harness.verifier import _date
        from datetime import datetime, timezone
        approval=db.execute('SELECT * FROM approvals WHERE approval_id=?',(approval_id,)).fetchone()
        if not approval or (approval['task_id'],approval['task_revision'],approval['action_digest'],approval['status'])!=(task_id,revision,digest,'APPROVED') or _date(approval['expires_at'])<=datetime.now(timezone.utc):
            raise ControllerError('Approval does not bind current action')

    def claim(self, effect_id):
        with self.controller._connection(write=True) as db:
            row = db.execute('SELECT * FROM outbox WHERE effect_id=?', (effect_id,)).fetchone()
            if not row: raise ControllerError('Unknown effect')
            task = self.controller._read(db, row['task_id'])
            # Reserving a future effect is not dispatch authority. Only a task
            # admitted to EXECUTING by the trusted controller may claim it.
            if task['revision'] != row['task_revision'] or task['status'] != 'EXECUTING':
                raise ControllerError('Task not in authorized EXECUTING state for dispatch')
            if row['approval_id'] is not None:self._approval(db,row['approval_id'],row['task_id'],row['task_revision'],row['action_digest'])
            return db.execute("UPDATE outbox SET state='DISPATCHING',row_version=row_version+1,updated_at=? WHERE effect_id=? AND state='PENDING'", (_now(),effect_id)).rowcount == 1

    def _resolve(self, effect_id, result, success, expected):
        if type(success) is not bool: raise ControllerError('Boolean result required')
        encoded = _json(result)
        with self.controller._connection(write=True) as db:
            state = 'SUCCEEDED' if success else 'FAILED'
            row = db.execute('SELECT * FROM outbox WHERE effect_id=?',(effect_id,)).fetchone()
            if row and row['state']==state and row['result_json']==encoded: return
            if not row or row['state'] != expected: raise ControllerError('Effect not in required state')
            db.execute('UPDATE outbox SET state=?,result_json=?,row_version=row_version+1,updated_at=? WHERE effect_id=?', (state,encoded,_now(),effect_id))

    def finish(self, effect_id, result, success):
        self._resolve(effect_id,result,success,'DISPATCHING')

    def mark_unknown(self, effect_id):
        with self.controller._connection(write=True) as db:
            changed=db.execute("UPDATE outbox SET state='UNKNOWN',row_version=row_version+1,updated_at=? WHERE effect_id=? AND state='DISPATCHING'",(_now(),effect_id))
            if changed.rowcount != 1: raise ControllerError('Only dispatched effects can become unknown')

    def reconcile(self, effect_id, result, success):
        """Host calls only after confirming actual external outcome; never retries."""
        self._resolve(effect_id,result,success,'UNKNOWN')

    def unresolved(self, task_id):
        with self.controller._connection() as db:
            return [r[0] for r in db.execute("SELECT effect_id FROM outbox WHERE task_id=? AND state IN ('PENDING','DISPATCHING','UNKNOWN') ORDER BY effect_id",(task_id,))]
