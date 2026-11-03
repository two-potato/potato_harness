"""Transactional state machine for trusted, single-host controller processes.

Guard functions are host-owned code, never worker-supplied callbacks. Default
behavior denies transitions. This module provides no process isolation.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Callable

from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[2]


class ControllerError(ValueError):
    """Rejected operation; no state or event was committed."""


class StaleVersion(ControllerError):
    """Caller must reload the task before proposing a new operation."""


@dataclass(frozen=True)
class Event:
    event_id: str
    idempotency_key: str
    target: str
    kind: str = 'transition'
    reference: str | None = None


@dataclass(frozen=True)
class GuardContext:
    before: dict
    after: dict
    event: Event
    interruption: dict | None


def _deny(context: GuardContext) -> bool:
    return False


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ControllerError('Expected a nonempty string')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _now():
    return datetime.now(timezone.utc).isoformat()


def initialize(database: str | Path) -> None:
    """Explicitly initialize a new file. Never migrate or replace existing data."""
    path = Path(database)
    # Exclusive creation protects against accidentally truncating an existing DB.
    with path.open('xb'):
        pass
    connection = sqlite3.connect(path)
    try:
        connection.executescript((ROOT / 'state/001_init.sql').read_text())
    finally:
        connection.close()
    # A failed initialization is deliberately retained for inspection, not deleted.


class Controller:
    def __init__(self, database: str | Path, *, guard: Callable[[GuardContext], bool] = _deny):
        self.database = Path(database).resolve()
        self.guard = guard
        self.policy = json.loads((ROOT / 'policy/transitions.json').read_text())
        self.validator = Draft202012Validator(json.loads((ROOT / 'schemas/task.schema.json').read_text()))

    @contextmanager
    def _connection(self, *, write=False):
        # mode=rw rejects missing databases rather than silently creating them.
        db = sqlite3.connect(self.database.as_uri() + '?mode=rw', uri=True, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            versions = [row[0] for row in db.execute('SELECT version FROM schema_migrations ORDER BY version')]
            if versions != [1]:
                raise ControllerError('Unsupported database migration version')
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def _validate(self, task):
        try:
            self.validator.validate(task)
        except ValidationError as exc:
            raise ControllerError(f'Invalid task snapshot: {exc.message}') from exc
        if any(type(task[field]) is not int for field in ('revision', 'row_version')):
            raise ControllerError('Revision and row_version must use integer representation')
        ids = [item['id'] for item in task['acceptance']]
        if len(ids) != len(set(ids)):
            raise ControllerError('Acceptance IDs must be unique')

    def _read(self, db, task_id):
        row = db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
        if row is None:
            raise ControllerError('Task not found')
        task = json.loads(row['task_json'])
        self._validate(task)
        for column, field in [('state', 'status'), ('revision', 'revision'),
                              ('row_version', 'row_version'), ('task_id', 'task_id'),
                              ('owner', 'owner'), ('repository_id', 'repository_id')]:
            if row[column] != task[field]:
                raise ControllerError('Task columns and snapshot disagree')
        return task

    def get_task(self, task_id: str) -> dict:
        with self._connection() as db:
            return self._read(db, task_id)

    @staticmethod
    def _unique_event(db, event_id, key):
        _text(event_id)
        _text(key)
        if db.execute('SELECT 1 FROM events WHERE event_id=? OR idempotency_key=?', (event_id, key)).fetchone():
            raise ControllerError('Event identity already used; read persisted state before retrying')

    @staticmethod
    def _record(db, task, event, payload, now):
        db.execute('INSERT INTO events(event_id,idempotency_key,task_id,revision,row_version,event_type,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)',
                   (event.event_id, event.idempotency_key, task['task_id'], task['revision'],
                    task['row_version'], event.kind, _json(payload), now))

    def create_task(self, task: dict, *, event_id: str, idempotency_key: str) -> dict:
        task = deepcopy(task)
        self._validate(task)
        if (task['status'], task['revision'], task['row_version']) != ('NEW', 0, 0) or 'resume_state' in task:
            raise ControllerError('New tasks must start at NEW with revision and row_version zero')
        now = _now()
        with self._connection(write=True) as db:
            self._unique_event(db, event_id, idempotency_key)
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',
                       (task['task_id'], 0, 0, 'NEW', task['owner'], task['repository_id'], _json(task), now))
            self._record(db, task, Event(event_id, idempotency_key, 'NEW', 'created'), {'snapshot': task}, now)
        return task

    def transition(self, task_id: str, expected_row_version: int, event: Event) -> dict:
        if type(expected_row_version) is not int or expected_row_version < 0:
            raise ControllerError('Expected a nonnegative integer row version')
        if not isinstance(event, Event) or event.kind not in ('transition', 'resume'):
            raise ControllerError('Unsupported event')
        _text(event.target)
        if event.reference is not None:
            _text(event.reference)
        with self._connection(write=True) as db:
            before = self._read(db, task_id)
            if before['row_version'] != expected_row_version:
                raise StaleVersion('Task changed; reload before retrying')
            self._unique_event(db, event.event_id, event.idempotency_key)
            source, target = before['status'], event.target
            if source in self.policy['terminal']:
                raise ControllerError('Terminal tasks cannot reopen')
            after = deepcopy(before)
            interruption = None
            if event.kind == 'resume':
                if source not in ('BLOCKED', 'NEEDS_HUMAN_APPROVAL'):
                    raise ControllerError('Only interrupted tasks can resume')
                row = db.execute('SELECT payload_json FROM events WHERE task_id=? AND row_version=?',
                                 (task_id, expected_row_version)).fetchone()
                interruption = json.loads(row[0]) if row else None
                if (not interruption or interruption.get('to') != source
                        or interruption.get('revision') != before['revision']
                        or not event.reference or interruption.get('reference') != event.reference):
                    raise ControllerError('Missing or stale interruption resolution reference')
                if target != before.get('resume_state') or target in ('ACCEPTED', 'DONE'):
                    raise ControllerError('Resume target must match stored safe state')
                after.pop('resume_state', None)
            elif source in self.policy['interruptible_states'] and target in self.policy['interrupts']:
                if target != 'CANCELLED':
                    if not event.reference:
                        raise ControllerError('Interruption requires blocker or approval reference')
                    after['resume_state'] = 'VERIFYING' if source == 'ACCEPTED' else source
            elif [source, target] not in self.policy['edges']:
                raise ControllerError(f'Illegal transition: {source} -> {target}')
            after.update(status=target, row_version=expected_row_version + 1)
            if target == 'REPAIR' and event.kind != 'resume':
                after['revision'] += 1
            self._validate(after)
            # Detached copies prevent a trusted adapter's accidental mutation from
            # rewriting task identity or bypassing transition validation.
            context = GuardContext(deepcopy(before), deepcopy(after), event, deepcopy(interruption))
            if self.guard(context) is not True:
                raise ControllerError('Trusted state guards did not authorize transition')
            now = _now()
            changed = db.execute('UPDATE tasks SET revision=?,row_version=?,state=?,task_json=?,updated_at=? WHERE task_id=? AND row_version=?',
                                 (after['revision'], after['row_version'], target, _json(after), now, task_id, expected_row_version))
            if changed.rowcount != 1:
                raise StaleVersion('Concurrent update')
            self._record(db, after, event, {'from': source, 'to': target,
                         'revision': after['revision'], 'previous_revision': before['revision'],
                         'reference': event.reference}, now)
        return after
