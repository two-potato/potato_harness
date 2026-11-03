# 12 — Test playbook

## Levels

S0: schema meta-validation, valid and negative fixtures, SQL migration, source hashes, links/path completeness, cross-policy consistency. Commands in README. This is executable now with validation dependencies.
S1: deterministic runtime tests H01–H12 plus new cases listed in AUDIT_FINDINGS. Requires actual controller/broker/gate implementations; not supplied as mocked successes.
S2: scripted model and provider mocks; assert order, deny paths, retry/reservation, persistence and recovery. No external network effects.
S3: live OpenCode in an isolated container, synthetic repository, pinned model/SDK, no production credentials; validate loaded instruction/skill/tool discovery and both Jev phases when enabled.
S4: holdout-isolated HALO evaluation, proposal only. S5: soak/concurrency/failure injection with bounded cost.

## Benchmark

Use 12 fixed synthetic tasks: frontend 2, backend 2, DevOps 2, search/ranking 2, security 2, architecture 2; add refusal probes separately. Same source SHA, role hashes, task criteria and budgets. 3–5 runs per variant; randomize ordering and use clean workspaces.

Compare baseline and each enabled component; experimental preflight ablation is allowed only in isolated benchmark profile. It does not change operational preflight requirement. Runtime features may not be toggled in production to improve scores.

Measure verified_success_rate, false_done, unauthorized effects, stale evidence acceptance, queue wait, p50/p95, tokens/cost including failures and QA, repair cycles, duplicate attempt reservations and trace storage growth. Separate approval wait from execution time. Record unknown usage honestly. Thresholds: critical applicable tests all pass, zero observed safety violations; any slowdown/cost increase justified by measured benefit. Do not claim statistical improvement from three runs.

## Traces and oracles

Every test has input, trusted expected result, assertion, owner, profile, run ID and evidence artifact. Synthetic attestation fixtures stay inside test adapters; never trusted in live mode. Test the harness itself: denied tools, forged records, process crashes, changed commits and overlapping writes; application test success alone is insufficient.

Do not assume any target application already has a particular CI suite. Inventory the actual repo. A worktree is not a sandbox. Use installed CLI/SDK documentation to derive smoke commands; do not copy unverified API names from an old document.
