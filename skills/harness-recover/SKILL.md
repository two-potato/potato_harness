---
name: harness-recover
description: Use after worker crash, session restart, stale checkpoint, cancelled task or uncertain external operation.
---

# harness-recover

Read the task-bound injected policy first. This skill never grants permissions or overrides role prohibitions.

1. Pause new scheduling for the affected workflow. Read trusted state/event/outbox records through approved adapter.
2. Compare revision, row_version, policy, commit and last event. Mark affected leases SUSPECT.
3. Ask trusted reconciler to inspect external operation IDs and actual outcome. UNKNOWN is not a failed action and must not be blindly retried.
4. Fence/stop stale workers before releasing resources. Preserve audit/evidence and private worktree for diagnosis.
5. Recompute grants, dependencies, budget and evidence freshness before proposing resume_state.
6. If an effect cannot be reconciled, report BLOCKED_NEEDS_HUMAN with exact unknown; do not claim cancellation/completion.

Return: recovered state, unresolved effects, evidence invalidations, resource status and safe next action. Replay reconstructs state only, never executes effects.
