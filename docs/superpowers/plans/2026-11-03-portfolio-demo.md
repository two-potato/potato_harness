# Portfolio demo implementation plan

Goal: a runnable, measurable, honest demonstration of supervised automation.
Architecture: existing SQLite controller, independent record verification, a
constrained arithmetic repair in a disposable Git repository, trusted local test
collector, terminal/JSON/HTML reports. Offline baseline requires no model; an
optional Ollama adapter requests a typed proposal, never arbitrary executable code.
Stack: Python 3.12, existing jsonschema, SQLite, Git; Ollama optional.
Spec: IMPLEMENTATION_PLAN.md milestone 2 and docs/harness/v3/EVIDENCE_GATES.md.

Constraints: do not activate production runtime or claim OS isolation. Preserve
agent exports and contract schemas. Do not fabricate human approvals, live model
runs, cost savings or full H/M/C coverage. Existing controller default deny remains.
Demo permissions are a tiny application allowlist, not the future general broker.

1. Verification: add tests for provenance, bytes, task/repo/SHA/revision/policy,
   missing coverage, contradictory runs, independent review identity, action-bound
   approvals, expiration and revocation; implement trusted resolver interfaces.
2. Demonstration: test the happy path, test failure, stale evidence and forbidden
   role. Run actual Git commits and unittest subprocesses on fixed template code.
   Persist transitions with a demo-only guard and collect real elapsed time.
3. Optional Ollama: POST /api/chat, nonstreaming JSON constrained proposal;
   validate exact fields/operator, bound response/time, never execute returned code.
   Test protocol against a local HTTP server; live call only if available.
4. Delivery: one-command bootstrap, CI tests/demo, concise README, docs, measured
   case study, license/provenance note, terminal recording/video and changelog.
5. Independent review, fix regressions, refresh manifest, publish reviewed PR.

Review focus: stale evidence and cross-check coverage substitution; runtime/record
trust confused with JSON validity; inherited subprocess credentials/git config;
model response changing arbitrary files; unsafe overwrite of requested report paths.
