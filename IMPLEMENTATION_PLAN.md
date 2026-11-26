# Harness 3.0.1 implementation plan

Goal: materialize the approved spec as a tested runtime after importing this package.
Architecture: one deterministic controller and state store; task-scoped workers; trusted effect/evidence/approval boundaries. Valera only coordinates.
Spec: docs/harness/v3/CONTROL_FLOW.md, CAPABILITIES.md, EVIDENCE_GATES.md.
Stack decision: SQLite for single-host state; implementation language follows the verified target SDK; JSON Schema 2020-12 for contracts. No language-specific SDK is assumed installed.

## Global constraints

Preserve agents/ hashes. Never auto-activate adapters. No product features or production changes. Actual schema validation is separate from authorization. Critical runtime checks must not be replaced by fixture checks.

## Milestones (each is a reviewed PR)

1. State controller: implement transition(task_id, expected_row_version, event) and guarded resume against policy/transitions.json in harness/controller/. Tests in tests/runtime/test_controller: reject NEW→DONE, stale CAS, direct resume to DONE; event/state atomicity; separate semantic revision from row version. Start with failing tests, implement, run pass, commit.
2. Evidence/approval: implement verify_evidence(record, task, trusted_collector) and verify_approval(record, action, clock, issuer) in harness/verifier/. Tests reject forged issuer, wrong repo/SHA/revision, bad digest, expired/revoked approval, substituted action and conflicting run results. No LLM used in these tests.
3. Broker/isolation: implement authorize(grant, request, context) and trusted publish(lease, artifact) in harness/policy/. OS adapter prevents direct publication outside broker. Tests cover all real tools/MCP, symlink/path escape, forbidden network, stale process and no Valera engineering actions.
4. Scheduler/leases: implement acquire_claims(task, resources, expected_version) under BEGIN IMMEDIATE in harness/leases/; integrate DAG scheduler. Two real processes contend; only one conflicting lease; SUSPECT not reassigned; contract dependency blocked; integration commit evidence refreshed.
5. Outbox/recovery/budget: implement reserve_effect, claim_effect, reconcile_effect and reserve_budget in harness/state/ and harness/budget/. Fault tests crash before/after dispatch/result write; unknown non-idempotent effect never repeats; concurrent calls cannot exceed reservation; safe cancellation preserves unresolved effects.
6. Context: implement compile_context(task, recipient, model_limits) in harness/context/. Tests injection, redaction, mandatory overflow, stale cache and unauthorized recipient. Exact tokenizer budget checked against target model.
7. Runtime/Jev: implement adapters only against verified installed SDK. Mock first, then isolated live smoke. Assert parent turn identity, at-most-one local send authorization, no duplicate child preflight, fallback and durable completion (v3.1 only).
8. Integration: run all applicable core H/C cases plus at least 12 synthetic workloads; collect raw artifacts and independent review. Write environment manifest and activation decision; no activation if any critical denial/provenance test fails.
9. v3.2 replay/handoff: read-only replay and soak under concurrent faults; measure latency/queue/storage growth without repeating effects.
10. v3.3 HALO: isolate evaluator/holdout, implement proposal schema workflow, M01–M10; human-reviewed PR only.

For every milestone: write the named failing tests, confirm intended failures, implement only its interfaces, rerun to PASS, review changes, record evidence and commit. Do not mark future milestones complete because the documentation exists. Add precise executable commands once language/SDK is pinned; current static commands are in README.

## Review focus

Cross-process stale writers, unknown provider delivery, changed commit during acceptance, approval revocation during execution, and concurrent budget reservations must be exercised before runtime activation. The corresponding milestones above own these cases.

## Milestone 1 implementation status

Initial Python 3.12/SQLite state controller and runtime tests are implemented.
See docs/runtime/STATE_CONTROLLER.md for the API and trust boundary. The default
guard denies all transitions; production destination guards, cleanup and outbox
integration remain owned by later milestones. This PR does not activate runtime.

## Portfolio preview status

