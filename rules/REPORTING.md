# Structured results

Every handoff includes task_id, revision, objective, scope, non_goals, acceptance IDs, required checks, dependencies, budget, evidence_refs and proposed next action.

Use DONE only after controller final decision; otherwise PARTIAL or BLOCKED in the user report. Distinguish NOT_RUN, FAIL, SKIPPED, ERROR and PASS. A skipped check is never a passing check. NOT_APPLICABLE must be decided by trusted policy before verification and recorded with reason.

Summaries include paths, commit, issuer/run IDs and evidence digests; do not copy secrets, private prompts or hidden reasoning. Unknown cost is null/unknown, never zero. Report a missing integration as missing, not mocked success. A schema PASS means structure only.
