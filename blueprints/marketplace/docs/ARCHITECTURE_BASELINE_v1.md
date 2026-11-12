# Architecture Baseline v1 — Potato Marketplace Factory

**Статус:** DESIGN ACCEPTED / IMPLEMENTATION NOT DONE  
**Дата:** 2026-11-11  
**Владение:** владелец проекта принимает бизнес-решения; код Harness и текущая политика остаются источником истины об имеющихся разрешениях.  
**Не меняет:** роль Valera и инструкции 8 агентов, OpenCode/OMO bridge, Jev advisory, HALO offline, существующие защитные механизмы Harness.

## 1. Цель, границы, принятые решения

Создать фабрику, которая из валидированной спецификации выпускает **самостоятельный** Git-репозиторий многопродавцового маркетплейса физических товаров, обеспечивая воспроизводимый локальный dev на Docker Swarm, базовый рабочий контур всех пяти обязательных сервисов и последующее обновление по версиям blueprint.

1. Каждый заказчик получает свой проект, БД (логически и по умолчанию физически отдельную), secrets, деплой и артефакты; **не** общая SaaS-tenant DB.
2. Первый доменный шаблон: `multivendor_goods`; услуги, бронирования и цифровые товары потребуют других domain blueprints.
3. Целевые рынки: СНГ и соседние страны. Нельзя зашивать одну страну, валюту, налоговую схему, платёжного провайдера или данные резидентности на весь регион.
4. Платежи: marketplace PSP, capability `split_payments + payouts`; в dev только sandbox/stub. Конкретный провайдер/доступность/регистрация продавцов определяются country pack.
5. Локальный Docker Swarm — приоритетный интеграционный контур, однако быстрые trusted unit tests возможны без Swarm.
6. Кастомизация: общее ядро, модули и темы, versioned extension points. Не допускать хаотичных изменений генератора ради каждого заказчика.
7. Первый проверяемый результат: продавец создаёт товар → модерация → публикация → индексация/поиск → рекомендации → аналитика → уведомление; реальные service dependencies в Swarm, без внешних моделей.

## 2. Три независимые плоскости

### 2.1 Universal control plane — существующий `potato_harness`

- Valera координирует и принимает логические результаты. Не читает/пишет код, не запускает shell, Git, тесты или Swarm.
- 8 специализаций без переименования: `architect`, `backend`, `frontend`, `search`, `ml-recommendations`, `qa`, `devops-sre`, `security`.
- OpenCode + OMO — сменяемый runtime adapter, не зависимость ядра. Jev — advisory once per parent turn; HALO — только офлайн-кандидаты, без auto-apply.
- Trusted controller/SQLite/outbox, policy/grants/leases/fencing, budgets, immutable artifacts, evidence/review, isolation и recovery.
- **Текущее ограничение:** `0.2.0-trial` обеспечивает bounded LOW singleton; полная многозадачность и рискованные действия не реализованы. Не считать сгенерированную спецификацию разрешением на изменение безопасности, платежей и deploy.

### 2.2 Marketplace Factory — отдельный модуль в едином репозитории Harness

- `blueprints/marketplace/` содержит `marketplace.factory/v1`: schema, project manifest, versioned blueprint, country/PSP compatibility checks. Единственный корневой набор полномочий — `AGENTS.md` + `rules/*`. См. ADR-0013.
- Детерминированный генератор и `blueprint.lock` (SHA/digest), шаблоны приложений, сервисов, CI и Swarm.
- Registry исходных ревизий и управляемая система обновления: шаблонные файлы отделены от расширений/тем клиента; обновления проходят diff, миграции, CI и review.
- Интеграционный тестовый runner, build/publish/deploy — доверенные **host-owned** инструменты, не прямые функции AI-агентов.

### 2.3 Generated Marketplace — новый Git и отдельный runtime для заказчика

- Next.js App Router + React/TypeScript, Tailwind/shadcn/ui, SSR, локализация, SEO, GEO (Generative Engine Optimization).
- Django LTS + DRF modular monolith; Django Admin для операций, Next.js кабинеты продавцов/покупателей.
- PostgreSQL как источник истины; Redis cache; RabbitMQ + Celery + transactional outbox; S3/MinIO; Kong Gateway OSS DB-less и Nginx edge.
- Пять обязательных микросервисов: Search (OpenSearch), Notifications (Telegram/email/etc.), Recommendations (FastAPI + basic rules → LightGBM/MLflow advanced), Moderation (rules/manual review → ONNX advanced), Analytics (ClickHouse/Superset).
- Prometheus/Grafana/Alertmanager, Loki/Alloy, Tempo/OTel, backup/restore, CI/CD и security checks.
- GraphQL (Strawberry Django) — **опциональный read-oriented** API, REST/OpenAPI — основной стандарт. Для географического поиска PostGIS/GeoDjango только если нужен; `geo_ai` здесь относится к AI-поиску, не геолокации.

