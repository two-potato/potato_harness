# Validation — 03.11.2026

Executed locally in Python 3.12 with the exact package versions recorded in requirements-validation.txt.

- `python tools/validate_pack.py`: PASS. 14 Draft 2020-12 schema definitions, 14 structural valid fixtures, 9 source file SHA256 hashes, 10 skill frontmatter headers, state enum/policy consistency, 13 SQL tables and SQLite integrity/foreign key checks.
- `python -m unittest discover -s tests -v`: PASS, 30 tests. Negative cases include missing scope/revision/attestation/action binding, malformed SHA/digest/date, invalid Jev authority, path traversal/globs, unknown state, duplicate outbox key, stale row CAS and release inheritance.
- A date-format negative test initially failed because optional validator support was absent. Added an explicit strict date-time checker using the standard library; rerun passed.
- Independent static review completed; corrected release enable/disable inheritance, risk signal floors, missing H/M scenario registry and unresolved inherited instruction names.
- Runtime scenario registry contains H01–H22, M01–M10 and C01–C10, all NOT_RUN. Structural tests do not substitute for them.

Not run: real OpenCode/SDK/Jev calls, OS sandbox escape/mediation tests, live CI attestation and human-approval issuer checks, cross-process lease races, external-effect crash reconciliation, performance/soak, GitHub-hosted workflow or branch protection.

The 10 project skills were inspected for role/policy consistency and metadata; no live agent workflow execution is claimed. Source hashes prove correspondence to the fetched v2 export code blocks, not to an unseen installation.

Remaining work is implementation, integration and runtime validation as listed in IMPLEMENTATION_PLAN.md. This deliverable is EXPORT_READY / STATIC_VALIDATED, not READY_TO_ACTIVATE.

## Initial state-controller implementation — 03.11.2026

- TDD: 22 runtime tests first failed because the controller was absent.
- `python -m unittest discover -s tests -v`: 54 tests PASS (30 existing + 24 runtime).
- Runtime tests use actual file-backed SQLite, transactional rollback on event
  insertion failure, restart, guarded resume and two spawned writer processes.
- Production guard adapters and activation remain NOT_IMPLEMENTED; permissive
  test guards establish only state-machine/storage behavior.
- H/M/C integration scenario registry remains NOT_RUN.
- Independent code review found an integral-float version intake inconsistency;
  reproduced with a failing regression test and fixed by strict integer versions.

## Portfolio preview — 03.11.2026

- `.venv-demo/bin/python -m unittest discover -s tests -q`: 86 tests PASS
  (30 contracts, 26 controller, 15 verifier, 8 Ollama protocol, 7 demo).
- First-run `python3 tools/run_demo.py` created a fresh environment, installed
  dependencies and completed all four expected scenarios. Linux tested; use WSL
  on Windows until native behavior is validated.
- `.venv-demo/bin/python tools/validate_pack.py`: PASS.
- Recorded demo: one DONE and three BLOCKED. Real Git commits, real subprocess
  test output and artifact bytes are retained in docs/demo/report.json.
- Independent verifier review found timestamp parsing and JSON coercion issues;
  both reproduced with failing regressions and fixed. Final demo/controller/Ollama
  review found no important defects for the documented Linux scope.
- `git diff --check`: PASS. Video is an illustrated playback of measured output,
  approximately 120 seconds, not a screen recording or wall-clock benchmark.
- Live Ollama inference, OpenCode/Jev, production approval issuance, OS sandbox,
  full policy compiler and H/M/C activation validation remain NOT_RUN/unimplemented.

## HALO/Jev implementation — 04.11.2026

Durable advisory preflight/completion and System One protocol were implemented.
HALO generates offline schema-valid proposals, evaluates separate datasets and
records all attempts with a digest-bound holdout reuse cap. Reference optimization
metrics are synthetic character counts, not production token/cost measurements.
Full suite and both CLI workflows were run. Live Jev is NOT_RUN: neither provider
API key is configured. Production OpenCode session integration and OS separation
of optimizer/evaluator remain pending. Independent review findings for stale Jev
cache and HALO dataset aliases were fixed with regression coverage.
