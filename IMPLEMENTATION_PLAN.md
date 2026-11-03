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
