# Implementation Plan v1 — Potato Marketplace Factory

**Статус:** ROADMAP / NOT IMPLEMENTED (для нового blueprint).  
**Ветки и Git:** этот документ не даёт разрешения на автоматический merge, deploy или обход review.  
**Модельные тесты:** `NOT_IN_SCOPE` до отдельного запроса.  
**Метод:** TDD/contract-first → детерминированные fixtures → real dependencies integration → negative failure tests → evidence by commit → независимое QA → управляемое обновление.

## 0. Правила выполнения

- Не переписывать существующие Harness controller/broker/leases/outbox/publisher без воспроизведённой потребности.
- Сохранить Valera control-only, роли 8 специалистов и независимость ядра от Django/Swarm/OMO.
- Каждый PR с областью изменения, тестовым доказательством, SHA, риском и rollback. Отрицательные тесты обязательны для authorization, payment, retries, publication.
- Нет host fallback при недоступной изоляции; test runner и Docker socket принадлежат только доверенному хосту, не модели.
- Каждый шаг `DONE` только после перечисленных проверок. Если Swarm недоступен по аппаратным причинам — `BLOCKED_ENV`, не подмена mock сервисом.

## R0 — Стабилизировать существующее основание Harness [P0]

**Зависимости:** нет. **Владелец:** `backend` + `security` + `qa`, review `architect`.

1. Провести review PR #9 local-first readiness, слить только после security review и CI.
2. Исправить guarded переходы: `EXECUTING` только после валидных ревизионных lease/grant, проверенных зависимостей и budget reservation, под контролем доверенного state/guard.
3. Стресс/аварийные тесты SQLite/outbox: разрыв до/после provider dispatch, `UNKNOWN`, stale lease, recovery без повторного эффекта, согласование `run.json`/DB/Git/evidence.
4. Спроектировать и испытать host-controlled integration test runner с изолированной сетью тестовых PostgreSQL/RabbitMQ/Swarm, без Docker socket у агентов. Небезопасный путь запрещён.

**Gate R0:** отрицательные тесты доказывают отказ до выдачи полномочий и отсутствие повтора неизвестных side effects; `run` по-прежнему fail-closed на неподдерживаемом хосте.

## R1 — Контракты фабрики и базовые ADR [P0]

**Зависимости:** независимая подготовка от R0; публикация execution gates после R0. **Владелец:** `architect`, `backend`, `security`, `qa`.

1. В одном репозитории создать изолированный модуль `blueprints/marketplace/`, не внедряя зависимости Django/Swarm в core Harness. Генерируемые проекты получают отдельные Git.
2. JSON Schema `marketplace.factory/v1`: независимость проектов, тип товаров, country pack, PSP capabilities, 5 обязательных сервисов, Kong/Nginx, storage, security, resource profile.
3. Кросс-сервисный event envelope AsyncAPI + JSON Schema, publish/subscription contracts, idempotency, review, replay.
4. OpenAPI по публичным и внутренним API, codegen TypeScript, security matrix, нет общего `superuser` service account.
5. Тесты негативных конфигураций: неизвестная страна/валюта, реальный PSP без capabilities, отключение обязательного сервиса, плавающие образы, публикация внутренних портов.

**Gate R1:** schema-valid project manifest и намеренно невалидные примеры корректно отвергаются; каждый сервис владеет явным контрактом и данным.

## R2 — Генератор и минимальный торговый каркас [P0]

**Зависимости:** R1. **Владелец:** `architect`, `backend`, `frontend`, `qa`.

1. Детерминированная генерация отдельного Git-репозитория; `blueprint.lock` с pinned digest; template extension points, themes/modules.
2. Django/DRF + PostgreSQL + PostgreSQL migrations, seller RBAC/object permissions, catalog/product/listing, status `DRAFT/PENDING_REVIEW/PUBLISHED/REJECTED`, immutable content revision.
3. Next.js storefront и seller portal, TS client из OpenAPI, SSR, базовые локализованные маршруты, дизайн-система.
4. Оформить composable payment adapter с offline fake PSP для split/payout contract. Реальный PSP не активировать до COUNTRY/PSP решения.

**Gate R2:** два запуска генератора с одинаковым manifest/blueprint дают эквивалентные исходники и lock; seller не видит чужой listing; миграции и API contracts зелёные.

## R3 — Local dev Swarm, Edge и observability [P0]

**Зависимости:** R2, R0 для хостового интеграционного тестирования. **Владелец:** `devops-sre`, `security`, `qa`.

1. Preflight оборудования и Docker/Swarm, hard fail если обязательный basic сервис не помещается, отсутствие подмены теста.
2. Build→scan/SBOM→registry/pin digest→`docker stack deploy`; управляемые job migrations, trust-bound deployment.
3. Nginx TLS edge → Next.js и Kong DB-less → Django / разрешённые сервисы; Kong Admin на приватной сети, API-level rate/body/time limits.
4. Per-project overlay сети, database roles/secrets, volumes и placement constraints.
5. Prometheus/Grafana/Alertmanager + Loki/Alloy + Tempo/OTel; минимум dashboard здоровья, outbox, queue, API.
6. Runbooks, backup/restore для PostgreSQL, ClickHouse и критичных данных, проверка отказа и восстановления.

**Gate R3:** стек запускается и восстанавливается после перезапуска, публичные маршруты работают, внутренние базы/админки не открываются снаружи, trace и alarms видны; ресурсные лимиты измерены.