The portfolio branch adds evidence/approval verification primitives and an
end-to-end constrained demo (docs/PORTFOLIO.md). Milestone 2 has library-level
coverage; authenticated collector/issuer services, persisted gate decisions and
nonce consumption still require integration. The demo's tiny operator allowlist
is not milestone 3's general broker/sandbox. Live OpenCode/Jev and full H/M/C
activation coverage remain unimplemented/unrun. Demo version is 0.1.0-demo;
contract version remains 3.0.1.

## 0.2.0-trial integration candidate — 2026-11-05

A persistent LOW/BOUNDED single-task runner now composes context, ready-queue,
Jev hooks, model gateway, durable outbox/budget, broker/leases, artifact receiver,
real Git targets, sandbox tests and evidence gates. Pinned OMO+OpenCode+SDK gateway
loads actual dependencies and executes coordinator then specialist without native
model-side tools. HALO accepts actual redacted trace datasets; no auto-application.

This delivers the bounded trial path, not every production profile: host namespace
activation, external inference, exact whole-request/Jev cost controls, hostile
optimizer process separation, full parallel team fairness/repair/cancellation and
MEDIUM+ independent human/QA integrations remain distinct acceptance work.
Refer to docs/trials/2026-11-06-RUNBOOK.md; do not mark H/M/C registry complete merely
because module tests passed. Existing historical status sections above are snapshots.

## Native OpenCode 2.4.1 gateway migration

The sole built-in gateway is now the native v2 SDK, with fixture and explicit
budget-confirmed Console profiles; the legacy executable integration is removed.
All nine role definitions and the controller's existing security contracts stay
unchanged. A full OMO integration with v2 remains pending, not emulated by the
native profile. The earlier trial section is a historical snapshot.

## Native free R2 first increment

Shared native session/proposal flow and explicit synthetic-only runtime fixture
are implemented in the candidate branch. The existing outbox and budget remain
host-owned. CI covers contract and fault tests and actual host worker/runtime
with a synthetic native client and injected sandbox seam; operator Bubblewrap
verification is separate. Live native-free profile is intentionally rejected
until R1 live inference, reconciliation and independent security review pass.
No new provider integration or changes to agent roles.

R2.4a candidate: actual native CLI connection through the trusted worker is
restricted to an offline diagnostic profile. Its expected outcome is HOLD,
not a proposal or live admission. Independent containment, prior external
outcome reconciliation, and live inference are still required.

R2 local-first refinement: native OpenCode owns upstream routing; no custom
HTTPS proxy or hard-coded cloud endpoint. The private local server remains
loopback HTTP. Native runtime diagnostic requests reject transport overrides
and unknown fields before launch. Hook checks are not egress enforcement.
Live adapter admission, independent review and prior-outcome reconciliation
remain open; no real model execution is claimed.

R2.5 preparation adds terminal idle failure handling and cumulative reported
token accounting across coordinator and specialist. This is not live runtime
admission or a wire-level usage guarantee. Live activation remains HOLD.

R2.5b candidate proposal contract: pinned native model, host-selected model
consistency, mandatory reservation/deadline and two-stage bounded proposal.
Synthetic transport tests only; no live CLI binding or activation. Keep the
explicit HOLD until independent review and real external evidence are available.

## R3.1 — workflow-bound specialist selection

The existing Scheduler now exposes a strict read-only workflow selector using
schema 3.0.1, exact host-approved task/revision set, workflow/turn/repository
identity, admitted specialist availability and existing dependency evidence
checks in one SQLite read snapshot. The single-task trial uses this same path.
Valera cannot expand task membership or choose unavailable roles; Explore is
not admitted in this increment. The selector does not create tasks, grant
rights, dispatch workers, or implement parallel workflow execution. Tests use
real SQLite and explicit planning-state test guards. Live model admission is
unchanged and remains HOLD. R3.2 will address durable multi-task dispatch.

## R3.2a — atomic per-task dispatch reservation

