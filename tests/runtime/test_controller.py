"""Real SQLite behavior; permissive guards are test doubles, never runtime policy."""
import importlib.util
import json
import multiprocessing
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def allow(context):
    return True


def race(db, barrier, queue):
    from harness.controller import Controller, Event, StaleVersion
    barrier.wait(timeout=10)
    try:
        Controller(db, guard=allow).transition('fixture', 0, Event(
            event_id=str(multiprocessing.current_process().pid),
            idempotency_key=str(multiprocessing.current_process().pid), target='CLASSIFIED'))
        queue.put('ok')
    except StaleVersion:
        queue.put('stale')


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('harness'), 'State controller is not implemented')
        from harness.controller import Controller, Event, initialize, ControllerError
        self.Controller, self.Event, self.Error = Controller, Event, ControllerError
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'state.db'
        initialize(self.db)
        self.c = Controller(self.db, guard=allow)
        self.task = json.loads((ROOT / 'fixtures/valid/task.json').read_text())
        self.task.update(revision=0, row_version=0)
        self.c.create_task(self.task, event_id='create', idempotency_key='create')
        self.seq = 0

    def event(self, target, **kwargs):
        self.seq += 1
        return self.Event(event_id=f'e{self.seq}', idempotency_key=f'k{self.seq}', target=target, **kwargs)

    def move(self, target, **kwargs):
        return self.c.transition('fixture', self.c.get_task('fixture')['row_version'], self.event(target, **kwargs))

    def walk(self, target):
        for state in ['CLASSIFIED', 'PLANNED', 'ASSIGNED', 'EXECUTING', 'REVIEWING',
                      'VERIFYING', 'COMPLETION_AUDITING', 'ACCEPTED', 'DONE']:
            self.move(state)
            if state == target:
                break

    def count_events(self):
        with sqlite3.connect(self.db) as db:
            return db.execute('SELECT count(*) FROM events').fetchone()[0]

    def test_reject_new_to_done(self):
        with self.assertRaises(self.Error):
            self.move('DONE')
        self.assertEqual(self.c.get_task('fixture')['status'], 'NEW')
        self.assertEqual(self.count_events(), 1)

    def test_transition_persists_snapshot_and_event_across_restart(self):
        self.move('CLASSIFIED')
        task = self.Controller(self.db).get_task('fixture')
        self.assertEqual((task['status'], task['row_version'], task['revision']), ('CLASSIFIED', 1, 0))
        with sqlite3.connect(self.db) as db:
            row = db.execute('SELECT state,row_version,revision,task_json FROM tasks').fetchone()
            self.assertEqual(row[:3], ('CLASSIFIED', 1, 0))
            self.assertEqual(json.loads(row[3]), task)
            event = db.execute('SELECT event_type,row_version FROM events ORDER BY event_seq DESC').fetchone()
            self.assertEqual(event, ('transition', 1))

    def test_stale_cas_is_rejected_without_event(self):
        self.move('CLASSIFIED')
        with self.assertRaises(self.Error):
            self.c.transition('fixture', 0, self.event('PLANNED'))
        self.assertEqual(self.count_events(), 2)

    def test_default_guard_denies_even_legal_edge(self):
        with self.assertRaises(self.Error):
            self.Controller(self.db).transition('fixture', 0, self.event('CLASSIFIED'))
        self.assertEqual(self.c.get_task('fixture')['row_version'], 0)

    def test_guard_requires_literal_true(self):
        for result in [False, None, 'PASS', 1, {'ok': True}]:
            with self.subTest(result=result), self.assertRaises(self.Error):
                self.Controller(self.db, guard=lambda ctx: result).transition('fixture', 0, self.event('CLASSIFIED'))
        self.assertEqual(self.count_events(), 1)

    def test_guard_exception_rolls_back(self):
        def broken(ctx):
            raise RuntimeError('collector unavailable')
        with self.assertRaises(RuntimeError):
            self.Controller(self.db, guard=broken).transition('fixture', 0, self.event('CLASSIFIED'))
        self.assertEqual(self.count_events(), 1)
        self.assertEqual(self.c.get_task('fixture')['status'], 'NEW')

    def test_guard_cannot_mutate_persisted_snapshot(self):
        def mutate(ctx):
            ctx.after['objective'] = 'injected'
            ctx.before['revision'] = 100
            return True
        self.Controller(self.db, guard=mutate).transition('fixture', 0, self.event('CLASSIFIED'))
        self.assertEqual(self.c.get_task('fixture')['objective'], 'fixture')
        self.assertEqual(self.c.get_task('fixture')['revision'], 0)

    def test_event_insert_failure_rolls_back_state(self):
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TRIGGER fail_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.move('CLASSIFIED')
        self.assertEqual(self.c.get_task('fixture')['status'], 'NEW')
        self.assertEqual(self.count_events(), 1)

    def test_duplicate_identity_never_applies_second_change(self):
        first = self.event('CLASSIFIED')
        self.c.transition('fixture', 0, first)
        for event in [self.Event(first.event_id, 'other-key', 'PLANNED'),
                      self.Event('other-id', first.idempotency_key, 'PLANNED')]:
            with self.assertRaises(self.Error):
                self.c.transition('fixture', 1, event)
        self.assertEqual(self.c.get_task('fixture')['status'], 'CLASSIFIED')
        self.assertEqual(self.count_events(), 2)

    def test_repair_advances_semantic_revision_only_once(self):
        self.walk('VERIFYING')
        task = self.move('REPAIR')
        self.assertEqual((task['revision'], task['row_version']), (1, 7))
        task = self.move('ASSIGNED')
        self.assertEqual((task['revision'], task['row_version']), (1, 8))

    def test_block_requires_reference(self):
        with self.assertRaises(self.Error):
            self.move('BLOCKED')

    def test_block_resume_survives_restart_and_preserves_revision(self):
        self.walk('EXECUTING')
        self.move('BLOCKED', reference='blocker-1')
        self.c = self.Controller(self.db, guard=allow)
        task = self.move('EXECUTING', kind='resume', reference='blocker-1')
        self.assertEqual((task['status'], task['revision'], task['row_version']), ('EXECUTING', 0, 6))
        self.assertNotIn('resume_state', task)

    def test_resume_revalidates_guards(self):
        self.walk('EXECUTING')
        self.move('BLOCKED', reference='b')
        with self.assertRaises(self.Error):
            self.Controller(self.db).transition('fixture', 5, self.event('EXECUTING', kind='resume', reference='b'))
        self.assertEqual(self.c.get_task('fixture')['status'], 'BLOCKED')

    def test_resume_rejects_wrong_reference_and_bypass_target(self):
        self.move('BLOCKED', reference='b')
        for target, kind, ref in [('NEW', 'resume', 'other'), ('DONE', 'resume', 'b'),
                                  ('CLASSIFIED', 'resume', 'b'), ('NEW', 'transition', 'b')]:
            with self.subTest(target=target, kind=kind), self.assertRaises(self.Error):
                self.move(target, kind=kind, reference=ref)
        self.assertEqual(self.c.get_task('fixture')['status'], 'BLOCKED')

    def test_acceptance_interrupt_resumes_only_at_verification(self):
        self.walk('ACCEPTED')
        task = self.move('NEEDS_HUMAN_APPROVAL', reference='approval-1')
        self.assertEqual(task['resume_state'], 'VERIFYING')
        with self.assertRaises(self.Error):
            self.move('ACCEPTED', kind='resume', reference='approval-1')
        task = self.move('VERIFYING', kind='resume', reference='approval-1')
        self.assertEqual(task['status'], 'VERIFYING')

    def test_terminal_states_cannot_reopen(self):
        self.walk('DONE')
        for target in ['CLASSIFIED', 'BLOCKED', 'CANCELLED']:
            with self.assertRaises(self.Error):
                self.move(target)

    def test_cancellation_is_guarded_and_terminal(self):
        with self.assertRaises(self.Error):
            self.Controller(self.db).transition('fixture', 0, self.event('CANCELLED'))
        self.move('CANCELLED')
        with self.assertRaises(self.Error):
            self.move('CLASSIFIED')

    def test_invalid_initial_task_cannot_bypass_lifecycle(self):
        for field, value in [('status', 'DONE'), ('revision', 1), ('row_version', 1), ('owner', 'valera')]:
            task = dict(self.task, task_id=f'bad-{field}')
            task[field] = value
            with self.subTest(field=field), self.assertRaises((self.Error, ValueError)):
                self.c.create_task(task, event_id=field, idempotency_key=field)
        self.assertEqual(self.count_events(), 1)

    def test_creation_event_failure_leaves_no_task(self):
        task = dict(self.task, task_id='second')
        with self.assertRaises(self.Error):
            self.c.create_task(task, event_id='create', idempotency_key='another')
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0], 1)

    def test_two_processes_cannot_both_update_same_version(self):
        ctx = multiprocessing.get_context('spawn')
        barrier, queue = ctx.Barrier(2), ctx.Queue()
        workers = [ctx.Process(target=race, args=(str(self.db), barrier, queue)) for _ in range(2)]
        for p in workers:
            p.start()
        for p in workers:
            p.join(15)
            if p.is_alive():
                p.terminate()
                p.join()
            self.assertEqual(p.exitcode, 0)
        self.assertEqual(sorted([queue.get(timeout=2), queue.get(timeout=2)]), ['ok', 'stale'])
        queue.close()
        self.assertEqual(self.count_events(), 2)

    def test_corrupt_snapshot_is_not_silently_repaired(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE tasks SET row_version=99 WHERE task_id='fixture'")
        with self.assertRaises(self.Error):
            self.c.transition('fixture', 99, self.event('CLASSIFIED'))

    def test_initialization_cannot_erase_existing_database(self):
        from harness.controller import initialize
        with self.assertRaises(FileExistsError):
            initialize(self.db)
        self.assertEqual(self.c.get_task('fixture')['status'], 'NEW')

    def test_fractional_representation_of_version_is_rejected_at_intake(self):
        for field in ['revision', 'row_version']:
            task = dict(self.task, task_id=f'float-{field}')
            task[field] = 0.0
            with self.subTest(field=field), self.assertRaises(self.Error):
                self.c.create_task(task, event_id=field, idempotency_key=field)
        self.assertEqual(self.count_events(), 1)

    def test_resume_of_repair_does_not_increment_revision_again(self):
        self.walk('VERIFYING')
        self.move('REPAIR')
        self.move('BLOCKED', reference='b')
        task = self.move('REPAIR', kind='resume', reference='b')
        self.assertEqual((task['revision'], task['row_version']), (1, 9))

    def test_pin_target_advances_revision_with_atomic_event(self):
        self.walk('EXECUTING')
        commit = {'hash_algorithm': 'sha1', 'value': 'b' * 40}
        self.assertTrue(hasattr(self.c, 'pin_target'), 'Target pinning is not implemented')
        task = self.c.pin_target('fixture', 4, commit, event_id='pin', idempotency_key='pin')
        self.assertEqual((task['status'], task['revision'], task['row_version']), ('EXECUTING', 1, 5))
        self.assertEqual(task['target_commit'], commit)
        self.assertEqual(self.count_events(), 6)
        with self.assertRaises(self.Error):
            self.c.pin_target('fixture', 4, commit, event_id='stale-pin', idempotency_key='stale-pin')

    def test_pin_target_cannot_bypass_guard_or_phase(self):
        self.assertTrue(hasattr(self.c, 'pin_target'), 'Target pinning is not implemented')
        commit = {'hash_algorithm': 'sha1', 'value': 'b' * 40}
        with self.assertRaises(self.Error):
            self.c.pin_target('fixture', 0, commit, event_id='pin', idempotency_key='pin')
        self.walk('EXECUTING')
        with self.assertRaises(self.Error):
            self.Controller(self.db).pin_target('fixture', 4, commit, event_id='pin', idempotency_key='pin')
        self.assertEqual(self.c.get_task('fixture')['revision'], 0)

    def test_unresolved_effect_prevents_terminal_state(self):
        self.walk('ACCEPTED')
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO outbox(effect_id,task_id,task_revision,idempotency_key,action_digest,state,payload_json,created_at,updated_at) VALUES('effect','fixture',0,'effect','digest','UNKNOWN','{}','now','now')")
        with self.assertRaises(self.Error):
            self.move('DONE')
        self.assertEqual(self.c.get_task('fixture')['status'],'ACCEPTED')
