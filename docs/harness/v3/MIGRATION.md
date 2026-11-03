# 10 — GitHub migration and rollback

Repository-neutral package. Choose a new harness repository or a reviewed integration branch; no hard-coded 24sparts/servio paths. Existing project instructions/configuration are merged deliberately, never overwritten.

## Transfer

1. Unpack into a clean directory. Run manifest verification and static validation.
2. Inventory target Git status, branch, existing AGENTS.md, agent definitions, skills, configs and plugins. Back up user customizations. A dirty target requires preserving changes before integration.
3. If this is a new repository: git init -b main; review files; git add selected paths; git commit. Choose the actual GitHub remote, visibility and owner before push; this package does not create a repository automatically.
4. For an existing project create a branch, copy docs/policy/schemas/tests into dedicated harness paths and adapt relative references together. Merge AGENTS.md navigation; retain product instructions.
5. Keep original agents/ byte-identical; verify sources.json. Map agent files and project skills into the actual runtime's supported directories only after checking installed runtime documentation and testing discovery. Do not install unverified config/plugins by copying guessed API keys.
6. Run static CI, independent review and runtime milestone tests. Configure branch protection/required checks on GitHub separately and verify they are effective. CI file alone does not enforce branch protection.
7. Pin real OpenCode/SDK/provider/plugin versions and exact model IDs in an environment manifest after successful smoke. OMO disabled until its compatibility suite passes.
8. Enable write-capable execution only after broker/sandbox/fencing/outbox/approval and evidence tests pass. No production credentials in the sandbox.

## Promotion

EXPORT_READY: complete files, manifest and instructions. STATIC_VALIDATED: validator + schema fixtures + SQL checks pass. READY_TO_TEST: runtime code/dependencies materialized. READY_TO_ACTIVATE: applicable runtime/mocked/live tests pass on pinned environment. PRODUCTION_ELIGIBLE: additional explicit user authorization for actual production integration. Status of one level never implies another.

## Rollback

Pause dispatch; reconcile in-flight effects; revoke grants/fence workers; checkpoint/export state; restore previous code/config and compatible DB snapshot or tested forward migration. Never git-revert a schema migration against live newer state blindly. Retain audit/evidence; do not erase failures. Record rollback commit and unresolved effects. Importing docs into Git is reversible; external actions may not be.
