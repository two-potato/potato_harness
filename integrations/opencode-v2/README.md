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

### Hosted Linux diagnostic fallback

The branch-only Native CLI offline diagnostic workflow is a development
fallback for hosts that reject unprivileged user/network namespaces. It checks
namespace support first, verifies the official Linux CLI release SHA-256,
warms the native catalog using the no-prompt preflight, then runs the offline
probe in a distinct loopback-only namespace. No host privilege changes,
provider credentials, external inference or fallback to a live prompt.
A completed job confirms only diagnostic evidence, not successful inference
or isolation on the operator host. The workflow is not a runtime dependency.

The offline probe reproduced the same pre-dispatch model identity rejection
on both operator Ubuntu and hosted Linux. Resolution diagnostics now separate
provider and model ID mismatches (including a qualified model ID), missing or
invalid fields, and null/empty/default/named/invalid variants. Hosted offline evidence identified
exactly the `default` sentinel. OpenCode 2.4.1 `ModelResolver.withVariant`
normalizes that sentinel to undefined without applying a variant overlay.
The native hook and response checks therefore accept only undefined or the
exact string `default` for the same provider and model. The preflight still
requires an empty variant catalog and unchanged agent configuration. Null,
empty, other named variants and alternate model/provider IDs remain denied.
Diagnostic labels never expose raw observed identifiers. A privileged host may use `sudo unshare --net` solely to create the
namespace and bring up loopback, then drop to its normal unprivileged operator
before executing the probe. Never run the CLI or candidate code as root.

## R2 native runtime fixture (no live activation)

The explicit `opencode-v2-native-free-fixture` profile uses the same native
session/proposal/audit flow as R1 with an in-process client fixture. It does
not start a real CLI, import the SDK in that worker mode, send network traffic,
or accept a real model. The synthetic model ID is
`opencode/potato-runtime-fixture-free`. The real `opencode-v2-native-free`
profile remains rejected. Existing embedded fixture and Console profiles are
unchanged. Runtime Outbox, budget, grants, leases, publication and HALO's
synthetic exclusion are reused. A failed worker remains UNKNOWN; no replay.

After CI, from the repository root as an ordinary user:

```sh
trial="$(mktemp -d)/trial"
python3 tools/create_trial.py --directory "$trial" --adapter opencode-v2-native-free-fixture &&
.venv-demo/bin/python -m harness.runtime init --config "$trial/config.json" --state "$trial/state" &&
.venv-demo/bin/python -m harness.runtime run --state "$trial/state"
.venv-demo/bin/python -m tools.trial_diagnostics --state "$trial/state"
```

Expected DONE and synthetic provenance. CI uses a sandbox seam; operator
Bubblewrap testing remains separate. This does not prove actual native CLI
HTTP delivery, provider billing or independent review. R1 manual attempts with
Beam and DeepSeek returned RATE_LIMIT (operator reports); their external
outcomes remain unresolved. Before any live admission, reconcile them,
complete independent human review, enforce verified network/budget limits,
and confirm successful native inference. Never switch models or retry to evade
provider restrictions. No activation by environment variable or flag.

## R2.4a: native CLI offline runtime diagnostic

The explicit `opencode-v2-native-free-offline` profile connects the real private CLI
and native client to the runtime, but only in a distinct loopback-only Linux
network namespace. The Python host rejects a missing namespace before effect
reservation; the worker and server launch independently verify it again.
The model hook intentionally denies the first request. A fixed advisory
`offline_boundary/ok` event is emitted only after the final audit confirms
`offline_stop`, zero model/HTTP admissions, no assistant and successful cleanup.
Expected runtime result is HOLD/BLOCKED, not DONE. The claimed diagnostic effect
is retained UNKNOWN by the existing generic fail-closed outbox behavior; no
proposal or artifact can be published, and HALO excludes this provenance.
The profile cannot activate live inference; no automatic retries or fallback.

Generate a fresh trial and initialize outside the namespace:

```sh
trial="$(mktemp -d)/trial"
python3 tools/create_trial.py --directory "$trial" --adapter opencode-v2-native-free-offline --model opencode/deepseek-v4.1-flash-free &&
.venv-demo/bin/python -m harness.runtime init --config "$trial/config.json" --state "$trial/state"
```

On a host with a verified cached native catalog, create the namespace with
`sudo unshare --net` solely for network setup and drop to the operator:

```sh
sudo unshare --net -- sh -ec '
  ip link set lo up
  exec runuser -u "$1" -- env HOME="$2" PATH="$3" POTATO_OUTER_NETNS="$4" \
    "$5" -m harness.runtime run --state "$6"
' sh "$(id -un)" "$HOME" "$PATH" "$(readlink /proc/self/ns/net)" \
  "$PWD/.venv-demo/bin/python" "$trial/state"
.venv-demo/bin/python -m tools.trial_diagnostics --state "$trial/state"
```

Never run the candidate as host root. Expect exit 2 from run and the final
advisory boundary marker. An earlier HOLD without the marker is not a passed
diagnostic. Do not reuse this trial state for inference. This is an offline
network boundary, not full native transport containment or a billing proof.

## R2.4c: local-first transport boundary and closed runtime contract

The Harness connects to its private OpenCode server via authenticated loopback
HTTP. No local HTTPS service, proxy, alternate provider or upstream URL
override is introduced. The prior hard-coded candidate cloud endpoint was
not observed in the native CLI and has been removed. Native OpenCode owns
its model route. The upstream model hook still validates primary session,
model identity, request count, POST, HTTPS and fresh JSON-body shape;
observable redirects, retries and WebSocket remain rejected. The HTTPS
check applies only to an upstream model call, not the local client.
It is not an origin allowlist, wire-payload check or proof of egress control.
The hook cannot undo a redirect already followed by the upstream transport.

Both native runtime diagnostic modes share a closed host request contract:
explicit mode/model match, bounded subtotal objective and scope, existing
output allowance, bounded host deadline, and no provider/URL/key/fallback/
tool/permission/activation overrides. Only the trusted launch binding
chooses the transport. A host project directory is not forwarded to native
OpenCode. Unknown fields fail before launch. Synthetic fixture requests use
an inert .invalid URL object and never send it.

Live native-free runtime admission remains disabled. The previously observed
RATE_LIMIT attempts are not reconciled by these changes. Independent review,
verified billing/limits and evidence of actual upstream behavior are still
required for live activation. Keep the confirmed offline namespace and
Bubblewrap checks, Outbox reconciliation and deny-by-default control.

## R2.5 preparation: terminal outcome and cumulative accounting

Native sessions can terminate with an idle failure and no assistant. Preserve
only the known diagnostic category (RATE_LIMIT, FREE_QUOTA, AUTH, etc.); reject
failed/interrupted/duplicate idle events even when assistant text exists. No
specialist follows an invalid coordinator outcome, and no automatic replay or
model fallback is introduced. The host now passes its reserved token allowance
into native diagnostic modes; the shared flow checks cumulative reported usage
and blocks another stage when fewer than two tokens remain. This is a reported
usage gate, not an independent pre-dispatch limit on upstream input tokens.
The host's final accounting and UNKNOWN effect semantics remain unchanged.

This is live-admission preparation, not activation: no new live worker mode,
no provider dispatch from CI, no change to native route selection or local
HTTP. Independent review, prior-outcome reconciliation, actual provider limits
and successful real inference remain required before a live runtime trial.
