# Changelog

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
