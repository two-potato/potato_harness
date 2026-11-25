# OpenCode 2.4.1 migration candidate (not activated)

The existing 1.19.5 + OMO adapter remains the default and is not modified.
OpenCode v2 changes package names, session admission/wait/message APIs,
configuration fields, plugin registration and permissions. This separate
candidate implements the two-stage proposal path against the embedded
`@opencode/sdk@2.4.1` API, with the existing role prompts and host wire contract.

**Fixture mode:** `fixture/test` is the sole admitted synthetic model. A synthetic HTTP
transport never forwards requests to the network. It allows one bounded request
per stage and rejects additional/foreign requests. The v2 retry hook sets
`decision={retry:false}` before retry scheduling. No external key is needed.
The fixture can now be selected explicitly by the bounded runtime using\n`--adapter opencode-v2-fixture`; this runs the generated subtotal trial only.

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

## Explicit runtime profiles (no default switch)

```sh
trial=$(mktemp -u /tmp/potato-v2-fixture.XXXXXXXX)
python3 tools/create_trial.py --directory "$trial" --adapter opencode-v2-fixture
.venv-demo/bin/python -m harness.runtime init --config "$trial/config.json" --state "$trial/state"
.venv-demo/bin/python -m harness.runtime run --state "$trial/state"
```

This requires actual Bubblewrap on the host; no key, no external inference.
CI uses the real SDK/host subprocess and an explicitly injected sandbox seam.
Synthetic results carry provenance and are excluded from actual HALO traces.

The optional `opencode-v2-console` profile is a trial path only, not certified
for live use. It admits exactly `opencode/minimax-m3` (paid), and requires
`--confirm-provider-budget` after the operator has configured a provider-wide
spend cap no larger than the dispatch reservation, and explicitly authorized
this cost. The host cannot verify the remote cap itself. Do not run it until
these prerequisites and independent security review are satisfied. The original
1.x profile stays the default. No automatic fallback or subscription purchase.

The SDK uses a private synthetic URL/model alias; the host transport alone maps
it to the fixed Console HTTPS endpoint, attaches the environment key, refuses
redirects, strips nontext/tools, admits one request per stage and reads bounded
stream usage. Actual Console balance cost and billed tokens replace SDK catalog
cost; incomplete billing fails closed, never becomes zero. See
https://opencode.ai/docs/console/api/inference/ for the cost and authentication
contract. Free chat models are restricted to the official client; no spoofing.
The test uses an injected HTTP responder, not the external service. The transport
boundary is in the trusted host process, not an OS-wide network containment proof.
