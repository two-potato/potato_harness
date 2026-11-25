# Native OpenCode SDK 2.4.1 gateway

The single built-in gateway uses pinned `@opencode/sdk@2.4.1` and Bun 1.4.4.
There is no installed older SDK, executable fallback or OMO plugin. Valera and
all eight specialist prompts are preserved; host assignment, grant, lease,
budget, evidence and outbox contracts remain unchanged.

## Install and verify

From repository root:

```sh
python3 tools/prepare_trials.py --install --verify
```

Or verify only the native integration:

```sh
cd integrations/opencode-v2
npm ci --ignore-scripts --no-audit --no-fund
node node_modules/bun/install.js
npm test
node_modules/.bin/bun src/smoke.mjs
```

Only the locked Bun install script is explicitly run. The SDK smoke uses real
SDK sessions with synthetic HTTP and mocked Console transport, no credentials
or external inference. CI also uses the actual SDK worker and runtime with an
explicitly injected sandbox seam. Actual Bubblewrap is needed on the operator
host for a complete local fixture. No untrusted test code receives secrets.

## Runtime profiles

- `opencode-v2-fixture`: default trial generator, exact generated subtotal
  fixture, no key or external request. Synthetic provenance is recorded and
  excluded from actual HALO inference evidence.
- `opencode-v2-console`: explicit paid `opencode/minimax-m3` with confirmed
  provider-wide budget and key. Direct runtime configurations without an
  adapter select this profile, but still require explicit budget confirmation.
  The remote cap must be independently checked; this is not live-certified.

See the [current runbook](../../docs/trials/2026-11-06-RUNBOOK.md) for commands.
Old initialized states must not be migrated or dispatched in place; status
and recover remain available. The operator may separately configure a trusted
absolute custom worker argv, not a built-in legacy fallback.

## Safety and remaining gates

Native Plugin API removes tools, denies permissions, disables automatic
discovery of local model servers and denies SDK retries before dispatch.
The transport admits at most one request per stage, only the fixed endpoint,
no redirect, no forwarding of SDK authorization headers or auxiliary tools.
The external key is passed only by the trusted host transport. Missing billing
or a coordinator exhausting the reservation prevents specialist dispatch.
Console-reported balance cost replaces synthetic catalog cost. The SDK's
embedded fixture URL never makes a network request.

Independent supply-chain/security review, provider cap verification and a
separately authorized external inference trial are still required. No
provider-wide hard cost guarantee, OMO composition or production activation
is claimed. Upstream OMO's v2 entrypoint was a placeholder in the versions
inspected during migration; a future full v2 integration requires separate review.

Pinned upstream references:
- https://github.com/anomalyco/opencode/blob/v2.4.1/packages/sdk/README.md
- https://github.com/anomalyco/opencode/blob/v2.4.1/packages/core/src/session/runner/retry.ts
- https://github.com/anomalyco/opencode/blob/v2.4.1/packages/plugin/src/promise/session.ts
- https://opencode.ai/docs/console/api/inference/
