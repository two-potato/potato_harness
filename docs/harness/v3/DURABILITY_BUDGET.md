# 07 — Recovery, outbox and budget

Minimal safe recovery and budget are v3.0 core prerequisites for any write-capable execution. v3.2 adds richer handoff/replay tooling and diagnostics, not the first safety boundary.

Use SQLite on one host, local filesystem, WAL and foreign_keys per connection. One state store is authoritative; multi-host controllers require a separately tested shared storage design. Checkpoints/events/state/outbox reservations are written transactionally with CAS row_version. Keep task revision separate from row version.

## Outbox state machine

PENDING → DISPATCHING → SUCCEEDED or FAILED or UNKNOWN. Unique idempotency_key binds canonical action_digest, task revision, target, scope and approval. Atomic claiming requires CAS; record provider operation ID before finalization when available. UNKNOWN is never blindly retried. Reconciler queries actual external status/artifact; resolves SUCCEEDED/FAILED, or BLOCKED_NEEDS_HUMAN if unknowable. Retrying a proven-not-applied operation may reuse the same key only if target supports safe idempotency. Non-idempotent uncertain effects never auto-repeat.

Events and outbox are different: event dedup does not make external actions exactly-once. A signature or hash alone does not authenticate a sender. Trusted issuer credentials are outside the state DB and agent access.

## Recovery sequence

Pause new scheduling; check migration version and checkpoint/event continuity; compare task revision, source/target SHA and policies; mark crashed workers/leases SUSPECT; reconcile external effects; fence/stop workers; reissue authorized scopes only after reconciliation; invalidate stale evidence; resume from a guarded state. Never replay shell/Git/network calls when reconstructing state.

## Budgets

Track total Jev, Valera, specialists, QA, tools and retries. Reserve worst-case tokens/cost before dispatch under the same scheduler transaction; reconcile actual usage afterward. Unknown price blocks cost-constrained work unless a user-approved finite conservative estimate is supplied; record unknown separately, never zero.

Defaults per task: soft 40k/hard 70k tokens, soft $0.50/hard $1, soft 1200s/hard 2400s, max_parallel_workers 2, max_repair_attempts 4, max_no_progress_cycles 2. These are editable policy limits, not promises about provider prices. Count time since first execution separately from approval wait; timeout of pending approval 24h returns BLOCKED and requires revalidation.

Hard limit denies new dispatch and transitions to safe pause. In-flight effect follows its documented safe-point and reconciles; no kill-and-retry shortcut. Cleanup has reserved capacity and cannot perform new product actions. Budget increase requires recorded human authorization and a new budget revision.

Schema checkpoint includes pending_effect_ids, lease IDs, last_event_seq, task revision and row_version. Session handoff includes only references and redacted summaries; trusted controller validates it against state rather than trusting imported JSON.
