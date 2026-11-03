# State controller — milestone 1

Implementation: Python 3.12, SQLite on one host. Contract version remains
`3.0.1`; this is an initial runtime component, not an activated agent system.
The existing implementation plan selects SQLite. Python is the implementation
choice for this SDK-independent core because the package already uses Python
for validation; no OpenCode/Jev SDK compatibility is claimed.

## Scope and design

A trusted host calls `Controller.transition(task_id, expected_row_version, event)`.
Each write uses a fresh connection with foreign keys enabled and `BEGIN IMMEDIATE`.
The transaction reads and validates the current snapshot, checks CAS, validates
policy edges, calls a host-owned guard, then commits the state and audit event
together. A failed guard or event insert leaves both unchanged. File-backed
SQLite allows independent local processes to contend safely. Network-filesystem
and multi-host deployment are unsupported.

`revision` identifies semantic work; `row_version` increments on every state
write. Entering REPAIR increments revision; resuming an interrupted REPAIR does
not. General scope/plan/commit amendment APIs are not implemented yet. A caller
cannot patch the task through an event or supply a replacement snapshot.

Interruptions persist a safe `resume_state` in the task, and reference plus prior
revision in the atomic event. Resume must name the stored target and interruption
reference, match the current revision and pass the guard again. Interrupting
ACCEPTED stores VERIFYING as the resume target. Direct resume to ACCEPTED/DONE
is rejected. The reference is correlation data, **not proof of resolution**.

The JSON policy is loaded from the trusted checkout, never from a worker request.
Changes require a controller restart and the policy review process. The task
schema and mirrored SQL columns must agree; corruption is rejected, not repaired.

## Trust boundary and incomplete guards

The default guard denies **every transition**, including cancellation. Creating
and reading a NEW task is possible; creation requires a full schema-valid task,
revision 0 and row_version 0. There is no HTTP endpoint or worker-facing service.
Only trusted host code may construct the controller and select its guard.

A custom guard is a trusted in-process adapter. It receives detached before/after
snapshots, the event and interruption metadata, and must return literal `True`.
It must validate every destination's requirements in CONTROL_FLOW.md, including
preflight, dependencies, fresh grants/leases, budget, evidence, cleanup and actual
resolution of interruptions. The included permissive adapter exists **only in
tests** to exercise state storage independently of future integrations.

Do not wire the test adapter into an agent host. Do not accept guard functions,
PASS strings or resolution claims from model output. A Python callback is not
sandboxing or issuer authentication. The evidence/approval verifier and broker
are later milestones. In particular, this milestone does not implement atomic
grant revocation, lease release, outbox reservations, cancellation reconciliation,
or completion freshness across external services. Safe production DONE/CANCELLED
remains unavailable with the default configuration.

Guards execute under a SQLite write lock. They should inspect already-collected
trusted local evidence, have bounded latency, and perform no irreversible external
effects. Callback effects are not rolled back by the SQLite transaction. Later
milestones must integrate transactional cleanup and outbox operations explicitly;
a callback cannot substitute for that integration.

## API example (safe default)

Run from the repository root after installing requirements-validation.txt:

```python
from pathlib import Path
from harness.controller import Controller, Event, ControllerError, initialize

path = Path('.runtime/state.db')
path.parent.mkdir(exist_ok=True)
initialize(path)  # exclusive creation; existing file raises FileExistsError
controller = Controller(path)
# Supply a full task contract with status NEW, revision=0, row_version=0:
# controller.create_task(task, event_id='intake-1', idempotency_key='intake-1')
# controller.get_task(task['task_id'])
# All transitions are denied until trusted guards are implemented/configured.
```

`Event(event_id, idempotency_key, target, kind='transition', reference=None)`
supports transition and resume. Resume uses `kind='resume'`. Event identifiers
are globally unique within the DB. Duplicate event IDs or idempotency keys are
rejected without writing; this is duplicate prevention, not replay of prior
responses. Reload persisted state to reconcile an uncertain request before issuing
another event. Stale versions raise `StaleVersion`; rejected transitions raise
`ControllerError`; infrastructure errors propagate after transaction rollback.

Initialization uses the existing 001 migration and will never overwrite an
existing file. If it fails, retain and inspect the partial file. Automatic upgrade,
repair and startup recovery are outside this milestone. Protect the DB directory
with host permissions; any process with direct write access can bypass this API.

## Validation and next step

```bash
python -m unittest discover -s tests/runtime -v
python -m unittest discover -s tests -v
python tools/validate_pack.py
python tools/verify_manifest.py
```

The runtime tests exercise a real temporary SQLite database, restarts, failing
SQL event writes and two spawned processes. They do not certify live agent guards
or mark the H/M/C integration registry as executed.

Next: milestone 2, trusted evidence and approval verification. This change is
submitted as a reviewed PR; runtime activation stays disabled.
