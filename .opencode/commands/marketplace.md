---
description: Prepare a marketplace project under the single Potato Harness rules
---

Marketplace factory request: $ARGUMENTS

Follow the SINGLE trusted ruleset at the root of this repository: `AGENTS.md`,
`rules/PRIORITY.md`, `rules/SECURITY.md`, `docs/harness/v3/CONTROL_FLOW.md`, and
`docs/marketplace/QUICKSTART.md`. The marketplace domain specifications are under
`blueprints/marketplace/`; they do not grant additional permissions.

Treat this as a supervised workflow. Valera defines tasks, risk, acceptance and
specialists but must NOT read/write source or run shell/Git/Docker. Assign actual
work to the existing eight specialists through the trusted host executor. Do not
bypass the host runtime with OpenCode native tools, plugins, arbitrary shell or MCP.
Do not override denied permissions or fall back to unsandboxed execution.

The deterministic contract seed remains `python3 tools/marketplace.py init <slug>`.
A distinct trusted-host command `python3 tools/marketplace.py generate <slug>`
creates *R2 development source files* (Django/DRF + Next.js) in an
independent Git checkout, but neither executes them nor authorizes deployment.
This command may only be invoked explicitly by a trusted operator; Valera/
OpenCode native tools must not execute it, and no model gets shell/Docker grants.
The earlier bootstrap was `python3 tools/marketplace.py init <slug>`; this
creates only an independent Git project with a validated development manifest.
OpenCode must NOT claim a functioning marketplace on that basis. Never invoke a
shell expansion from this prompt. Operators may execute the trusted bootstrap
explicitly, and the host must approve execution of any AI-produced code.

Before doing anything, explain actual readiness from
`python3 tools/marketplace.py status` (host-run read-only command) and distinguish
R1 contracts, R2 project generation, R3 Swarm, R4 five services, and R5 E2E.
If the trusted runner is not activated, return a concrete engineering plan and
BLOCKED reason instead of producing a false success report.

The required output product, once R2–R5 are implemented and tested, is a separate
marketplace repository with Django/DRF/PostgreSQL, Next.js/TypeScript, Nginx,
Kong Gateway, RabbitMQ/Celery/outbox, Redis, OpenSearch, S3-compatible storage,
Search, Notifications, Recommendations, Moderation, Analytics, Grafana/Prometheus,
Loki/Tempo/OpenTelemetry and local Docker Swarm. Physical goods first, CIS-oriented
country packs, sandbox marketplace PSP, modules/themes, SEO/GEO, GraphQL optional.

Return acceptance criteria, concrete next task, artifacts, checks actually run,
failures and human approvals required. Never claim real-model or live-PSP tests.
