"""Atomic provider dispatch preparation on real SQLite; no worker launch."""
import json
import multiprocessing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from harness.budget import Budget
from harness.controller import Controller, ControllerError, Event, initialize, ROOT
from harness.leases import LeaseManager
from harness.runtime.dispatch import reserve_provider_dispatch
from harness.state import Outbox


def reserve(db, task, lease, **overrides):
    args = dict(task_id=task['task_id'], revision=task['revision'],
                row_version=task['row_version'], owner=task['owner'],
                lease_id=lease['lease_id'], session=lease['worker_session_id'],
                workspace=lease['workspace_id'], model='fixture/test',
                context_digest='sha256:'+'a'*64, tokens=10, cost=0.1)
    args.update(overrides)
    return reserve_provider_dispatch(db, **args)


def contender(args):
    db, task, lease = args
    try:
        reserve(db, task, lease)
        return 'reserved'
    except ControllerError:
        return 'denied'


class DispatchPreparationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name)/'state.db'
        initialize(self.db)
        self.controller = Controller(self.db, guard=lambda c: c.after['status'] in
                                     ('CLASSIFIED','PLANNED','ASSIGNED','EXECUTING'))
        self.budget = Budget(self.db)
        self.leases = LeaseManager(self.db)

    def add_task(self, task_id, owner, path):
        task = json.loads((ROOT/'fixtures/valid/task.json').read_text())
        task.update(task_id=task_id, workflow_id='workflow', user_turn_id='turn',
                    repository_id='repo', owner=owner, revision=0, row_version=0,
                    scope=[path], budget_id='budget-'+task_id, depends_on=[])
        task = self.controller.create_task(task, event_id=task_id+'create', idempotency_key=task_id+'create')
        for state in ('CLASSIFIED','PLANNED','ASSIGNED','EXECUTING'):
            task = self.controller.transition(task_id,task['row_version'],Event(task_id+state,task_id+state,state))
        record = json.loads((ROOT/'fixtures/valid/budget.json').read_text())
        record.update(task_id=task_id,budget_id=task['budget_id'],revision=0,
                      token_soft=100,token_hard=100,cost_usd_soft=1,cost_usd_hard=1,
                      wall_time_s_soft=60,wall_time_s_hard=60)
        self.budget.configure(task_id,record)
        lease = self.leases.acquire(task_id,task['row_version'],'session-'+task_id,
                                    'workspace-'+task_id,[{'kind':'path','key':path}])
        return task,lease

    def counts(self):
        with sqlite3.connect(self.db) as db:
            return (db.execute('SELECT count(*) FROM budget_reservations').fetchone()[0],
                    db.execute('SELECT count(*) FROM outbox').fetchone()[0])

    def test_two_specialists_share_ledger_but_not_task_budget_or_lease(self):
        api, a = self.add_task('api','backend','api.py')
        ui, b = self.add_task('ui','frontend','ui.py')
        x = reserve(self.db,api,a)
        y = reserve(self.db,ui,b)
        self.assertNotEqual(x['effect_id'],y['effect_id'])
        self.assertEqual(self.counts(),(2,2))
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT task_id,reserved_tokens FROM budgets ORDER BY task_id').fetchall(),
                             [('api',10),('ui',10)])
            self.assertEqual(db.execute('SELECT task_id,state FROM outbox ORDER BY task_id').fetchall(),
                             [('api','DISPATCHING'),('ui','DISPATCHING')])
        Outbox(self.db).mark_unknown(x['effect_id'])
        with self.assertRaises(ControllerError):
            reserve(self.db,api,a)
        self.assertEqual(Outbox(self.db).unresolved('api'),[x['effect_id']])
        self.assertEqual(Outbox(self.db).unresolved('ui'),[y['effect_id']])
        self.assertEqual(self.counts(),(2,2))

    def test_stale_or_cross_task_bindings_and_insufficient_budget_leave_no_rows(self):
        api,a = self.add_task('api','backend','api.py')
        ui,b = self.add_task('ui','frontend','ui.py')
        for change in (dict(owner='valera-ceo'),dict(row_version=3),dict(revision=1),
                       dict(lease_id=b['lease_id']),dict(session=b['worker_session_id']),
                       dict(workspace=b['workspace_id']),dict(tokens=101)):
            with self.subTest(change=change),self.assertRaises(ControllerError):
                reserve(self.db,api,a,**change)
        self.leases.suspect(a['lease_id'])
        with self.assertRaises(ControllerError):
            reserve(self.db,api,a)
        self.assertEqual(self.counts(),(0,0))

    def test_failure_after_budget_and_outbox_insert_rolls_back_both(self):
        task,lease = self.add_task('api','backend','api.py')
        with patch.object(Outbox,'_claim',side_effect=ControllerError('injected failure')):
            with self.assertRaises(ControllerError):
                reserve(self.db,task,lease)
        self.assertEqual(self.counts(),(0,0))
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT reserved_tokens,reserved_cost FROM budgets').fetchone(),(0,0))
            self.assertEqual(db.execute('SELECT count(*) FROM budget_clocks').fetchone()[0],0)
        reserve(self.db,task,lease)
        self.assertEqual(self.counts(),(1,1))

    def test_two_processes_cannot_claim_same_task_dispatch(self):
        task,lease = self.add_task('api','backend','api.py')
        with multiprocessing.get_context('spawn').Pool(2) as pool:
            results = pool.map(contender,[(str(self.db),task,lease)]*2)
        self.assertEqual(sorted(results),['denied','reserved'])
        self.assertEqual(self.counts(),(1,1))
