# R4.1 — OMO compatibility decision (2026-11-25)

Status: HOLD for runtime admission. Source inspection only; no installation,
plugin execution, model request or independent review.

Pinned upstream release: [oh-my-openagent v5.1.83](https://github.com/code-yeongyu/oh-my-openagent/releases/tag/v5.1.83)
(2026-11-24), commit `69a1863a457da06fb64ae788e335bf272f1df406`.
Potato's gateway remains OpenCode/SDK 2.4.1.

- [V2 server entry](https://github.com/code-yeongyu/oh-my-openagent/blob/69a1863a457da06fb64ae788e335bf272f1df406/packages/omo-opencode/src/opencode-v2/server-entry.ts):
  registers an ID and startup log, not the V1 execution runtime.
- [V2 startup notice](https://github.com/code-yeongyu/oh-my-openagent/blob/69a1863a457da06fb64ae788e335bf272f1df406/packages/omo-opencode/src/opencode-v2/startup-notice.ts):
  agents, tools and hooks are not active in the OpenCode 2 plugin.
- [Native package](https://github.com/code-yeongyu/oh-my-openagent/blob/69a1863a457da06fb64ae788e335bf272f1df406/packages/omo-native/package.json):
  separate `omo-ai` 5.1.83 CLI with Senpi 2026.11.23; not an OpenCode plugin.
- [Migration guide](https://github.com/code-yeongyu/oh-my-openagent/blob/69a1863a457da06fb64ae788e335bf272f1df406/docs/guide/migrating-from-opencode.md):
  setup imports credentials, MCP configuration and skills into user state;
  OpenCode tool permissions and plugin hooks are not carried across.

Decision: do not install the limited V2 plugin, restore legacy V1, invoke
`omo setup`, import credentials or introduce a second orchestrator. Native
OMO is a possible separate adapter, not a required dependency or an automatic
fallback. Its supported proposal-only mode, exact role/model identity,
tool/delegation denial, bounded request count, accounting, no-replay behavior
and isolated config must be demonstrated before runtime binding. Use a private
fixture and an explicitly reviewed pinned dependency tree; no normal user
state or external inference in compatibility tests. There is no new OMO
runtime profile in this increment.

The existing native policy still rejects unapproved active external plugins;
it now additionally requires exactly one local trusted policy identity.
This snapshot check is not proof that an unexpected plugin never executed
during server startup. The private launch configuration and independent review
remain necessary. Native standalone admission is unchanged (HOLD).
