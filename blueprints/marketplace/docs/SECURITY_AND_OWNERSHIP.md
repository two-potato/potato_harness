# Boundary and data ownership — version 1

| Component | Authority / storage | API access | Failure behavior |
| --- | --- | --- | --- |
| Django Commerce | PostgreSQL (users, sellers, listings, pricing, orders, payments, stock); emits outbox | Public via Kong, object permission and RBAC | Orders fail closed on database failures |
| Search | OpenSearch projection; indexer consumes listing changes | Bounded read via Kong | PostgreSQL FTS or controlled unavailable, never authority for stock/price |
| Notifications | Delivery database and Celery/RabbitMQ, separate Telegram ops/user bots | Internal only | Retain pending delivery, rate-limit/retry, no order rollback |
| Recommendations | Versioned strategies, Redis & OpenSearch projections | Bounded read via application/API | Hide block or deterministic popular fallback |
| Moderation | Versioned policy/verdict/audit DB; content digest | Internal only, signed/revision-bound verdict | PENDING_REVIEW, not silently published |
| Analytics | Consent-aware event ingestion, ClickHouse; financial events from backend only | Rate-limited public collector with schema and CORS + private reporting | Bounded durable buffering, never block commerce |
| Kong | API policy/rate limiting | Through Nginx only; Admin API internal | Gateway outage alerts |
| Nginx | Edge TLS, public Next.js rendering | Public | No direct stateful/admin routes |

- No service writes Django commerce tables directly. Moderation decisions are
  commands verified by Django, not raw database updates.
- Each service authenticates its caller; per-project and per-seller authorization
  is applied *inside* the owning business service, not only at gateway.
- No agents or untrusted code get Docker socket, Kong Admin, secrets or database
  management credentials. Host-only runner with allowlisted pinned artifacts.
- Outbox and RabbitMQ deliveries are at-least-once. Consumers deduplicate on
  `(project_id,event_id)` and reject older aggregate versions; DLQ and manual
  replay are audited.
- No production split/payouts until explicit country law, PSP capability and
  compliance review; fake PSP only in R1.
