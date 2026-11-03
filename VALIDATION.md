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
