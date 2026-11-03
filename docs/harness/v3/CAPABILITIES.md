# 03 — Capability Broker and Isolation

Grant fields and syntax are in schemas/capability-grant.schema.json. Only a trusted broker issues grants. Model-proposed grants are requests, never permissions.

Bind grants to task_id, revision, agent_id, worker_session_id, workspace_id, explicit actions, normalized relative path prefixes, TTL, policy_digest and fencing token. scope is nonempty; root access requires explicit authorization and documented reason. Deny traversal, absolute paths, symlink escapes, secrets, unreviewed tools and unauthorized network destinations. Check at every tool operation and artifact publication.

Valera gets only named control operations: propose_task, assign_authorized_worker, read_structured_result, request_approval, propose_acceptance, report. No source read/search/glob, write, shell, test, Git or engineering MCP. Runtime injects instructions and skills; loading skills never grants Valera filesystem access.

Workers use restricted containers/mounts and unique session identity. Tools, MCP and optional OMO must pass the same boundary. No nested delegation without controller authorization. Credentials are short-lived and action-bound; no host sockets or production credentials in agents.

For file effects, workers edit private workspaces; the trusted publisher validates current lease and fences the immutable artifact before integration. For external effects, route through outbox and scoped approval. Checking a token only at shell startup is insufficient for a long-running writer.

Revoke at expiration, cancellation, task revision/policy change or completion. Renewals require current policy and CAS ownership. Missing broker/sandbox is an activation blocker, not an invitation to rely on prompts.