Reuse the existing Budget, Outbox and LeaseManager transaction primitives to
reserve budget and claim the provider effect in one SQLite write transaction,
with current task revision, row version, specialist and exact-scope lease
validation. The existing bounded runtime uses the same preparation path.
No provider call is made by the reservation function. Two independent task
owners can prepare distinct dispatches in the same database, while duplicate
claims, stale bindings and transaction failures fail closed. A crash after
commit but before execution retains DISPATCHING for conservative recovery.
This is per-task accounting, not an aggregate workflow budget or a complete
multi-task executor. Multi-task workspace creation, scheduling transitions,
dependency handoff, aggregate budgets and actual parallel dispatch remain open.

## R3.2b — task-bound private source layouts

Extract the existing pinned raw Git preparation into a host-only workspace
module. The bounded runtime uses the same primitive. A new task-bound API
creates a distinct private directory per persisted task/revision/owner/base
binding, rejects stale or foreign bindings and duplicate preparation, and
keeps the Git integration checkout separate from the source copy. Both copies
contain raw tracked blobs, not filtered checkout bytes. The trial limits are
1 MiB per file, 32 MiB total source and 4096 tracked entries per layout.
Partial directories remain for inspection. Workspace receipts are descriptive;
no grants, live dispatch, OS sandbox proof or cross-task artifact handoff are
provided by preparation. Actual multi-task execution remains open.

## R3.3a — verified dependency context handoff

A host-only reader resolves an explicit path/digest allowlist for one direct
DAG dependency. It checks same workflow/turn/repository and exact revisions,
DONE and reconciled producer, full evidence bundle via a trusted collector,
prior publication lease and target-pin event, private content-addressed object
bytes and the exact verified Git blob. The result is bounded mandatory
untrusted context data; the existing compiler performs redaction and context
budget checks. No direct access to another agent's workspace, automatic merge,
new grant or task dispatch. The workflow executor and dispatch-time revalidation
remain to be integrated; independent evidence collection is host-supplied.

## R3.3b — bounded sequential workflow coordinator

Compose the existing Scheduler, task-bound workspace preparation, dependency
handoff and completed-output verification through an explicitly trusted host
executor callback. A durable SQLite workflow marker prevents automatic replay
after HOLD or interruption; only one single target-pin revision per planned
task is admitted. Every declared output is checked before selecting dependent
work and again before workflow completion. No production worker binding,
automatic merge, aggregate workflow budget, authenticated independent evidence
collector or restart/resume protocol is added. Tests exercise real local Git,
SQLite, Publisher and dispatch reservations with synthetic guards and executor.

## R3.3c — bounded runtime binding (synthetic only)

A host-only fixture API binds the sequential coordinator to the existing task
runtime instead of reimplementing its gates. It uses one SQLite database and
object store, unique task evidence/pin identities, task-specific leases and
context including verified dependencies. The initial admitted roles are Backend
and Frontend, LOW/BOUNDED existing-file edits with the configured-tests gate.
Only an explicit trusted synthetic worker is accepted; the fallback command
is /usr/bin/false. No live provider mode or public workflow CLI is added.
Bubblewrap remains the default; tests inject sandbox/worker seams. Evidence
collection is local deterministic host evidence, not independent QA. Workflow
outputs remain separate commits with context-only dependency transfer; no
aggregate budget, recovery/resume or automatic merge is claimed.

## R3.4a — aggregate workflow reservation limits

The existing Budget ledger can be configured by the trusted host before
first dispatch with an immutable workflow/repository/turn and exact approved
member revisions, total token/cost ceilings and maximum in-flight provider
reservations/effects. The same SQLite write transaction checks the aggregate
and per-task budget before registering a reservation and claiming Outbox.
Unknown outcomes block new workflow reservations, and a slot is retained
until both its reservation and effect are reconciled. This is not a cap on
OS worker lifetime or an upstream wire/billing guarantee. Existing workflows
without explicit aggregate configuration retain their previous behavior.
The fixture runtime exercises the configured gate, including stopping the
second task before its synthetic worker. Process contention tests cover
atomicity. Actual parallel execution, workflow wall time and mandatory
aggregate configuration for a future parallel profile remain open.

## R3.4b — bounded parallel fixture dispatcher

