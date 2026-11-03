---
name: harness-security-review
description: Use for auth, permissions, payments, secrets, external effects, agent tool boundaries or policy changes.
---

# harness-security-review

Read the task-bound injected policy first. This skill never grants permissions or overrides role prohibitions.

1. Identify actors, assets, entry points and trust boundaries actually changed.
2. Verify object/tenant authorization, input handling, secret isolation and exact grant/approval scope.
3. Test denied paths through each installed tool/MCP and nested execution; prompts alone are not controls.
4. For high-impact actions require trusted issuer, action digest, task revision, scope, expiry/revocation and nonce. Never approve a JSON record merely because status is APPROVED.
5. Check whether stale workers can publish after lease loss and whether uncertain external effects can duplicate.
6. Report evidence-backed findings with severity, affected surface, realistic impact and fix. Avoid generic blockers unrelated to the task.

Return: controls verified, findings, required approvals and residual risk. No production probes without authorized scope.
