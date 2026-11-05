# Pinned OpenCode / OMO integration

Verified locally: OpenCode 1.19.5, @opencode-ai/sdk and plugin 1.19.5,
oh-my-opencode 5.1.60 (upstream renamed oh-my-openagent), Bun 1.4.4.
package-lock.json pins resolved dependencies/integrity. All installs are local.
OMO is SUL-1.0 licensed; it is an external dependency, not bundled MIT code.

```sh
npm ci --ignore-scripts --no-audit --no-fund
node src/bootstrap.mjs
node_modules/.bin/bun test tests
PATH="$PWD/node_modules/.bin:$PATH" node_modules/.bin/bun src/protocol-smoke.mjs
```

The last command starts the actual pinned OpenCode server, imports/initializes the
actual OMO plugin, asserts the composed configuration marker, sends bounded model
requests to a local HTTP fixture, verifies the bounded proposal and cleans up.
It is real SDK/plugin integration, but NOT live external model inference.

The plugin composes OMO's configuration/context compaction with Harness-owned
roles. It disables OMO's Sisyphus/orchestration, autonomous continuation, updates,
telemetry, external MCP and model fallback. Only Valera is primary. Native model
filesystem/shell/MCP/delegation tools are denied. Trusted Python runtime performs
all scoped edits, sandbox tests and state transitions. OMO adds no parallel
controller and cannot grant execution privileges. Additional OMO tools/hooks are
intentionally not exposed; arbitrary OMO toolkit behavior is outside this profile.

Official opt-out flags DO_NOT_TRACK=1, OMO_DISABLE_TELEMETRY=1,
OMO_DISABLE_POSTHOG=1 and OMO_SEND_ANONYMOUS_TELEMETRY=0 are set before factory
initialization. A prior extended smoke attempt was blocked by automatic review
when PostHog egress was observed; the unsafe configuration was replaced with
these source-verified supported opt-outs. No telemetry approval is assumed.

worker.mjs reads a bounded JSON request on stdin, starts a fresh provider project
in a host-owned temporary directory (never an untrusted checkout), selects an
explicit specialist, obtains JSON edits and measured SDK token/cost usage, and
returns data only. It uses the pinned executable path, clears ambient configuration
and blocks model-side tools. The provider key stays in the trusted gateway process.
Model-side shell execution is never an alternative to a failed sandbox.

OpenCode SDK/server is the pinned 1.x API. OMO supports this API and a distinct
2.x entrypoint. This implementation verifies the installed 1.x entrypoint;
it does NOT claim an untested OpenCode 2.x migration.

worker request: role, prompt, model=provider/model, output_token_allowance, coordination.
Valera receives coordination objective/scope only, then host validates the assignment
before a separate specialist session. Token/cost usage from both calls is summed.
The SDK's actual HTTP output-token limit is set through the pinned model's
limit.output and tested against the local provider fixture. The host still must
reconcile actual reported usage and stop on budget overrun/unknown cost.

Sources checked 2026-11-05: https://opencode.ai/docs/plugins/,
https://opencode.ai/docs/sdk/,
https://github.com/code-yeongyu/oh-my-openagent and the installed package types.
Upstream limit behavior checked in v1.19.5 session/llm/request.ts and transform.
