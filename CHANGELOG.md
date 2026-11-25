# Changelog

## Unreleased — local-first readiness

- Fix native CLI preflight rejection of the observed OpenCode 2.4.1 merged
  deny-only agent permissions. Preserve wildcard denial and reject unknown
  shapes and non-deny effects; add positive and negative snapshot tests.
  Real-model inference remains disabled pending separate validation.

- Add an isolated official OpenCode 2.4.1 CLI server preflight, pinned native
  client, explicit zero-price catalog admission, private plugin and no-prompt
  policy validation. No Console key or identity override. Server inference
  and runtime selection remain pending real CLI validation.

- Remove the legacy OpenCode/OMO executable integration, SDK, lockfile, old
  installation and CI path. The sole built-in gateway is native OpenCode SDK
  2.4.1 with its own pinned Bun 1.4.4, fixture and explicit-budget Console profiles.
  Shared assignment, accounting and deadline checks are retained. Old run states
  remain readable/recoverable, never replayed or automatically migrated.
  OMO v2 integration and external inference remain unverified.

The following entries record historical changes, not current dependency pins.

- Connect the isolated v2 SDK to the bounded runtime through explicit fixture
  and Console profiles, with durable provenance, environment scrubbing, fixed
  transport and provider-reported billing. Default v1 stays unchanged. Console
  live inference and actual sandbox end-to-end certification remain pending.

- Add a separate fixture-only OpenCode 2.4.1 SDK migration candidate, with
  v2 retry hook, restrictive roles and bounded synthetic HTTP transport.
  Default OpenCode/OMO 1.x is unchanged; full OMO v2 is not available in the
  pinned upstream entrypoint. Candidate is not authorized for live dispatch.

- Stop on the first observed OpenCode session retry, request bounded abort,
  and retain allowlisted provider failure categories for both model stages.
  Added mocked retry tests and real SDK local HTTP rejection fixtures.

- Fixed direct trial diagnostics CLI imports and added subprocess coverage.
- Added allowlisted Valera failure step/reason metadata, typed bridge deadlines,
  and negative fixture coverage; no raw provider errors or automatic replay.

- Evening Zen trial hardening: trial preparation installs marketplace/PyYAML
  requirements; isolated SDK smoke rejects inherited Sisyphus config;
  read-only diagnostics display only allowlisted phase and state metadata.
  Added an explicit one-shot live runbook without changing fail-closed gates.

- Added separate development/execution readiness checks. Development requires
  Python and Git, but never probes Bubblewrap or runs untrusted code.
- Added host-owned IsolationBackend contract and reused the existing Bubblewrap
  implementation for the protected runtime; no unsandboxed execution fallback.
- Model/SDK compatibility and live inference remain unchanged and untested.
- Added a shared bridge deadline and bounded SDK session cleanup for Valera
  and specialist. Optional reasoning/cache token counts no longer become
  NaN; unknown SDK cost remains unknown, without a free-price assumption.
- Added allowlisted phase diagnostics for pinned OpenCode/OMO bridge failures
  and timeouts. Raw provider stderr, prompts and credentials are not persisted;
  provider outcomes remain unknown on timeout.

## 0.1.0-demo — portfolio preview

- Runnable constrained repair with real Git commits, subprocess tests and SQLite
  state transitions; offline mode needs no model or API key.
- Evidence/approval verifier checks trusted records, artifact bytes, bindings,
  acceptance coverage, conflicting results, expiry and revocation.
- Four scenarios: accepted repair, test failure, stale evidence, unauthorized role.
- Optional loopback-only Ollama proposal adapter; protocol-tested, no live model
  execution claimed in the recorded sample.
- HTML/JSON report, terminal playback and a two-minute illustrated walkthrough.
- Atomic target pinning increments task revision and preserves row-version CAS.

This is a demo release version, not a production runtime activation or completion
of every milestone. JSON contracts remain version 3.0.1.

## Unreleased — HALO and Jev

- Durable advisory preflight/completion and typed System One transport.
- Offline bounded HALO proposals with independent aggregate evaluation and holdout ledger.
- Demo hooks and opt-in provider configuration; live Jev unverified without credentials.

## Unreleased — capability decisions

- Fresh grant authorization for bounded read/edit/test actions, role/session/revision/
  workspace/policy/fence bindings and path/secret/symlink restrictions.
- Demo requests broker authorization before writing; no callback defaults to denial.
- OS isolation, race-free file operations and trusted artifact publication remain pending.

## Unreleased — leases, artifact receiver and isolation adapter

- Atomic resource leases and reconciliation-required release.
- Trusted content-addressed artifact receiver with current lease/fence checks.
- Fail-closed Bubblewrap runner and actual availability probe; local namespaces unavailable.

## Runtime 0.2.0-trial — 2026-11-05

Added durable outbox, budget reservations, DAG scheduling, trusted role/skill context and persistent LOW runtime. Integrated pinned OpenCode 1.19.5 with actual OMO 5.1.60, isolated coordinator/worker model sessions, Jev completion gates and real-trace HALO CLI. Added reproducible preparation, trial fixture, runbook and keyless verification. Terminal states now reject unresolved effects or leases. Sandbox limitations fail closed before inference.
