---
name: harness-implement
description: Use for an assigned feature or bugfix with approved scope, workspace, grants and acceptance criteria.
---

# harness-implement

Read the task-bound injected policy first. This skill never grants permissions or overrides role prohibitions.

1. Validate task revision, lease, allowed paths, dependency artifacts and remaining budget before execution.
2. Inspect existing patterns. For behavior changes, create a minimal failing regression/acceptance test and confirm the intended failure.
3. Make the smallest implementation pass. Do not weaken tests, refactor unrelated areas or extend contracts without revising the task.
4. Run relevant checks from the task. Report exact commands, outcomes, target commit and limitations. Never label NOT_RUN as PASS.
5. Publish only through the trusted publisher after fence validation; local worktree changes are not verified artifacts.
6. Hand off to QA/reviewer; do not approve your own work. New changes invalidate affected evidence and increment task revision.

Stop: revoked/expired grant, conflicting lease, unexpected secret, scope growth, missing dependency, hard budget or repeated no-progress.
Return: diff artifact, target commit, tests, contracts/migrations affected, failures and evidence refs.
