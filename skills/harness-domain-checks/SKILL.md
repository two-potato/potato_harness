---
name: harness-domain-checks
description: Use when selecting domain-specific checks for Backend, Frontend, Search, ML or DevOps work.
---

# harness-domain-checks

Read the task-bound injected policy first. This skill never grants permissions or overrides role prohibitions.

1. Start from task acceptance and policy/checks.json. Add checks for changed contracts; do not remove mandatory ones.
2. Backend: input/authorization, transaction, duplicate/retry semantics, migrations and API compatibility.
3. Frontend: loading/empty/error/success, accessibility/keyboard, responsive behavior, duplicate submission and server/client boundaries.
4. Search: exact identifiers, filters, zero results, relevance corpus, index freshness and unavailable-index behavior.
5. ML: impression/click/action identity, dedup/attribution, cold start, missing signals, privacy and baseline rollback; no unapproved training data.
6. DevOps: reproducible build, health/readiness, deployment/migration order, backup/restore and rollback where affected.
7. Pin test input/source and output artifacts; label checks not run. If a domain is untouched, avoid ceremonial extra tests.

Return: check IDs, commands/fixtures, applicability rationale, expected behavior and evidence requirements.
