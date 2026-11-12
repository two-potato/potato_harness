# R1 API and event contracts

OpenAPI 3.1 documents reside under `contracts/openapi/`. Schemas define
*target* interfaces, not deployed endpoints. Implementers must keep auth,
object permissions, request limits and idempotency in the owning service.

| Service | Illustrative endpoint | Auth | Notes |
| --- | --- | --- | --- |
| Search | `GET /v1/search` | optional bearer + app rate limit | Published only, price/stock remain Django truth |
| Recommendations | `GET /v1/recommendations` | authenticated scoped user | Return offer IDs, not canonical price |
| Moderation | `POST /internal/v1/verdicts` | internal service identity | Revision/content digest; Django verifies before publish |
| Notifications | `POST /internal/v1/deliveries` | internal service identity | Idempotency key, no direct public API |
| Analytics | `POST /v1/events` | public consent/session token | No financial truth from browser; strict schema and bounds |

Event channels described by `contracts/asyncapi/marketplace-events.v1.yaml`.
Envelopes validated by `schemas/event-envelope.v1.schema.json`. Each event
carries unique ID, schema version, aggregate/version, project ID, occurrence
and correlation. Add a new version for incompatible changes. Never accept
arbitrary raw PII keys in event payloads. Cross-service contract tests and
negative duplicate/stale event tests become executable during R4/R5.
