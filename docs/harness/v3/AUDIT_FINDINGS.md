# 13 — Audit closure and remaining runtime gates

03.11.2026, specification revision 3.0.1. This replaces the prior audit's current-status table; original snapshots remain historical v2 sources.

| Finding | Specification change | Runtime closure |
| --- | --- | --- |
| A01 inconsistent evidence fixture | canonical record/graph fixture generated from schemas | structural validation only |
| A02 weak hashes / untrusted source | algorithm-aware commit + sha256 digest + attestation reference; trusted collector contract | OPEN: real issuer/artifact verification |
| A03 absent outbox | SQL outbox and UNKNOWN reconciliation contract | OPEN: crash-before/after dispatch tests |
| A04 lease overlap/fencing | normalized claims, atomic transaction algorithm, private workspaces + trusted publisher | OPEN: process-level concurrency/bypass tests |
| A05 controls only on paper | explicit NOT_IMPLEMENTED status; staged plan | OPEN: controller/broker/sandbox/gate |
| A06 Jev hooks unverified | provider reservation/fallback contract, adapter activation checklist | OPEN: installed SDK integration |
| A07 missing audit states | COMPLETION_AUDITING/REREVIEW, guarded resume and revision semantics | OPEN: runtime transitions |
| A08 HALO proposal/evaluator gaps | proposal schema, immutable splits, independent evaluator, holdout reuse cap | OPEN: evaluator isolation |
| A09 approval trust gap | action_digest/revision/issuer/nonce/attestation/expiry contract | OPEN: trusted issuer and replay tests |
| B01 overstated readiness | export/static/runtime statuses separated | no runtime completion claimed |
| B02 universal QA vs LOW policy | one checks.json matrix and guard references | test all task/risk combinations |
| B03 version/tests mismatch | core safety prerequisites moved into core, release profiles explicit | run only applicable profile tests |
| B04 missing schemas | all documented contracts included in package | cross-record runtime checks still required |
| B05 context overflow | mandatory content counts toward total, BLOCKED on overflow | tokenizer/real-model limits test |
| B06 malformed paths/repo coupling | canonical relative paths, no hard-coded repo | target integration review |
| B07 original Security Rules missing | rules/SECURITY.md supplied; role mapping/load order | runtime loading test |
| B08 task revision/CAS ambiguity | semantic revision and row_version separated | stale-controller tests |
| B09 integration commit omitted | combined target commit and fresh integration evidence required | merge/rebase stale evidence tests |
| B10 false exactly-once expectation | at-most-one local reservation, UNKNOWN reconciliation | provider fault injection |

New negative cases: C01 unknown transition; C02 forged approval fields; C03 stale task revision; C04 duplicate acceptance IDs; C05 missing scope; C06 unsupported path glob; C07 context mandatory overflow; C08 changed integration SHA; C09 role/skill permissions conflict; C10 unsupported runtime plugin. Static fixtures cover only structural subsets; do not mark semantic runtime cases PASS from JSON validation.