## R4 — Пять микросервисов в basic [P0]

**Зависимости:** R1–R3. **Владельцы:** `search`, `ml-recommendations`, `backend`, `frontend`, `qa`, `security`.

1. **Search:** FastAPI + OpenSearch + indexer; published-only, query/filter/alias/reindex; повтор/устаревший event не переопределяет свежие данные.
2. **Notifications:** Celery/RabbitMQ, delivery store, provider mock Telegram/email, idempotency/retry/DLQ; отдельный Alertmanager Telegram ops канал.
3. **Recommendations:** FastAPI, popularity/category similarity, Redis, filtered offers; версия стратегии, deterministic offline dataset, fallback.
4. **Moderation:** FastAPI, versioned policy rules, own DB, manual queue; signed/revision-bound verdict, Django publication gate; `PENDING_REVIEW` при outage.
5. **Analytics:** FastAPI collector, RabbitMQ consumer, ClickHouse ingestion, seller dashboards; consent/PII, financial source backend only, replay.

**Gate R4:** все 5 сервисов функциональны на `basic`, покрыты unit/contract/integration tests; существует деградация для каждого; нет публичных опасных admin API.

## R5 — Основной вертикальный e2e [P0, первый milestone успеха]

**Зависимости:** R4. **Владельцы:** `qa` как независимый проверяющий, `backend`, `frontend`, `search`, `ml-recommendations`, `security`.

1. Пользователь-продавец через Next.js создаёт offer; Django commit+outbox.
2. Moderation выносит rule-based verdict; Django проверяет content digest и переводит в PUBLISHED.
3. Search индексирует опубликованный offer; поиск возвращает только разрешённые данные.
4. Recommendations возвращает эту карточку либо фиксированную детерминированную стратегию; нет скрытых/отклонённых офферов.
5. Analytics агрегирует server event и consented impression в ClickHouse; результаты запросов сверяются.
6. Notifications пишет delivery attempt и через Telegram/email stub подтверждает передачу provider.
7. Отрицательные сценарии: duplicate/out-of-order events, outdated moderation verdict, RabbitMQ outage/replay, OpenSearch down, ClickHouse down, notifier timeout, stale offer, unauthorized seller.

**Gate R5:** один user-facing сценарий сквозь пять сервисов подтверждён по кореллирующим event ids и точному Git SHA; все явные отказы проходят ожидаемым образом. Без реальных моделей и реальных денег.

## R6 — Товарные операции, SEO/GEO и эксплуатационная проверка [P1]

**Зависимости:** R5. **Владельцы:** `backend`, `frontend`, `qa`, `security`, `devops-sre`.

1. Inventory reservations (concurrency), cart, checkout, orders/seller suborders, refunds, fake PSP split/payout capabilities, duplicate webhooks, reconciliation.
2. SSR pages, canonical/sitemap/hreflang/JSON-LD Product/Offer; human-verifiable price/availability, crawl/indexability; Merchant Feeds.
3. Проверки локалей/валют согласно стране, consent/retention и audit trail; редактирование/удаление PII в analytics/index/model datasets по утверждённой политике.
4. Restore drill, нагрузочный baseline, disabled external services; release evidence + approvals.

**Gate R6:** реальные DB/queue и тестовый PSP проводят заказ/возврат с идемпотентностью и корректной финансовой сверкой; нет утечки PII или secret в логах/событиях.

## R7 — Factory repeatability и безопасные обновления [P1]

**Зависимости:** R5–R6. **Владельцы:** `architect`, `devops-sre`, `qa`, `security`.

1. Генерировать два независимых проекта (разные страны/локали на sandbox policy) и проверить project isolation.
2. Изменить тему и включить дополнительный модуль во втором проекте.
3. Обновить оба с blueprint `v1.0 -> v1.1`, получить reviewable diff и schema migrations без потери расширений.
4. Реверс/rollback, реплей событий и restore drill; independent QA и digest-based evidence.

**Gate R7:** два проекта работают и обновляются без доступа к чужим БД/секретам; обновление воспроизводимо, изменения клиентского кода не уничтожены.

## R8 — Advanced capabilities [P2, только после R5–R7]

**Зависимости:** R5–R7 и измерения. **Владельцы:** `ml-recommendations`, `search`, `backend`, `qa`.

- LightGBM/implicit ranking, MLflow registry, offline datasets/evaluation, inference shadow/rollback, A/B тесты; отдельные ресурсы/квоты.
- ONNX Runtime text/image moderation, quality/false positive/appeals metrics; human oversight.
- OpenSearch hybrid ranking, тематические и географические расширения (PostGIS), GraphQL read-only при потребности.
- Production HA и live PSP подключать только после country/provider/security/legal review и production readiness.

**Gate R8:** measured improvement + reproducible model versions, security/performance proof. Никаких заявлений о live inference без отдельного тестового протокола.

## Критический путь

`R0 security` ∥ `R1 contracts` → `R2 skeleton` → `R3 Swarm` → `R4 five services` → **`R5 five-service e2e`** → `R6 commerce/SEO` → `R7 two-project upgrade` → `R8 advanced`.

**Блокеры:** отсутствие измеренного dev hardware не блокирует документацию и контракты; оно блокирует утверждение успешного Swarm E2E. Без установленного country/PSP невозможно активировать реальные выплаты, но тестовый fake PSP покрывает разработку.
