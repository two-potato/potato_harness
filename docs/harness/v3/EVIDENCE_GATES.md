# 05 — Evidence Graph and Deterministic Gates

Use schemas/evidence-record.schema.json and evidence-graph.schema.json. SHA-1 object IDs are 40 lowercase hex; SHA-256 object IDs 64 lowercase hex, with explicit hash_algorithm. Artifact digests use sha256: plus 64 lowercase hex. A syntactically valid digest is not proof.

Trusted collectors fetch evidence from configured CI/review/artifact providers. Attestation references resolve to immutable collector records containing issuer, repository identity, run/job ID, task revision, target commit, artifact digest, checks and policy version. Workers cannot write collector storage or trust roots. Verify actual provider identity/result and fetched artifact bytes. Human approval is a separate authenticated record.

## Gate algorithm

1. Validate schemas, unique acceptance/evidence IDs and referential integrity.
2. Compute effective risk and checks using policy/checks.json; risk can increase but not be silently downgraded.
3. Resolve each evidence attestation through trusted collector. Reject issuer mismatch, substituted repo/run, revoked records, invalid digest, unknown checks and missing artifacts.
4. Match task_id, revision, repository, exact target commit and policy version. Do not accept stale commit evidence. No equivalent-artifact exception in v3.0 core.
5. Cover every acceptance requirement and every required check ID. Policy establishes check applicability before execution. Required SKIPPED/UNKNOWN/ERROR/missing is INCOMPLETE, FAIL is FAIL. Multiple contradictory records require reconciliation; a later PASS does not erase an unresolved failure.
6. Validate independent reviewer session/actor and conflict-of-interest rule for required reviews; author cannot supply reviewer attestation.
7. Validate narrow human approvals for high-impact actions and rollback plans where required. Approval does not replace tests.
8. Reject unresolved blockers. Persist gate decision with exact input digest, task revision, row_version and policy.
9. At acceptance/completion recheck freshness and CAS; changes invalidate decision.

Statuses: PASS, FAIL, INCOMPLETE, BLOCKED, NEEDS_HUMAN_APPROVAL. Runtime grants must be valid for a new effect, but historical evidence is not invalid just because its already-finished worker grant expired. Cleanup revocation must not invalidate an otherwise valid DONE record.

LOW/SPIKE may use attested contract/research review artifacts on a pinned source commit without CI when policy makes CI inapplicable. A task without a repository needs a separate versioned artifact workflow; it is outside this Git-bound core, never a fake SHA.
