# 06 — Risk policy and Auto Jev Completion

policy/checks.json is the single machine-readable minimum. Task acceptance can add checks; model output cannot subtract them. Trusted diff/action analysis sets a risk floor: auth/payments/secrets/permissions, production/destructive operations and schema/data migrations are at least HIGH. Cross-service/public-contract changes at least MEDIUM. Sensitive scope cannot be called LOW because a model chose it.

| Task/risk | Minimum | Independent review | CI |
| --- | --- | --- | --- |
| SPIKE LOW, read-only | pinned source + research acceptance evidence | basic structured review | not required unless acceptance says so |
| BOUNDED LOW | relevant static/behavior checks + acceptance coverage | basic review; independent if specified | only if required by acceptance/project policy |
| Any MEDIUM | relevant checks + contract checks where touched | independent QA | required |
| Any HIGH/CRITICAL | MEDIUM + security/architecture review + rollback plan | independent QA and specialist reviewer | required; e2e where applicable |

Production/destructive/privileged/high-blast-radius actions always require authenticated human approval before execution, regardless of task labels. HIGH read-only research requires stronger review but not a meaningless production approval. ARCHITECTURAL has minimum MEDIUM. SPIKE cannot perform production effects or silently become implementation.

## Jev contract

Preflight: one durable reservation keyed by session_id + user_turn_id before first delegation. Duplicate events return existing result; tool continuations and child tasks do not trigger it. Reservation has RESERVED/SENT/RESULT/UNAVAILABLE/UNKNOWN states. Crash in uncertain network delivery becomes UNKNOWN; no blind retry. Exactly-one remote execution cannot be promised without provider idempotency. Required invariant is at-most-one local send authorization.

Completion: core v3.0 policy disables network completion but records SKIPPED_BY_POLICY in COMPLETION_AUDITING. v3.1 enables one reservation keyed by task_id + revision + target SHA + evidence digest + policy version after base PASS. Timeout 10 seconds, no same-key retry. Provider response schema accepts CLEAR/REVIEW_RECOMMENDED/INCOMPLETE/UNAVAILABLE only. Bad output maps UNAVAILABLE. No source code, credentials or raw conversation sent.

CLEAR never overrides a failed gate. UNAVAILABLE proceeds only if all hard checks pass. A concrete gap enters REREVIEW at most once per revision; QA resolves it with evidence or requests REPAIR. Mere Jev uncertainty cannot waive checks or loop forever. INCOMPLETE is advice, not authority. Persist gap resolution and re-evaluate gates; do not recall Jev solely for the same gap resolution.

Requested policy changes require a reviewed policy version and new task revision. No caching across turns may suppress the required preflight reservation. If provider is unavailable, reserve and record UNAVAILABLE without inventing a network result.
