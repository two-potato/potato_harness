# R5.1e — keyless native inference: proposed admission procedure

Status: PROPOSED / LIVE HOLD. Not an approval, attestation, executable gate
or change to the current requirement to reconcile prior uncertain outcomes.
This document requires independent human review before any policy change.

## Architecture and scope

The operator requires a local official OpenCode 2.4.1 server, signed-out
native free provider, no API key, no Console API, no paid fallback. The
existing host owns the foreground server on authenticated loopback HTTP
127.0.0.1, with a private project, generated deny-only policy, and stable
private OpenCode data/cache/state. Native OpenCode owns upstream routing.
The remote free model is not a local LLM. No shared server attachment,
new proxy, credential forwarding, account creation or quota-state reset.

The proposed first external experiment is the existing R1 manual inert
probe, exact model opencode/beam-free, Valera then Backend, at most one
prompt per stage, at most 1024 output tokens per stage. No real project
source, no actual edit publication, no tools, no runtime activation.
An unsuccessful first stage must not admit the second. The existing
manual probe is not a durable authorization or cross-process replay guard.

## Evidence observed on 2026-11-25

Base revision: 83aa2df70c8b0d7f21bed146866de79fe1210315.
CI #219 on merged source revision 68c795468eead38895be9a7c02327301f5706702:
297 Python tests passed, no skips reported; synthetic runtime and actual
Bubblewrap integration. Operator screenshots/reports for local base:

- Clean synchronized main; 271 manifest entries matched.
- Python 3.14.4, Bubblewrap 0.11.1, execution readiness true.
- Synthetic SDK trial gateway phases OK, operator confirms DONE/DONE,
  unresolved effect count zero and gateway OK.
- Native server preflight PASS for opencode/beam-free, policy active,
  external_inference false, console_api false, exit 0.
- Unprivileged unshare failed writing uid_map. Operator used sudo only
  to create network namespace, then dropped to normal user.
- Offline diagnostic HOLD, offline_network true, offline_stop, zero model
  and HTTP hooks, zero assistant messages, cleanup_failed false, exit 2.
  This verifies the offline boundary on that host, not live egress.

These are operator-provided observations, not independently signed
attestations. No actual live inference, billing or provider-side limits
have been verified by this increment.

## Historical attempts: preserve UNKNOWN

Previous Beam/DeepSeek RATE_LIMIT and historical DEADLINE/HTTP 429
outcomes remain unresolved, per the existing runbook and integration
README. Operator states earlier requests used no API key. No reliable
provider-side history or per-request billing evidence has been supplied.
Do not assert that reconciliation is impossible merely from missing keys.
Inspect existing local sanitized records and any available official
provider records, without sending another model prompt. Record the exact
known attempt identity/date/model, diagnostic category, admitted hook
counts if available, provider outcome evidence and evidence gaps.
Do not infer non-delivery from a missing response, zero cost from free
catalog prices, or zero usage from an absent history entry.

If no authoritative outcome is available, retain UNKNOWN, the associated
reservations and any original artifacts. Do not mutate old ledgers,
replay their effects, reset provider state or switch identity/model/region
to circumvent restrictions. Manual recovery is not a settlement.

## Proposed narrow exception for independent review

If authoritative reconciliation is unavailable, a reviewer may consider
whether a genuinely new, inert diagnostic experiment can be separately
authorized despite historical UNKNOWN. It is not a retry of an existing
task, not a way to settle old usage, and not permission to evade a rate
limit. The current rule remains HOLD until an explicit policy decision
has been reviewed and adopted. Required evidence before any exception:

1. Document efforts to reconcile each prior uncertain attempt and why
   authoritative evidence is unavailable. Preserve all unresolved records.
2. Confirm the provider permits a new anonymous free diagnostic at the
   existing identity, region and quota; honor rate-limit/reset guidance.
   If permitted availability, cost ceiling or applicable limits cannot
   be established, remain HOLD. A zero-price catalog is not billing proof.
3. Independently verify confinement and egress controls on the exact
   native CLI revision, including auxiliary requests, redirects and retry
   behavior. The plugin HTTPS hook is not an origin allowlist or wire-level
   measurement. Offline isolation is not proof of live egress controls.
4. Obtain independent human review of the exact policy/code revision,
   unresolved-risk disposition, and the new experiment's bounds. Owner
   approval is not independent review. Record reviewer identity and evidence.
5. Obtain separate, single-use explicit operator authorization tied to
   the exact reviewed revision, fixed model, inert scope, bounds, expiry
   and new attempt identity. No recurring approval or general runtime flag.
6. Before dispatch, implement and verify a trusted durable attempt record
   and exclusive single-flight admission preventing duplicate execution
   across crashes and processes. Persist authorization consumption and
   dispatch intent before the external effect. A manual confirmation flag,
   JSON checklist, or chat message is not that gate. Keep records outside
   the checkout in private storage. Do not log secrets, raw prompts or
   provider response bodies. On uncertain interruption mark UNKNOWN;
   no automatic retry, fallback or lease/budget release on assumption.
   Negative tests must exercise duplicate admission, stale authorization,
   crash after reservation, changed model/revision and prior UNKNOWN.

Any failed or unverifiable condition leaves HOLD. No runtime profile
is admitted by this proposal, even if a future manual experiment passes.

## Acceptance for a future R5.2 experiment

After all applicable reviewed gates are actually satisfied, the one-shot
manual probe may be run as the unprivileged operator, using the same
stable private OpenCode state and exact authorized model. It owns local
server startup/cleanup; no sudo model execution or manual public server.
Collect a sanitized report, exit status, revision, authorization and
durable attempt receipt. PASS requires the existing probe's fixed
assignment/proposal contracts, two confirmed stages, bounded positive
reported tokens, reported zero cost, exact admitted hook sequence,
no violation, successful cleanup and exit 0. Separately record independent
network/billing evidence and any uncertainty. HOLD, quota error, deadline,
unexpected response or cleanup failure means stop, preserve records and
reconcile; never automatically repeat.

R5.2 remains NOT RUN. R5.3+ live runtime wiring, all-role model execution,
Jev live accounting and HALO real datasets remain distinct future gates.
