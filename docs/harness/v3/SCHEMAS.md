# 09 — Canonical schemas and SQLite

Complete JSON Schema files are in schemas/, valid fixtures in fixtures/valid/. Version 3.0.1 is used consistently. Objects reject unknown fields; IDs/scopes are nonempty; SHA algorithms and digest formats explicit. Format checking must be enabled in the validator.

Contracts: task, evidence-record, evidence-graph, human-approval, context-pack, capability-grant, dag, lease, checkpoint, budget, jev-result, halo-proposal, gate-decision and handoff. SQL: state/001_init.sql.

Structural validation is not authorization. Trusted runtime separately validates graph cycles/references, actor independence, issuer authenticity, approval action binding/expiry/revocation, scope overlaps, freshness, risk and state transitions. Required checks are not inferred from free-form prose.

Task fields scope, objective, non_goals, acceptance, required_checks, budget_id, revision and repository identity are required. task_class SPIKE remains Git-bound read-only research. SQL stores row_version for CAS and revision for semantic contract changes. Any denormalized task_json must equal indexed task fields within the same transaction.

Migration creates tasks, events, leases/claims/fences, evidence, checkpoints, provider_attempts, approvals, outbox, budgets, gate_decisions, schema_migrations. It intentionally does not pretend SQL indexes implement hierarchical path locking. Broker/scheduler must implement the transaction algorithms in sections 03/04/07.

Validation commands: python tools/validate_pack.py; python -m unittest discover -s tests -v. Read VALIDATION.md for actually executed results. No runtime test is marked passed solely because a schema parses.
