---
name: harness-halo-propose
description: Use for offline optimization proposals based on redacted traces after a stable harness baseline exists.
---

# harness-halo-propose

Read the task-bound injected policy first. This skill never grants permissions or overrides role prohibitions.

1. Work on a read-only snapshot of permitted traces, baseline policies and train/eval data. Never access holdout examples or evaluator credentials.
2. Identify a recurring failure or overhead with measurable evidence; propose one bounded change.
3. Preserve immutable roles, Valera restrictions, approvals and required gates. Reject speed improvements that remove safety checks.
4. Submit candidate to independent evaluator with locked dataset/evaluator digests. Record all attempts; no cherry-picking.
5. Compare verified quality, failures, tokens/cost and latency with sample sizes. Do not claim significance from a few runs.
6. Produce halo-proposal schema record, reviewed PR and rollback plan. No automatic merge or live policy editing.

Return: hypothesis, trace/diff digests, evaluator/split refs, before/after metrics, regressions and rollback.
