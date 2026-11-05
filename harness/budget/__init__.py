"""Finite host-owned reservation accounting, serialized across local processes."""
import json
import math
import time
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
        _amount(tokens,True);_amount(cost_usd);_text(attempt_id)
        with self.controller._connection(write=True) as db:
            task=self.controller._read(db,task_id)
            row=db.execute('SELECT * FROM budgets WHERE budget_id=?',(task['budget_id'],)).fetchone()
            if not row or row['revision']!=task['revision'] or task['status'] in ('DONE','CANCELLED'):raise ControllerError('No current budget')
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
