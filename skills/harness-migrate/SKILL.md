---
name: harness-migrate
description: Use when importing this harness pack into GitHub or integrating it with an existing development runtime.
---

# harness-migrate

Read the task-bound injected policy first. This skill never grants permissions or overrides role prohibitions.

1. Verify package manifest, source hashes, schema/SQL/static tests and README status.
2. Inventory target repository, dirty changes, agent/config files and runtime versions. Preserve custom files; choose separate branch/worktree.
3. Merge shared rules/navigation deliberately. Keep original role exports unchanged; new skills are separate injected segments.
4. Follow adapters/README.md to discover actual supported agent/skill/plugin APIs. Do not guess config names or enable candidate hooks.
5. Implement staged milestones from IMPLEMENTATION_PLAN.md. Require runtime negative tests before activating write access.
6. Prepare reviewed PR, inspect files for secrets and generated state, configure actual branch protection separately. Push/merge/deploy only within user authorization.
7. Record release commit, environment versions, test artifacts and rollback reference. Do not call export readiness runtime readiness.

Return: transferred paths, validation, integration blockers and exact activation state.