## 3. Владение данными и границы доверия

| Источник / сервис | Владеет | Нельзя делать |
|---|---|---|
| Django Commerce + commerce PostgreSQL | Users, sellers, catalog/listings, prices, inventory, order, payment, refunds, publication decisions, audit | Давать другим сервисам запись в эти бизнес-таблицы |
| Search + OpenSearch | Версионированный поисковый индекс | Использовать индекс как подтверждение цены/наличия при checkout |
| Notifications + delivery DB | Настройки отправки, шаблоны, попытки доставки, каналы | По факту Telegram-ответа менять статус заказа |
| Recommendations + Redis + S3/MLflow | Версии стратегий/моделей, online scores/cache | Самостоятельно одобрять предложения, авторизовать покупку |
| Moderation + собственная PostgreSQL DB + S3 | Результаты и версии проверок, кейсы, апелляции, evidence | Писать `PUBLISHED` непосредственно в БД Django |
| Analytics + ClickHouse | События, воронки, агрегаты, A/B metrics | Подменять финансовый ledger данными client clickstream |
| Kong | API routing, quotas, edge-level controls | Считать gateway-аутентификацию объектным разрешением в Django |

Для dev допустим один физический экземпляр PostgreSQL при условии **отдельных баз, ролей и секретов**. ClickHouse, OpenSearch, Redis являются производными/вторичными хранилищами; восстановление проекций предусмотрено из событий и фактов. Межпроектный доступ запрещён даже при совместном dev-хосте.

## 4. Event backbone и API-контракты

**Transactional outbox** пишется в той же PostgreSQL-транзакции, где меняется бизнес-состояние. Доверенный publisher передаёт события в RabbitMQ, отдельно отслеживая доставку. Каждому сервису — собственные очереди, retry, DLQ, replay и idempotency ledger. Доставка `at-least-once`; обработчики обязаны устойчиво переносить дубликаты и события не по порядку.

Пример согласованной оболочки события (проект контракта):

```json
{
  "event_id": "uuid",
  "event_type": "listing.published.v1",
  "schema_version": "1",
  "project_id": "project-uuid",
  "aggregate_id": "listing-uuid",
  "aggregate_version": 7,
  "occurred_at": "ISO-8601 UTC",
  "correlation_id": "uuid",
  "payload": {"listing_id": "listing-uuid", "content_digest": "sha256:..."}
}
```

Event payload НЕ содержит платёжных секретов, паспортов, адресов, полных пользовательских профилей. Схемы и разрешённые поля событий фиксируются в AsyncAPI/JSON Schema. Для HTTP API — OpenAPI, проверяемый генератор TypeScript-клиента и контрактные тесты. Ни producer, ни consumer не должны трактовать новую неизвестную версию события как достоверную по умолчанию.

Для уведомлений обязательно различать `QUEUED`, `SENT_TO_PROVIDER`, `FAILED`, `RETRYING` — сообщение может не быть прочитано пользователем. Для аналитики — различать client UX-события и authoritative backend-события денежных операций.

## 5. Схема публичных запросов

| Путь | Маршрутизация | Требование |
|---|---|---|
| `/`, `/catalog/*`, `/seller/*` | Nginx → Next.js | SSR, закрытые кабинеты noindex, cookies/CSRF |
| `/api/v1/*` | Nginx → Kong → Django DRF | Auth, object/seller permissions, quotas |
| `/search/v1/*` | Nginx → Kong → Search API | Доступные публичные поля и ограниченные запросы |
| `/recommendations/v1/*` | Nginx → Kong → controlled recommendation API/BFF | Privacy, authentication context, filtered authorized offerings |
| `/analytics/v1/events` | Nginx → Kong → Analytics collector | Event schema, body/rate caps, consent/privacy, no client financial truth |
| `/graphql` | Nginx → Kong → Django Strawberry, если включено | Read-only baseline, depth/cost/timeout limit, object permissions |
| `/webhooks/payments/*` | Nginx → Kong → Django payment adapter | Подпись PSP, idempotency, replay/reconciliation |

