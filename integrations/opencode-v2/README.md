# OpenCode 2.4.1 migration candidate (not activated)

The existing 1.19.5 + OMO adapter remains the default and is not modified.
OpenCode v2 changes package names, session admission/wait/message APIs,
configuration fields, plugin registration and permissions. This separate
candidate implements the two-stage proposal path against the embedded
`@opencode/sdk@2.4.1` API, with the existing role prompts and host wire contract.

**Fixture only:** `fixture/test` is the sole admitted model. A synthetic HTTP
transport never forwards requests to the network. It allows one bounded request
per stage and rejects additional/foreign requests. The v2 retry hook sets
`decision={retry:false}` before retry scheduling. No external key is needed.
The candidate cannot be selected by the runtime's normal command.

**OMO blocker:** the upstream OMO 5.1.60
[server-entry](https://github.com/code-yeongyu/oh-my-openagent/blob/v5.1.60/packages/omo-opencode/src/opencode-v2/server-entry.ts)
explicitly registers a v2 placeholder without the full v1 runtime. Do not claim
OMO composition on v2. OpenCode/OMO 1.x remains available until a compatible
full integration is tested or a separate OMO-free production profile is approved.

Source references (pinned):
- [SDK README](https://github.com/anomalyco/opencode/blob/v2.4.1/packages/sdk/README.md)
- [Retry policy](https://github.com/anomalyco/opencode/blob/v2.4.1/packages/core/src/session/runner/retry.ts)
- [Plugin session hooks](https://github.com/anomalyco/opencode/blob/v2.4.1/packages/plugin/src/promise/session.ts)
- [Session protocol](https://github.com/anomalyco/opencode/blob/v2.4.1/packages/protocol/src/groups/session.ts)

## Verification

From repository root:

```bash
node --test integrations/opencode-v2/tests/*.test.mjs
cd integrations/opencode-v2
npm ci --ignore-scripts --no-audit --no-fund
../opencode/node_modules/.bin/bun src/smoke.mjs
```

The unit tests exercise contracts, transport boundaries, bounded asynchronous
plugin initialization and hooks with injected
fixtures. The smoke test uses the actual v2 SDK with synthetic HTTP responses;
it checks the two-stage path and 401/429/503 rejection without redispatch.
No external inference, no OMO v2 certification. Direct SDK version is pinned;
the candidate now commits the transitive npm lockfile resolved on CI, with
registry origins and integrity fields checked. This is not an independent
supply-chain audit. CI must verify the locked install and runtime behavior.

Promotion gates: actual SDK smoke, review of the committed lockfile, negative tests for tool
execution and auxiliary model requests, verified token/cost accounting,
bounded cancellation, external provider transport and credential isolation,
independent security review, and a separately authorized live trial. Preserve
unknown effects from previous trials; do not replay them.

Upstream OMO 5.1.83 (November 24) still has the same v2 placeholder.
The initial CI failed closed on asynchronous plugin activation; the candidate
now waits at most ten seconds for a complete deny-only roster before dispatch.

The locked SDK smoke initially observed a denied startup request to 127.0.0.1.
Upstream v2 local provider plugins probe Ollama, LM Studio and vLLM by default.
The candidate explicitly removes these three discovery plugins using documented
negative plugin directives. All non-fixture HTTP traffic remains blocked.
