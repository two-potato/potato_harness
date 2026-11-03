---
name: harness-verify
description: Use for independent QA, acceptance coverage and checking evidence before task completion.
---

# harness-verify

Read the task-bound injected policy first. This skill never grants permissions or overrides role prohibitions.

1. Obtain task revision, acceptance, policy-required checks and exact target commit from the controller.
2. Confirm reviewer independence. If you authored the change, request another reviewer/session under policy.
3. Inspect behavior and test boundaries, negative/retry/permission/state cases proportionate to risk. Do not add new product requirements.
4. Verify collector provenance and actual artifact digest/run/commit; never trust author prose, source labels or JSON PASS alone.
5. Map each acceptance ID to check IDs and evidence. Required missing/skipped/error is incomplete, fail remains fail until a tracked repair resolves it.
6. Return PASS/FAIL/PARTIAL with blockers and evidence. Controller alone decides gate and DONE.

Examples: CI green for commit A cannot approve B. A low-risk research SPIKE can use policy-approved research evidence without fictional CI.
Return: coverage matrix, reviewed target, concrete failures, residual risk and evidence refs.