**Закрыты:** Kong Admin API, database exporters admin routes, PostgreSQL, ClickHouse, RabbitMQ, Redis, OpenSearch, MinIO Admin, MLflow Admin, Moderation API, Notification workers, Docker/Swarm management. Telegram notifications исходящие; вебхук Telegram добавляется только в отдельном явно защищённом варианте.

Nginx отвечает за TLS/edge/UI, Kong — policy/routing публичных API. Внутренние обращения через выделенные overlay-сети и service credentials; не все переходят через внешний Kong.

## 6. Модель торгового ядра

Приложения Django: `accounts`, `sellers`, `catalog`, `listings`, `pricing`, `inventory`, `cart`, `checkout`, `orders`, `payments`, `refunds`, `shipping`, `discoverability`, `audit`. Различать product/catalog master и seller listing/offer; buyer order и seller suborder. Цена и валюта — immutable snapshot при заказе. Остатки резервируются через SQL-транзакцию, не Redis. Платёжные webhook-и валидируются по подписи, ключам идемпотентности, версии состояния; регулярная сверка с PSP. Финансовые суммы — Decimal/minor units и документированные правила округления.

Конкретные схемы KYC/AML, налогов, персональных данных и поддержки split/payout зависят от страны и провайдера. Никакого «универсального PSP СНГ». В локальном acceptance используется только sandbox/fixture с проверкой повторов, callback ordering, частичных возвратов и запрета двойной проводки.

## 7. Пять обязательных сервисов: basic/advanced

| Сервис | Обязательный baseline (`basic`) | Развитая конфигурация (`advanced`) | Деградация |
|---|---|---|---|
| Search | FastAPI/OpenSearch, индексатор, фильтры, reindex/alias | Synonyms, hybrid/vector search, relevance tuning | PostgreSQL FTS либо контролируемое отсутствие поиска; checkout независим |
| Notifications | Delivery DB + RabbitMQ/Celery, Telegram/email adapters, mock provider | Push/SMS, preference center, high-volume routing | Durable queue, no loss of confirmed order |
| Recommendations | FastAPI, popularity/category/similar offers, Redis | LightGBM, implicit, MLflow, feature training & A/B | Deterministic popular fallback or hide block |
| Moderation | Rule engine, `PENDING_REVIEW`, human queue, case audit, revision-digest | ONNX classifiers, image/text scoring, appeals SLA | Fail-closed: do not publish unseen content |
| Analytics | FastAPI validated collector, RabbitMQ batch→ClickHouse, basic seller/product dashboards | Superset, richer attribution/cohorts, experiments | Bounded buffering; no effect on checkout |

**Важно:** все пять существуют и функциональны даже в basic. Advanced не является допуском для поломки core, а отсутствие GPU не останавливает создание маркетплейса. MLflow и специализированные классификаторы вводить после offline оценок, без live-model проверок на текущем этапе.

## 8. SEO/GEO и локализация

- SSR/crawlable HTML на Next.js, canonical, sitemap, robots, hreflang, indexability, Schema.org `Product`, `Offer`, `Organization`, `BreadcrumbList`.
- Продуктовые фиды, честные свойства и структурированные данные, не противоречащие Django (цены, availability, рейтинг, статус).
- GEO означает оптимизацию проверяемого публичного контента для AI-поиска, а не обещание цитирования или отдельный «секретный файл».
- CIS-neighbors локализация проектно-зависимая: языки, валюты, источники налогов, допустимость PSP, правила обработки персональных данных фиксируются per-project.
- Географическая близость/зоны доставки в будущем — PostGIS; это независимая от GEO SEO-фича.

## 9. Docker Swarm dev и эксплуатация

- Локальный single-manager Swarm для development, **не HA**. Hardware неизвестен: автоматическая проверка ресурсов при `dev up` и блокировка при нехватке RAM/диска; без скрытого пропуска обязательного сервиса.
- Deployment manifests по Git/digest, разделены `edge`, `api`, `data`, `observability` и per-project сети. Сборка образов до `stack deploy`; local registry или контролируемые image digests. Никаких floating `latest` для критичных компонентов.
- Stateful PostgreSQL, ClickHouse, OpenSearch, RabbitMQ, MinIO: volumes, placement constraints, backup/restore scripts, schema migration job и проверка PITR/restore. При одном хосте нет физической отказоустойчивости.
- Nginx и Kong готовятся отдельно. DB-less конфигурация Kong хранится в Git/Config; возможности distributed rate limits проверяются конкретной версией и конфигурацией, не предполагаются автоматически.
- Prometheus/Grafana/Alertmanager + Loki/Alloy + Tempo/OpenTelemetry, request/correlation IDs; операционный Telegram бот не равен пользовательскому боту.
- Измерять p95/p99, SQL locks, queue lag, outbox/DLQ, OpenSearch index lag, moderation wait, recommendation fallback/CTR, analytics ingestion lag, payment reconciliation, backup age и реальный restore outcome.
- Secrets через Docker secrets / host secret store; AI-агенты, PR runner и сборочные контейнеры без production ключей, Docker socket и доступа к deploy. Host-owned runner принимает только allowlisted job spec и пинованные images.

