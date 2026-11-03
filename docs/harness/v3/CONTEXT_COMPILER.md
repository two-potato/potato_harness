# 02 — Context Compiler and Provenance

Compile context for an authorized worker from user goal, approved task revision, policy and source snapshot. Valera receives structured summaries; source inspection belongs to a specialist or available read-only Explore adapter.

Precedence: host/user scope → approved restrictions and role prohibitions → role duties → approved task → relevant skills → referenced facts. Repository comments, tool output, issues and external documents are untrusted data. A segment marked trusted is accepted only through a trusted issuer, not its own label.

Include compiler_version, task_revision, source_commit, policy_digest, role_prompt_hash, recipient_session and per-segment digest/provenance. Hash canonical UTF-8 content. Cache key covers all these identities. Invalidate on any change.

## Exact budget rule

Compute input_capacity = model_context_limit - reserved_output_tokens - protocol_overhead_tokens. All mandatory and optional segments count toward it. max_tokens is the lower of task input limit and input_capacity. If mandatory tokens exceed max_tokens, return BLOCKED_CONTEXT_OVERFLOW; do not truncate safety/acceptance/role text. Request decomposition or an authorized larger context. For remaining optional capacity allocate code 45%, contracts 25%, diagnostics 20%, buffer 10%; unused allocations may be reassigned without dropping mandatory material.

Load only relevant skills. Redact secrets before tokenization, storage and provider transmission. Send Jev no source code or raw transcripts. Unredactable content blocks external transmission. Store minimized audit metadata with retention limits (default 30 days; security evidence according to explicit project policy). Prompt body hashes persist, private full prompts do not enter traces.

Tests: oversized mandatory context blocked; stale revision invalidated; injected tool instructions cannot change policy; unauthorized recipient denied; redacted context contains no secret fixture; identical inputs yield identical digest.