The sequential coordinator now shares one batch execution core with an
explicit parallel fixture entry point (width 2–8). The host must configure
matching aggregate budget membership and sufficient in-flight slots. Ready
nodes with overlapping path resources are serialized using the existing lease
conflict predicate. Persist all admitted task IDs before preparing workspaces;
prepare and verify dependencies in the coordinator, then run distinct trusted
callbacks concurrently. Wait for the admitted batch to finish; accept only
verified outputs and stop on any HOLD. Keep unresolved batch IDs and prohibit
replay. No new batch after failure; previously admitted callbacks may finish.
Parallel fixture requires explicit injected sandbox seams: current Bubblewrap
uses preexec_fn, unsafe from a multithreaded host. Real concurrent sandbox
launch, workflow-wide wall time, interruption reconciliation, integration/merge
and live model activation remain open. Tests use a two-worker barrier, real
Git/SQLite and synthetic proposals/sandbox, not concurrent actual models.

## R3.4c — fresh-process Bubblewrap launcher

Replace the Python fork-time preexec callback with a private isolated
interpreter invoked by absolute script path, empty environment and no shell.
The fresh process applies CPU, address space, output file, descriptor and
core limits without raising inherited soft/hard ceilings, then execs only
/usr/bin/bwrap. The existing namespace/mount profile is unchanged. Timeout
and interrupted waits kill the launch process group and reap its leader;
this does not constitute independent descendant or kernel certification.
Unit and child-process tests exercise the launcher and limit failures; the
live concurrent sandbox test requires actual platform support and checks
separate network namespaces, overlapping payloads, private outputs and
limits. Keep the existing parallel workflow seam restriction until a live
E2E run is confirmed. No inference or provider activation.

## R3.4d — parallel fixture with real Bubblewrap

Allow the existing synthetic-proposal workflow to use the default Bubblewrap
backend for parallel tests after the R3.4c launcher change. Explicit test
seams remain supported only as a complete pair in parallel mode. The same
aggregate budget, task leases, durable batch marker and evidence gates apply;
no model access or fallback is introduced. The integrated live test requires
two overlapping sandbox payloads, distinct network namespaces, task-local
pinned inputs and persisted completion/evidence. CI requires the real backend
rather than accepting a skipped test. Live provider activation, workflow-wide
deadlines, interruption reconciliation and merge remain separate gates.

## R4.1 — cooperative workflow deadline

One host-owned monotonic deadline (default 300 seconds, explicit finite
limit up to 3600) covers fixture configuration, scheduling, preparation,
dispatch, bounded task work and workflow acceptance. Each task retains its
own stricter budget; the worker and sandbox receive the smaller remaining
allowance. Sandbox preparation/probe time consumes its payload allowance.
Persist the declared duration, UTC start and observed expiry with the workflow
marker. On expiry return HOLD/WORKFLOW_DEADLINE, preserve the outstanding batch
and never schedule a new callback or accept a late result. Reconcile returned
provider usage before rejecting late proposals; preserve uncertain effects.
No hard thread cancellation, bound on blocking host IO/cleanup, or automatic
recovery is claimed. Already-persisted side effects are not rolled back.
R4.2 must reconcile persisted tasks, reservations, effects and leases before
any recovery decision. No live inference or new provider admission.

## R4.2 — conservative recovery

New workflows persist their exact membership, private paths and accepted
output receipts alongside the active batch. A single-host advisory flock
on the existing database inode serializes cooperating coordinators, recovery
and integration. Recovery atomically sets interrupted DISPATCHING effects
and in-flight Jev attempts UNKNOWN, marks ACTIVE leases SUSPECT and records
HOLD; reservations, task status and late DONE remain untouched. The recovery
report enumerates exact task ledgers and optionally re-verifies accepted
outputs with a host evidence resolver. No lease release, automatic retry,
resume, promotion or legacy migration. Stop legacy/uncooperative workers
before operator reconciliation. Test includes a real process exit after
dispatch reservation and recovery idempotence.

## R4.3 — tested private integration candidate

