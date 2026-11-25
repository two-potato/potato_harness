"""Provider-independent workflow selection on real SQLite, no dispatch."""
import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy

from harness.controller import Controller, ControllerError, Event, initialize
from harness.scheduler import Scheduler, SPECIALISTS

ROOT = Path(__file__).resolve().parents[2]


class WorkflowSelectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / 'state.db'
        initialize(self.db)
        # The permissive guard is an explicit test seam for planning states only.
        self.controller = Controller(self.db, guard=lambda c: c.after['status'] in ('CLASSIFIED', 'PLANNED'))
        self.template = json.loads((ROOT / 'fixtures/valid/task.json').read_text())
        self.tasks = {}
        self.add('api', 'backend')
        self.add('ui', 'frontend')
        self.add('review', 'qa', ['api', 'ui'])
        self.dag = {'schema_version': '3.0.1', 'workflow_id': 'w', 'nodes': [
            {'id': 'a', 'task_id': 'api', 'needs': []},
            {'id': 'b', 'task_id': 'ui', 'needs': []},
            {'id': 'q', 'task_id': 'review', 'needs': ['a', 'b']}]}
        self.host = {'workflow_id': 'w', 'user_turn_id': 'turn', 'repository_id': 'repo',
                     'approved_revisions': {k: 0 for k in self.tasks}, 'available_owners': SPECIALISTS}

    def add(self, task_id, owner, depends=None, **overrides):
        t = deepcopy(self.template)
        t.update(task_id=task_id, workflow_id='w', user_turn_id='turn', repository_id='repo',
                 revision=0, row_version=0, owner=owner, depends_on=depends or [])
        t.update(overrides)
        t = self.controller.create_task(t, event_id=task_id, idempotency_key=task_id)
        for state in ('CLASSIFIED', 'PLANNED'):
            t = self.controller.transition(task_id, t['row_version'], Event(task_id+state, task_id+state, state))
        self.tasks[task_id] = t

    def test_multi_role_ready_and_no_state_mutation(self):
        scheduler = Scheduler(self.db)
        self.assertEqual(scheduler.ready_workflow(self.dag, **self.host), ['api', 'ui'])
        self.assertEqual(Scheduler(self.db, max_ready=1).ready_workflow(self.dag, **self.host), ['api'])
        for key, before in self.tasks.items():
            self.assertEqual(self.controller.get_task(key), before)

    def test_unavailable_owner_is_not_reassigned(self):
        host = dict(self.host, available_owners=('frontend', 'qa'))
        self.assertEqual(Scheduler(self.db).ready_workflow(self.dag, **host), ['ui'])
        self.assertEqual(self.controller.get_task('api')['owner'], 'backend')
        for owners in [('valera-ceo',), ('explore',), ('backend', 'backend'), 'backend']:
            with self.assertRaises(ControllerError):
                Scheduler(self.db).ready_workflow(self.dag, **dict(self.host, available_owners=owners))

    def test_rejects_graph_changes_and_stale_approval(self):
        variants = []
        d = deepcopy(self.dag); d['nodes'].pop(); variants.append(d)
        d = deepcopy(self.dag); d['nodes'][2]['needs'] = []; variants.append(d)
        d = deepcopy(self.dag); d['nodes'][0]['needs'] = ['q']; variants.append(d)
        d = deepcopy(self.dag); d['nodes'][0]['owner'] = 'valera-ceo'; variants.append(d)
        d = deepcopy(self.dag); d['nodes'][1]['task_id'] = 'api'; variants.append(d)
        d = deepcopy(self.dag); d['workflow_id'] = 'another'; variants.append(d)
        d = deepcopy(self.dag); d['nodes'][0]['needs'] = ['missing']; variants.append(d)
        for dag in variants:
            with self.subTest(dag=dag), self.assertRaises(ControllerError):
                Scheduler(self.db).ready_workflow(dag, **self.host)
        for revisions in [{'api': 1, 'ui': 0, 'review': 0}, {'api': False, 'ui': 0, 'review': 0}]:
            with self.assertRaises(ControllerError):
                Scheduler(self.db).ready_workflow(self.dag, **dict(self.host, approved_revisions=revisions))

    def test_rejects_cross_workflow_turn_repository_and_explore(self):
        for index, change in enumerate([{'workflow_id': 'other'}, {'user_turn_id': 'other'},
                                        {'repository_id': 'other'}, {'owner': 'explore'}]):
            key = 'foreign-'+str(index)
            self.add(key, change.pop('owner', 'backend'), **change)
            dag = deepcopy(self.dag)
            dag['nodes'].append({'id': key, 'task_id': key, 'needs': []})
            host = dict(self.host, approved_revisions={**self.host['approved_revisions'], key: 0})
            with self.assertRaises(ControllerError):
                Scheduler(self.db).ready_workflow(dag, **host)

    def test_all_eight_specialists_are_recognized_without_dispatch(self):
        for role in sorted(SPECIALISTS - {'backend', 'frontend', 'qa'}):
            self.add(role, role)
            self.dag['nodes'].append({'id': role, 'task_id': role, 'needs': []})
            self.host['approved_revisions'][role] = 0
        selected = Scheduler(self.db).ready_workflow(self.dag, **self.host)
        self.assertEqual(set(selected), set(self.tasks)-{'review'})
        self.assertEqual(len({self.controller.get_task(k)['owner'] for k in selected}), 7)
        self.assertEqual(self.controller.get_task('review')['owner'], 'qa')
