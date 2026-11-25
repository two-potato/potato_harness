# Changelog

## Unreleased — local-first readiness

- R5.1e: persistent native inference journal and historical UNKNOWN holds;
  per-stage reservation and reported usage tests. Manual live probe disabled
  pending reviewed reconciliation and activation; no external inference.

- R4.2–R4.4: durable workflow bindings, conservative interrupted-work recovery,
  tested private Git integration candidates and bounded synthetic execution
  for all eight specialist owners. No automatic replay or live activation.

- R4.1: shared monotonic workflow deadline, bounded per-stage allowances,
  durable expiry marker and fail-closed late-batch handling; no automatic
  replay or forcible trusted callback termination.

- R3.4d: admit default real Bubblewrap in parallel synthetic workflows, reject
  mixed sandbox bindings and require an integrated concurrent live test in CI.
  No live model admission or automatic merge.

- R3.4c: replace Bubblewrap preexec_fn with a fresh isolated resource-limit
  helper that execs only the fixed Bubblewrap binary; preserve stricter
  inherited limits and reap interrupted launches. Add concurrent live test.

- R3.4b: bounded parallel fixture batches through the existing workflow
  coordinator, mandatory aggregate limits, disjoint resource selection,
  durable batch IDs and failure barrier. Explicit synthetic sandbox seams only.

- R3.4a: add immutable host-configured aggregate workflow token/cost and
  in-flight reservation/effect limits in the existing SQLite budget gate;
  stop on unknown effects, test real process contention and fixture dispatch.

- R3.3c: bind the sequential coordinator to the actual bounded task runtime
  using shared SQLite/object store, task-specific identity and dependency
  context. Explicit synthetic worker only, Backend/Frontend, no live admission.

- R3.3b: compose a bounded sequential workflow coordinator using existing
  scheduler, workspace and handoff primitives, with durable no-replay marker
  and fresh completed-output verification. Trusted synthetic executor tests;
  no production worker binding or automatic merge.

- R3.3a: verify direct dependency artifacts against exact task revisions,
  trusted evidence, publication lease, pinned Git target and object bytes;
  deliver bounded untrusted context rather than shared workspace access.

- R3.2b: share pinned Git workspace preparation between the bounded runtime
  and task-bound private layouts; separate physical source and integration
  copies, reject stale/foreign bindings and never reuse incomplete layouts.

- R3.2a: atomically reserve a provider budget and claim its Outbox effect
  under the existing current task and lease bindings; use this in the
  bounded runtime and test multiple task owners and process contention.

- R3.1: add workflow-bound, revision-checked specialist ready selection
  using the existing DAG schema and SQLite scheduler. Route the bounded
  runtime through it; keep selection separate from authorization/dispatch.

- R2.5b: add the future native-free proposal contract, exercised against an
  injected fake client with a pinned real model identifier; mandatory host
  bounds and model consistency. Live configuration remains explicitly HOLD.

- R2.5 preparation: preserve native idle-only failure categories, reject
  contradictory terminal outcomes and enforce cumulative reported token usage
  against the host reservation. No live worker admission or automatic replay.

- R2: remove the guessed fixed cloud endpoint, retain native OpenCode routing
  and authenticated loopback HTTP; validate a closed native runtime request
  contract before launch. Fixture and offline modes remain non-live.

- R2.4c: deny unexpected native model HTTP methods, destinations and request
  shapes; reject observable redirects and record fixed diagnostic labels.
  Keep live runtime admission disabled pending independent egress controls.

- R2.4a: add a real native CLI offline runtime diagnostic, guard network
  namespace before dispatch, preserve UNKNOWN effects, deny all publication
  and expose a fixed post-cleanup boundary marker. Live profile still denied.

- R2: share the native two-stage flow with an explicit synthetic-only runtime
  fixture, reuse durable effect/budget and provenance contracts, and add
  regression/host integration tests. Real native-free runtime admission remains
  disabled; no provider calls or automatic fallback.

- Match native OpenCode 2.4.1's exact `default` variant sentinel in request
  hooks and response validation, while preserving model identity, empty
  variant catalog and deny-by-default rules. Reproduce the sentinel in
  positive/negative regression tests; no change to runtime admission.

- Separate native model resolution rejection into exact fixed field/variant
  categories without admitting alternate references. Add regression coverage
  and document the isolated ordinary-user probe on privileged Ubuntu hosts.

- Add a branch-only hosted Linux fallback for the offline CLI diagnostic
  on namespace-restricted operator hosts. Verify the release digest and
  require loopback-only isolation before any synthetic prompt.

- Add fixed first-denial hook reasons, sanitized idle errors and a separate
  network-isolated pre-dispatch diagnostic. Deny offline model/HTTP dispatch;
  never replay an unknown provider outcome or enable runtime admission.

- Distinguish native inference response checkpoints and report sanitized
  response shape and final hook audit on HOLD without changing admission.
  Keep unknown external outcomes and preserve the original failure on cleanup.

- Add an opt-in native free inference candidate with two synthetic role
  sessions, ordered deny-by-default hook audit, strict reported usage and
  bounded transcript validation. No runtime wiring, external CI requests or
  claimed live inference. Independent review and manual trial required.

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