Explicit host API integrates a fully accepted workflow at one common clean
Git base. Re-check task evidence, publication bytes and Git commits; reject
overlap, mode changes, unexpected paths and different parents. Compose raw
tracked files in a fresh private layout, run configured tests in real
Bubblewrap, reject input modification, and record a private candidate
commit and test digest. Durable integration attempt prevents replay.
No automatic merge, push, source checkout modification or deployment.

## R4.4 — eight-role bounded synthetic team

Reuse the existing scheduler, role context, task runtime and aggregate
budget for all eight host-approved specialist owners. Preserve Valera's
control-only boundary and original role prompts. This profile is still
LOW/BOUNDED, synthetic proposals, existing-file scope and deterministic
host acceptance. QA/security fixture execution is not independent QA or
security evidence. No live provider, new model permissions or general
MEDIUM/HIGH execution. Role-specific live proposal/review contracts and
independent acceptance remain R5/activation gates.

### R4 host API (local fixture profile)

For a fresh database and trusted host-approved DAG use the existing
`run_fixture_workflow` API. Inspect an interrupted workflow without dispatch
using `recover_workflow(database, workflow_id=...)` from
`harness.runtime.workflow_lifecycle`. Optionally provide a trusted evidence
collector to reverify previously accepted outputs; local synthetic artifacts
can be reopened using `fixture_evidence_collector(database, workflow_id=...)`
and issuer `frozenset({'trial-host'})`. This collector is not an independent
review service. Legacy workflows without persisted bindings require manual
inspection. Do not run old/uncooperative processes during recovery.

For a fully accepted workflow, use `integrate_workflow` from
`harness.runtime.workflow_integration` with the exact workflow ID, a new empty
private output directory outside the source/workspace/object directories,
host-approved absolute test argv, collector, trusted issuers and explicit
bounded timeout. The returned candidate is not merged. Inspect the commit
and integration test artifact before any separately authorized publication.

## R5.1e — durable native inference journal

Persist historical OMO and native RATE_LIMIT outcome cohorts separately from
new manual probe attempts. Fixed private SQLite database, single reservation,
durable per-stage dispatch markers, validated reported usage and conservative
UNKNOWN on interruption. Reopening does not replay or settle attempts.
The manual live CLI is explicitly held before server startup; the journaled
runner is an injected test candidate, not live admission. No reconciliation
authority or billing/egress guarantee is added. Actual provider reconciliation,
independent review, egress/budget enforcement and explicit scoped authorization
remain activation gates. No runtime provider profile is enabled.

## R5.1f — local historical reconciliation dossier

Read an explicitly selected historical trial without replay or migration.
Report fixed local effect states, whether a provider operation identifier
was recorded, normalized UTC timestamps, and sanitized gateway failure
categories. SQLite is opened read-only in a bounded transaction; run/gateway
metadata is advisory. Stop old processes first. The report does not establish
provider delivery or billing, authorize a retry, or clear the native ledger.
Missing identifiers/history remain unknown. No additional live admission.

## R5 alternate provider discovery — existing local OpenCode

The operator reported a successful manual OpenRouter Nemotron free response.
Add a read-only SDK catalog diagnostic against the fixed loopback server
on port 4096. This does not attach a worker, change provider selection,
or authorize inference. Ordinary Build sessions do not attest Harness
policy. Exact model identity, zero catalog price, and independent policy,
egress and accounting checks must precede a separate live profile.

### Attached catalog discovery follow-up

Generalize advisory discovery to explicit free IDs for OpenCode and OpenRouter,
report bounded provider counts and distinguish qualified identities without
weakening native policy. No automatic selection, fallback, prompt or admission.
The CLI catalog and attached server may differ.

### Attached-server role and policy staging

Generate a private deny-dispatch diagnostic profile from existing role
contracts and server plugin, with a single explicit free OpenCode/OpenRouter
model. Verify exact local generated bytes and the attached server snapshot.
No modification of ordinary config, provider state or runtime admission.
Stage opencode.json for a fresh private Location and inspect it using the
existing server without restarting or changing global configuration. Host
validation of discovery and isolation across Locations remains required.
Do not infer live safety from plugin presence or the snapshot alone.
