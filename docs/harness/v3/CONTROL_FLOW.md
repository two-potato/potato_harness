# 01 — State machine and Task Contract

Specification 3.0.1. One trusted controller owns state, audit and final completion. Valera proposes assignments and logical acceptance only.

## Transition contract

NEW → CLASSIFIED → PLANNED → ASSIGNED → EXECUTING → REVIEWING → VERIFYING → COMPLETION_AUDITING → ACCEPTED → DONE.

VERIFYING → REPAIR → ASSIGNED; COMPLETION_AUDITING → REREVIEW → VERIFYING or REPAIR. Each active state may enter BLOCKED, NEEDS_HUMAN_APPROVAL or CANCELLED. DONE/CANCELLED are terminal. No reopening: create a new task linked to the old one.

BLOCKED and NEEDS_HUMAN_APPROVAL store resume_state, blocker/approval ID and previous revision. Resume is allowed only after trusted resolution and complete revalidation of state guards. Resume to EXECUTING requires a fresh grant/lease; resume to ACCEPTED/DONE is prohibited, reroute to VERIFYING. Pending approvals never authorize execution by themselves.

Completion audit is a durable state for all versions. If disabled in the release profile, persist SKIPPED_BY_POLICY and proceed after base gates. If enabled, reserve a unique provider attempt keyed by task_id + revision + target_commit + evidence_digest + policy_version. Persist result or UNAVAILABLE; never rely on an untracked side call.

## Guards

- CLASSIFIED: preflight reservation for parent user_turn_id recorded. A failed/unavailable Jev does not block classification. Child tasks reference the same parent preflight; do not create additional calls.
- PLANNED: objective, non-goals, acceptance and risk floor agreed; DAG acyclic.
- ASSIGNED: all dependencies verified, owner available, scope and budget nonempty, required checks computed by trusted policy.
- EXECUTING: valid task-revision-bound capability; exclusive lease for writes; no unresolved approvals; budget reserved.
- REVIEWING: immutable artifact target exists; dirty worktree is not a review target.
- VERIFYING: review requirements from policy/checks.json satisfied. Independent QA is mandatory for MEDIUM+ and when acceptance requires it, not universally for LOW/SPIKE.
- COMPLETION_AUDITING: base verification PASS on exact target, revision and policy.
- ACCEPTED: completion step resolved, required independent reviews and approvals present, no unresolved blockers; Valera logical acceptance stored.
- DONE: repeat gate freshness/CAS checks transactionally; revoke grants, release leases and record final result. Cleanup failure blocks completion rather than falsely recording safety.
- REPAIR: new hypothesis; increment revision; invalidate changed evidence, contexts and grants; enforce attempt and no-progress caps.
- CANCELLED: mark cancellation requested, stop/reconcile workers/effects, then revoke and release; unresolved external effects remain BLOCKED, not falsely cancelled.

## Concurrency and revisions

Task revision changes when scope, acceptance, target commit or plan changes. SQL row_version changes on every state write. CAS uses row_version; completion identity uses task revision, not row_version. Persist state, event and outbox reservations in one transaction. Events have unique event_id/idempotency_key. Never independently edit task_json and state columns.

schemas/task.schema.json is the canonical full task snapshot. Intake may be an incomplete request in an ingress queue; it is not a valid persisted Task until required fields are populated. State enum does not grant permission to jump transitions. Cross-field guards are separate from structural validation.
