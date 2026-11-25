"""Finite host-owned reservation accounting, serialized across local processes."""
import json
import math
import time
from collections import Counter
from decimal import Decimal
from jsonschema import Draft202012Validator
from harness.controller import Controller, ControllerError, ROOT, _json, _text


def _amount(value, integer=False):
    if (type(value) is not int if integer else type(value) not in (int,float)) or not math.isfinite(value) or value < 0:
        raise ControllerError('Finite nonnegative amount required')


class Budget:
    def __init__(self,database):
        self.controller=Controller(database)
        with self.controller._connection(write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS budget_reservations(attempt_id TEXT PRIMARY KEY,budget_id TEXT NOT NULL REFERENCES budgets(budget_id),tokens INTEGER NOT NULL,cost REAL NOT NULL,settlement TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS budget_clocks(budget_id TEXT PRIMARY KEY REFERENCES budgets(budget_id),started REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS workflow_budget_limits(workflow_id TEXT PRIMARY KEY,repository_id TEXT NOT NULL,user_turn_id TEXT NOT NULL,members_json TEXT NOT NULL CHECK(json_valid(members_json)),token_hard INTEGER NOT NULL,cost_hard TEXT NOT NULL,max_in_flight INTEGER NOT NULL)')

    def configure_workflow(self, *, workflow_id, repository_id, user_turn_id,
                           approved_revisions, token_hard, cost_usd_hard, max_in_flight):
        """Host-only immutable limit for an exact, fresh set of workflow tasks.

        Counts provider reservations/effects, not OS worker lifetimes. No
        dispatch, replay, lease or billing proof follows from configuration.
        Existing unconfigured single-task and sequential workflows are unchanged.
        """
        for value in (workflow_id,repository_id,user_turn_id):_text(value)
        _amount(token_hard,True);_amount(cost_usd_hard)
        if (not 1<=token_hard<=2**53-1 or type(max_in_flight) is not int or
                not 1<=max_in_flight<=64 or type(approved_revisions) is not dict or
                not 1<=len(approved_revisions)<=64 or
                any(type(k) is not str or not k.strip() or type(v) is not int or v<0
                    for k,v in approved_revisions.items())):
            raise ControllerError('Invalid workflow budget or membership')
        members=dict(approved_revisions)
        with self.controller._connection(write=True) as db:
            if db.execute('SELECT 1 FROM workflow_budget_limits WHERE workflow_id=?',(workflow_id,)).fetchone():
                raise ControllerError('Workflow budget already configured; no replacement')
            actual={r[0] for r in db.execute("SELECT task_id FROM tasks WHERE json_extract(task_json,'$.workflow_id')=?",(workflow_id,))}
            if actual!=set(members):
                raise ControllerError('Workflow budget requires exact task set')
            for key,revision in members.items():
                task=self.controller._read(db,key)
                if ((task['workflow_id'],task['repository_id'],task['user_turn_id'],task['revision'])!=
                        (workflow_id,repository_id,user_turn_id,revision) or task['status'] not in ('PLANNED','EXECUTING')):
                    raise ControllerError('Stale or foreign workflow budget member')
                rows=db.execute('SELECT * FROM budgets WHERE task_id=?',(key,)).fetchall()
                if (len(rows)!=1 or rows[0]['budget_id']!=task['budget_id'] or rows[0]['revision']!=revision or
                        any(rows[0][name]!=0 for name in ('used_tokens','reserved_tokens','used_cost','reserved_cost')) or
                        json.loads(rows[0]['budget_json'])['status']!='ACTIVE' or
                        db.execute('SELECT 1 FROM budget_reservations WHERE budget_id=?',(task['budget_id'],)).fetchone() or
                        db.execute('SELECT 1 FROM outbox WHERE task_id=?',(key,)).fetchone()):
                    raise ControllerError('Workflow budget requires fresh member budgets and no prior effects')
            db.execute('INSERT INTO workflow_budget_limits VALUES(?,?,?,?,?,?,?)',
                       (workflow_id,repository_id,user_turn_id,_json(members),token_hard,
                        str(Decimal(str(cost_usd_hard))),max_in_flight))

    def _workflow_gate(self,db,task,tokens,cost):
        limit=db.execute('SELECT * FROM workflow_budget_limits WHERE workflow_id=?',(task['workflow_id'],)).fetchone()
        if not limit:
            return
        members=json.loads(limit['members_json'])
        if ((task['repository_id'],task['user_turn_id'])!=(limit['repository_id'],limit['user_turn_id']) or
                members.get(task['task_id'])!=task['revision']):
            raise ControllerError('Task is not admitted to configured workflow budget')
        # Reject changed membership rather than silently expanding limits.
        actual={r[0] for r in db.execute("SELECT task_id FROM tasks WHERE json_extract(task_json,'$.workflow_id')=?",(task['workflow_id'],))}
        if actual!=set(members):
            raise ControllerError('Workflow budget membership changed')
        marks=','.join('?' for _ in members)
        keys=tuple(members)
        rows=db.execute('SELECT * FROM budgets WHERE task_id IN ('+marks+')',keys).fetchall()
        if len(rows)!=len(members) or {r['task_id'] for r in rows}!=set(members):
            raise ControllerError('Workflow member budget binding changed')
        used_tokens=sum(r['used_tokens']+r['reserved_tokens'] for r in rows)
        # Decimal sums of persisted amounts avoid additional float summation
        # error across task rows; the underlying provider ledger remains REAL.
        used_cost=sum((Decimal(str(r['used_cost']))+Decimal(str(r['reserved_cost'])) for r in rows),Decimal(0))
        if used_tokens+tokens>limit['token_hard'] or used_cost+Decimal(str(cost))>Decimal(limit['cost_hard']):
            raise ControllerError('Workflow aggregate budget exhausted')
        active=Counter(r[0] for r in db.execute(
            'SELECT b.task_id FROM budget_reservations r JOIN budgets b USING(budget_id) '
            'WHERE r.settlement IS NULL AND b.task_id IN ('+marks+')',keys))
        effects=Counter()
        for row in db.execute("SELECT task_id,state FROM outbox WHERE state IN ('PENDING','DISPATCHING','UNKNOWN') AND task_id IN ("+marks+')',keys):
            if row['state']=='UNKNOWN':
                raise ControllerError('Workflow has unknown effects; reconcile before dispatch')
            effects[row['task_id']]+=1
        # A normal reservation and its effect are one call, not two. Keep a
        # slot occupied if either remains open, even after budget settlement.
        if sum(max(active[k],effects[k]) for k in keys)>=limit['max_in_flight']:
            raise ControllerError('Workflow in-flight limit reached')

    def configure(self,task_id,record):
        record=json.loads(_json(record))
        Draft202012Validator(json.loads((ROOT/'schemas/budget.schema.json').read_text())).validate(record)
        for prefix in ('token','cost_usd','wall_time_s'):
            if record[prefix+'_soft']>record[prefix+'_hard']: raise ControllerError('Soft limit exceeds hard limit')
        with self.controller._connection(write=True) as db:
            task=self.controller._read(db,task_id)
            if record['task_id']!=task_id or record['revision']!=task['revision'] or record['budget_id']!=task['budget_id']: raise ControllerError('Budget task binding mismatch')
            prior=db.execute('SELECT budget_json FROM budgets WHERE budget_id=?',(record['budget_id'],)).fetchone()
            if prior:
                if prior[0]!=_json(record):raise ControllerError('Existing budget immutable; host must authorize new revision')
                return
            db.execute('INSERT INTO budgets(budget_id,task_id,revision,used_cost,budget_json) VALUES(?,?,?,0,?)',(record['budget_id'],task_id,task['revision'],_json(record)))

    def reserve(self,task_id,tokens,cost_usd,attempt_id):
        with self.controller._connection(write=True) as db:
            return self._reserve(db,task_id,tokens,cost_usd,attempt_id)

    def _reserve(self,db,task_id,tokens,cost_usd,attempt_id):
        _amount(tokens,True);_amount(cost_usd);_text(attempt_id)
        task=self.controller._read(db,task_id)
        row=db.execute('SELECT * FROM budgets WHERE budget_id=?',(task['budget_id'],)).fetchone()
        if not row or row['task_id']!=task_id or row['revision']!=task['revision'] or task['status'] in ('DONE','CANCELLED'):raise ControllerError('No current budget')
        prior=db.execute('SELECT * FROM budget_reservations WHERE attempt_id=?',(attempt_id,)).fetchone()
        receipt={'attempt_id':attempt_id,'budget_id':row['budget_id'],'tokens':tokens,'cost_usd':cost_usd}
        if prior:
            if (prior['budget_id'],prior['tokens'],prior['cost'])!=(row['budget_id'],tokens,cost_usd):raise ControllerError('Reservation identity substituted')
            return receipt
        record=json.loads(row['budget_json'])
        clock=db.execute('SELECT started FROM budget_clocks WHERE budget_id=?',(row['budget_id'],)).fetchone()
        active=db.execute('SELECT count(*) FROM budget_reservations WHERE budget_id=? AND settlement IS NULL',(row['budget_id'],)).fetchone()[0]
        if record['status']!='ACTIVE' or (clock and time.time()-clock[0]>=record['wall_time_s_hard']) or active>=record['max_parallel_workers'] or row['used_tokens']+row['reserved_tokens']+tokens>record['token_hard'] or row['used_cost']+row['reserved_cost']+cost_usd>record['cost_usd_hard']:
            raise ControllerError('Budget cannot authorize reservation')
        self._workflow_gate(db,task,tokens,cost_usd)
        db.execute('INSERT OR IGNORE INTO budget_clocks VALUES(?,?)',(row['budget_id'],time.time()))
        db.execute('INSERT INTO budget_reservations VALUES(?,?,?,?,NULL)',(attempt_id,row['budget_id'],tokens,cost_usd))
        db.execute('UPDATE budgets SET reserved_tokens=reserved_tokens+?,reserved_cost=reserved_cost+?,row_version=row_version+1 WHERE budget_id=?',(tokens,cost_usd,row['budget_id']))
        return receipt

    def settle(self,attempt_id,used_tokens,used_cost):
        _amount(used_tokens,True);_amount(used_cost)
        encoded=_json({'used_tokens':used_tokens,'used_cost':used_cost})
        with self.controller._connection(write=True) as db:
            reservation=db.execute('SELECT * FROM budget_reservations WHERE attempt_id=?',(attempt_id,)).fetchone()
            if not reservation:raise ControllerError('Unknown reservation')
            if reservation['settlement'] is not None:
                if reservation['settlement']!=encoded:raise ControllerError('Settlement substituted')
                return
            row=db.execute('SELECT * FROM budgets WHERE budget_id=?',(reservation['budget_id'],)).fetchone()
            record=json.loads(row['budget_json'])
            if row['used_tokens']+used_tokens>=record['token_hard'] or row['used_cost']+used_cost>=record['cost_usd_hard']:record['status']='EXHAUSTED'
            db.execute('UPDATE budget_reservations SET settlement=? WHERE attempt_id=?',(encoded,attempt_id))
            db.execute('UPDATE budgets SET reserved_tokens=reserved_tokens-?,reserved_cost=max(0,reserved_cost-?),used_tokens=used_tokens+?,used_cost=used_cost+?,budget_json=?,row_version=row_version+1 WHERE budget_id=?',(reservation['tokens'],reservation['cost'],used_tokens,used_cost,_json(record),row['budget_id']))
