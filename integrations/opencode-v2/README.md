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

## Native CLI server candidate (preflight only)

A separate path starts the installed official OpenCode 2.4.1 CLI via
`serve --stdio --hostname 127.0.0.1 --port 0`. It uses an owned process,
random loopback password, clean project/config and stable private OpenCode
data under `~/.local/state/potato-harness/opencode-free`. The server uses its
own native signed-out provider; no Console key or user-agent override is
passed. Normal desktop/CLI credentials are not copied. Do not clear this
state to reset quotas. Native free usage is subject to provider restrictions.

After installing the locked dependencies, choose a model from the official
OpenCode catalog and run a no-inference probe:

```sh
integrations/opencode-v2/node_modules/.bin/bun \
  integrations/opencode-v2/src/server-probe.mjs opencode/<available-free-model>
```

The probe checks the exact CLI/server version, active private plugin, all
nine deny-only roles, a single enabled native model with explicit zero input,
output and cache prices, disabled tools and bounded output. Agent permissions
must include a wildcard deny; duplicate wildcard denies and the observed
browser/skill-browser denies are accepted, but unknown shapes or any non-deny
rule are rejected. It never submits
a prompt. The plugin contains candidate guards against duplicate dispatch,
auxiliary generation and retries; unit tests exercise these hooks, but
their actual CLI execution must be validated before enabling inference.
The preflight path is not yet a runtime profile and does not replace the
existing fixture/default config. Do not run the Console profile as part
of this migration. Full runtime wiring and real-model validation are separate.

## Native free inference R1 candidate (manual, not runtime)

After the preflight PASS, independent review and explicit authorization for
external inference, run from the repository root:

```sh
integrations/opencode-v2/node_modules/.bin/bun \
  integrations/opencode-v2/src/server-inference-probe.mjs \
  opencode/<available-free-model> --confirm-external-inference
```

One private server, two separate sessions, fixed inert synthetic proposal only.
No project files or model output are published. A strict policy audit allows
one model-request hook and one HTTP-request hook per role, in order, with no
retry, permission attempt, unexpected dispatch or WebSocket. The audit records
fixed local event labels and is deleted on cleanup. PASS requires validated
assignment, exact synthetic edit, complete bounded transcripts and explicit
zero reported cost with positive bounded token counts (1024 output per stage).
Hook counts are not independently measured network traffic; zero reported cost
is not a provider billing guarantee. HOLD after dispatch means an unknown
external outcome; do not retry automatically or reset provider state.
The probe is not installed/run by CI, does not enable the runtime profile, and
is not production or sandbox certification. No real inference is claimed until
an operator supplies evidence from the manual trial.

On HOLD, the report includes a fixed failure checkpoint, a sanitized response
shape (counts and boolean/enum checks only), final hook audit counts, and
cleanup status. It never prints model text, raw provider errors, session IDs
or credentials. These diagnostics do not establish provider delivery or billing
and do not authorize replay of a prior unknown attempt. Reconcile the prior
outcome separately before any newly authorized manual trial.

### Offline pre-dispatch diagnostic

If the live report has no assistant and no admitted model/HTTP hooks, use the
separate diagnostic below rather than replaying an unknown provider attempt.
Linux user/network namespaces and iproute2 are required. No host sysctl changes,
no network fallback; an unavailable namespace or uncached catalog is a HOLD.
Run from the repository root:

```sh
POTATO_OUTER_NETNS="$(readlink /proc/self/ns/net)" \
  unshare --user --map-root-user --net -- sh -c \
  'ip link set lo up && exec "$@"' sh \
  integrations/opencode-v2/node_modules/.bin/bun \
  integrations/opencode-v2/src/server-offline-probe.mjs opencode/beam-free
```

The runner verifies a distinct network namespace with only loopback, then
creates one local synthetic session. The plugin additionally denies the model
request before its HTTP hook. The report always exits HOLD (code 2), never
claims inference. A first violation of offline_stop means the request reached
the deliberate pre-transport boundary. Other fixed violation_reason values
locate an earlier failure; idle outcome/error categories are also reported.
No raw provider text or network addresses are emitted. This is not complete OS
sandbox certification and does not resolve past provider-side unknown effects.
