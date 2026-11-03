# 08 — Harness Evals and HALO

Distinguish static package checks, deterministic runtime tests, mocked integration, live sandbox and production eligibility. The package's Python tests validate contracts and SQL structure only. H/E/M runtime scenarios are NOT_RUN until code and adapters exist.

policy/releases.json determines applicable tests. Core v3.0 requires controller/CAS, context, broker, leases, evidence, approval, preflight, minimal recovery/outbox and hard budgets. v3.1 adds live completion/risk tuning; v3.2 extended replay/handoff/observability; v3.3 HALO. Disabled features have explicit NOT_APPLICABLE and are never counted as PASS.

Required core negatives: invalid state jump, concurrent row update, missing acceptance, stale/untrusted evidence, forged approval, risk downgrade, overlapping leases, stale fencing, unauthorized Valera tool, context injection/overflow, unknown external effect, duplicate preflight, budget overrun and partial cancellation.

Completion tests after v3.1: failed base gate prevents call; unavailable provider does not bypass checks; concrete gap has bounded re-review; duplicate key no resend; new revision invalidates cached result.

HALO is offline proposal generation only. Separate immutable train/eval/holdout IDs and digests; optimizer cannot access holdout examples, evaluator code or credentials. Independent evaluator runs holdout and releases aggregate results. Limit reuse per holdout version to 10 proposals, then rotate/quarantine; record all attempts to prevent cherry-picking.

Use schemas/halo-proposal.schema.json with trace digest, policy baseline, diff digest, evaluator/split provenance, before/after metrics, regressions, rollback and human review. Reject invariant weakening, auto-merge, stale baseline, test tampering and leakage. Optimization proposals cannot alter immutable role prompts without a separate explicit user decision and versioned source update.

Compare same repository SHA, role hashes, model IDs, task corpus, budgets and evaluator; randomize order. At least 3 runs per stochastic task is smoke-level evidence, not proof of significance. Report sample size, failure rate and uncertainty. Zero observed violations is a release condition, not a mathematical safety guarantee.

Canonical scenario registry: evals/cases.json defines all H01–H22, M01–M10 and C01–C10. All runtime cases remain NOT_RUN. S0 tests cover structural subsets only.
