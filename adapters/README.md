Implemented advisory Jev transport/hooks: see docs/runtime/JEV.md. The following activation contract still applies to the general OpenCode runtime, not the Python demo.

# Runtime adapter activation contract

A bounded native OpenCode 2.4.1 gateway is supplied in `integrations/opencode-v2/`; see its README for actual SDK fixture coverage and limits. General tool-mediated production activation remains unverified. The original agent text is preserved.

Resolve INHERIT names using the explicit alias map in rules/PRIORITY.md; do not rely on searching Notion or an absent v2 checkout at runtime. Inject instructions and selected skills before dispatch, especially for Valera with no source-reading tool.

Record in an environment manifest: OS/container, runtime binary/version, SDK package/version, actual config schema, model provider and IDs, tool inventory, skill discovery paths and plugin hashes. No placeholder model ID is operational configuration.

Implement typed adapter operations: reserve_preflight(turn_key), propose_task(contract), assign(task_id, worker_session), inspect_structured_result(task_id), request_approval(action_digest), propose_acceptance(task_id, revision), publish_artifact(lease_id, fence, artifact), collect_evidence(provider_run), reconcile_effect(effect_id). These are harness interfaces to implement, NOT claimed native OpenCode APIs.

Preflight hook must identify real user-turn IDs and finish/reserve before first delegation. Completion is a separate durable hook after base PASS. Unknown delivery never blindly retries. Provider errors become explicit UNAVAILABLE/UNKNOWN.

Acceptance tests: Valera direct read/write/shell/MCP denied; specialist path/network limits enforced; original prompt and injected rules loaded; skill selected and loaded without enlarging tools; duplicate turn no extra reservation; worker restart cannot reuse expired fence; forged CI/approval rejected; changing target commit invalidates gates; no production credentials accessible.

OMO is not installed by the native gateway. If a complete compatible v2 integration is enabled later, reject duplicate orchestrators, tools and hooks until compatibility tests pass. The package cannot establish SDK availability without the target machine.

See [R4.1 compatibility decision](OMO_COMPATIBILITY.md) for the pinned upstream
source inspection and admission blockers. OMO remains optional and inactive.
