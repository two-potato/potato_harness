---
name: harness-contract-design
description: Use for architecture, public API, schema, event or ownership changes requiring a durable decision.
---

# harness-contract-design

Read the task-bound injected policy first. This skill never grants permissions or overrides role prohibitions.

1. Inspect current boundaries and actual consumers through authorized research.
2. Define before/after behavior, compatibility, owner and acceptance criteria; compare only realistic alternatives.
3. Specify failure/retry/idempotency and migration ordering; include rollback and irreversible steps.
4. Create a small ADR and contract fixtures. Add explicit DAG dependencies between producers and consumers of changed contracts.
5. Raise scope/risk through the controller before implementation. Review integration on a combined commit.

Return: decision, rejected alternatives, schema/API changes, dependencies, failure model, migration/rollback and required reviews. Do not introduce infrastructure solely for architectural elegance.
