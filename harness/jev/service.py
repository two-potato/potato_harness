"""Single-send local authorization; no exactly-once provider delivery claim."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from jsonschema import Draft202012Validator
from harness.controller import Controller
from harness.verifier import action_digest, verify_bundle

ROOT=Path(__file__).resolve().parents[2]


class JevError(ValueError):
    pass


def _json(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def _result(task,phase,key,verdict,state,gaps):
    result={'schema_version':'3.0.1','task_id':task['task_id'],'task_revision':task['revision'],
            'phase':phase,'idempotency_key':key,'verdict':verdict,'gaps':gaps,
            'authoritative':False,'attempt_state':state}
    Draft202012Validator(json.loads((ROOT/'schemas/jev-result.schema.json').read_text())).validate(result)
    return result


class Jev:
    """Host-owned coordinator using an initialized controller database.

    provider(request) returns exactly {verdict, gaps}; never accept a worker's
    chosen provider. No provider means explicit UNAVAILABLE, without network IO.
    """
    def __init__(self,database,*,provider=None):
        self.database=Path(database).resolve()
        self.provider=provider

    def _connect(self):
        db=sqlite3.connect(self.database.as_uri()+'?mode=rw',uri=True,timeout=10,isolation_level=None)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def preflight(self,task_id):
        task=Controller(self.database).get_task(task_id)
        key='preflight:'+action_digest({'user_turn_id':task['user_turn_id']})
        return self._attempt(task,'PREFLIGHT',key,enabled=True)

    def completion(self,task_id,records,collector,*,trusted_issuers,enabled,
                   author_actor=None,author_session=None):
        if type(enabled) is not bool:
            raise JevError('Completion profile must be an explicit boolean')
        task=Controller(self.database).get_task(task_id)
        if task['status']!='COMPLETION_AUDITING':
            raise JevError('Completion advice requires COMPLETION_AUDITING')
        records=deepcopy(records)
        # Never replace this gate with a caller-supplied PASS boolean.
        verify_bundle(records,task,collector,trusted_issuers=trusted_issuers,
                      author_actor=author_actor,author_session=author_session)
        digest=action_digest({'records':sorted(records,key=lambda x:x['evidence_id'])})
        key='completion:'+action_digest({'task_id':task_id,'revision':task['revision'],
             'target_commit':task['target_commit'],'evidence_digest':digest,'policy_version':task['policy_version']})
        return self._attempt(task,'COMPLETION',key,enabled=enabled,evidence_digest=digest)

    def _attempt(self,task,phase,key,*,enabled,evidence_digest=None):
        request={'phase':phase,'summary':{'risk':task['risk'],'task_class':task['task_class'],
                 'scope_count':len(task['scope']),'acceptance_count':len(task['acceptance']),
                 'required_check_count':len(task['required_checks']),
                 'base_checks_passed':phase=='COMPLETION'},'evidence_digest':evidence_digest}
        db=self._connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT row_version,revision FROM tasks WHERE task_id=?',(task['task_id'],)).fetchone()
            if not current or tuple(current)!=(task['row_version'],task['revision']):
                raise JevError('Task changed before provider lookup')
            row=db.execute('SELECT * FROM provider_attempts WHERE idempotency_key=?',(key,)).fetchone()
            if row:
                envelope=json.loads(row['result_json'])
                result=envelope['result']
                if row['state'] in ('RESERVED','SENT'):
                    result=dict(result,verdict='UNAVAILABLE',attempt_state='UNKNOWN',
                                gaps=['Attempt in flight or interrupted; automatic retry forbidden'])
                db.commit()
                return result
            current=db.execute('SELECT row_version,revision FROM tasks WHERE task_id=?',(task['task_id'],)).fetchone()
            if not current or tuple(current)!=(task['row_version'],task['revision']):
                raise JevError('Task changed before provider reservation')
            terminal=not enabled or self.provider is None
            result=_result(task,phase,key,'UNAVAILABLE','UNAVAILABLE' if terminal else 'SENT',
                           ['SKIPPED_BY_POLICY'] if not enabled else ['Provider not configured'] if terminal else [])
            envelope={'request':request,'result':result,'provider':deepcopy(getattr(self.provider,'identity',{'provider':'not_configured' if self.provider is None else 'host_callback'}))}
            # Reservation and send authorization commit before calling the provider.
            db.execute('INSERT INTO provider_attempts VALUES(?,?,?,?,?,?,?)',
                       (key,task['task_id'],task['user_turn_id'],phase,result['attempt_state'],
                        _json(envelope),datetime.now(timezone.utc).isoformat()))
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
        if terminal:
            return result
        try:
            answer=self.provider(deepcopy(request))
            if (type(answer) is not dict or set(answer)!={'verdict','gaps'}
                    or answer['verdict'] not in ('CLEAR','REVIEW_RECOMMENDED','INCOMPLETE','UNAVAILABLE')
                    or type(answer['gaps']) is not list or len(answer['gaps'])>10
                    or any(type(x) is not str or not x.strip() or len(x)>256 for x in answer['gaps'])
                    or (answer['verdict']=='CLEAR' and answer['gaps'])):
                raise JevError('Invalid provider advice')
            result=_result(task,phase,key,answer['verdict'],'RESULT',answer['gaps'])
        except Exception:
            # Do not log credentials, prompts or provider response bodies.
            result=_result(task,phase,key,'UNAVAILABLE','UNKNOWN',['Provider delivery/result unknown; no automatic retry'])
        db=self._connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT row_version FROM tasks WHERE task_id=?',(task['task_id'],)).fetchone()
            if not current or current[0]!=task['row_version']:
                result=_result(task,phase,key,'UNAVAILABLE','UNKNOWN',['Task changed during provider call'])
            envelope['result']=result
            changed=db.execute("UPDATE provider_attempts SET state=?,result_json=? WHERE idempotency_key=? AND state='SENT'",
                               (result['attempt_state'],_json(envelope),key))
            if changed.rowcount!=1:
                raise JevError('Provider attempt changed; result not published')
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
        return result
