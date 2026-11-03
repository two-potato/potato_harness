# Project skill routing

Skills here belong to the harness project, not the user's personal ChatGPT installation. Their supported loading path depends on the target runtime; adapters/README.md requires discovery tests first. For Valera, runtime injects selected skill content, never grants read tools.

| Role | Skills |
| --- | --- |
| Valera | harness-delegate |
| Architect | harness-research, harness-contract-design, harness-verify |
| Backend | harness-research, harness-implement, harness-domain-checks |
| Frontend | harness-research, harness-implement, harness-domain-checks |
| Search | harness-research, harness-implement, harness-domain-checks |
| ML recommendations | harness-research, harness-implement, harness-domain-checks |
| QA | harness-verify, harness-domain-checks |
| DevOps SRE | harness-implement, harness-domain-checks, harness-recover, harness-migrate |
| Security | harness-security-review, harness-verify |
| Optional Explore | harness-research only, read-only |
| Offline optimizer | harness-halo-propose; no live execution privileges |

Load only the selected skill body, plus relevant policy/rules. Do not prepend all skills to every request. An agent unavailable in the runtime cannot be summoned by naming a skill.
