# 04 — Task DAG and Workspace Leases

Scheduler accepts schemas/dag.schema.json; requires unique node IDs, all dependencies present, no cycles, and verified immutable outputs of prerequisites. READY is scheduler eligibility, not a task lifecycle state. Each node references its own Task; workflow_id identifies the graph. Research uses a specialist or optional read-only Explore adapter.

Independent agents use distinct private worktrees and branches. Consumer nodes receive the exact approved dependency artifact, never an unreviewed mutable branch. A trusted integration owner creates the combined commit; integration tests and reviews run on that commit before final task completion. Passing separate branch checks is insufficient.

## Atomic lease algorithm

Use normalized relative directory/file prefixes and explicit logical resources (e.g. api:orders, db:users), not arbitrary glob intersections. Legacy backend/** normalizes to path:backend; reject unsupported patterns. Conflict if equal logical resource or one path prefix contains the other; exact file claims conflict with their ancestor directory claims. Namespace by repository identity; aliases and symlinks canonicalized by trusted filesystem adapter.

BEGIN IMMEDIATE: reconcile expired/suspect claims; check every requested resource against all ACTIVE/SUSPECT conflicting claims; allocate increasing repository fencing sequence; insert lease and all claims; commit atomically. No partial grants. SUSPECT resources remain unavailable until process/effect reconciliation completes. On expiry increment fence and stop publication; no blind reassignment.

Validate ownership and current fence at every trusted publication/external execution boundary. Long-running workers only mutate their isolated private worktree and cannot publish after lease loss. Heartbeat interval ≤ TTL/3; default TTL 90s and heartbeat 20s. Do not renew a grant after task cancellation or policy change.

FIFO scheduling within priority class; after 120s contention record BLOCKED_RESOURCE with owners/resources. Cancelled predecessors block descendants until replan; never silently drop dependencies. Rebase/merge changes target SHA and invalidates affected evidence.

SQL provides storage/indexes, not the overlap algorithm. Required runtime tests: two competing processes, overlapping parent/child paths, stale fencing, integration SHA change, dependency cancellation and starvation. No runtime results claimed by this package.