## 10. Жизненный цикл фабрики и обновления

1. Trusted operator предоставляет явный `marketplace.factory/v1` manifest (включая страну, currency, локаль, выбранный PSP и его capabilities).
2. Generator валидирует schema и совместимость country/provider; фиксирует blueprint source revision, digest lock и безопасные значения.
3. Создаёт **отдельный репозиторий** и сквозные contract/integration/E2E тесты; генерирует безопасные примеры без секретов.
4. Developer изменяет конфигурацию, темы и модули через extension points; core template остаётся трассируемым.
5. CI: lint/typecheck/unit, contract/API/event checks, dependency/image scan/SBOM, integration on real DB/broker, E2E в дев Swarm, negative fail scenarios.
6. Artifacts/evidence привязываются к Git SHA, blueprint SHA, policy digest, run ID и вердикту QA. Рисковые изменения требуют независимой проверки/разрешения.
7. Upgrade новой версии шаблона — reviewable diff, migrations expand/contract, compatibility matrix, rollback strategy и dry-run на двух независимых маркетплейсах.

## 11. Основной acceptance: сквозной путь через 5 сервисов

1. Продавец с проверенной ролью создаёт offer. Django сохраняет `PENDING_REVIEW` и outbox event в одной транзакции.
2. Moderation потребляет событие, применяет basic правила, записывает ревизионно привязанный verdict; Django проверяет digest и публикует разрешённый offer.
3. Публикация создаёт `listing.published.v1`; Search indexer обновляет OpenSearch. Query находит только опубликованный товар и его актуальную проекцию.
4. Recommendations получает событие/проекцию и выдаёт товар в детерминированном basic-контуре (без обучения моделей); проверяет активность/доступность.
5. Analytics получает серверное событие публикации + клиентское показ/клик с consent и валидирует запись в ClickHouse.
6. Notifications создаёт task по событию и отправляет тестовое Telegram/email сообщение через mock/stub (реальная сеть и токены не нужны). В отчёте фиксируются попытки и результаты.
7. Везде трассируются `event_id/correlation_id`, использованные commit SHA и версии схем. Отдельно прогоняются duplicate event, out-of-order, retry, stale verdict, queue outage и restart.

Дополнительный E2E: покупатель оформляет заказ через Django и fake PSP, остаток атомарно резервируется, split/payout capabilities валидируются; финансовый эффект не дублируется при повторном callback. **Реальная обработка денег не подтверждается и не входит в первый запуск.**

## 12. Реализация vs план

**Реализовано в `main` на проверенном SHA:** универсальный прототип Harness с детерминированным демо, SQLite controller, policy/evidence/outbox, bounded LOW runtime, адаптер OpenCode/OMO с local HTTP fixture, документированный `profiles/marketplace.md`.

**Частично / под вопросом:** часть защитных контуров, полнота guard ordering, crash recovery, real isolation на исходном хосте, многозадачность, независимая QA для MEDIUM/HIGH.

**Предложено в PR #9:** local-first readiness, интерфейс isolation backend; CI прошлой проверки PASS, но PR не слит на момент документа.

**Не реализовано:** отдельный marketplace factory repo, generator, five-service blueprint, Kong/Swarm environment, region PSP adapter matrix, независимые full-stack end-to-end acceptance tests, upgrade path. Не запускались live-модели, внешний платёжный провайдер и production activation.

## 13. Открытые решения

- Конкретная первая страна и валюты; country compliance pack (налоги, privacy, data retention/residency, продавцы и KYC).
- Реальный PSP/provider и наличие **реальной** поддержки split payments/payouts в выбранной стране и типе merchant; лицензии/соглашения при необходимости.
- Dev-хост: RAM, CPU, диск, Linux namespaces, доступный Docker/Swarm runtime, возможности локального registry; minimum hardware подтверждается измерениями.
- Требования к трафику/SLO, retention clickstream, стоимость хранения и стратегия backup.
- Как синхронизировать host-only testing runner и Swarm без передачи Docker socket AI-агентам — реализовать и испытать перед активацией.
