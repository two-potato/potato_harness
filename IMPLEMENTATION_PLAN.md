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
