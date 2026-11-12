# Architecture decisions: confirmed vs open

**Источник подтверждённых решений:** ответы владельца на 8 интерактивных вопросов 11 ноября 2026 года. Остальное — ранее согласованные решения или инженерные рекомендации. Отсутствующие ответы не считаются данными по умолчанию.

## 8 подтверждённых ответов

| № | Ответ | Архитектурное последствие |
|---|---|---|
| 1 | Независимый проект на заказчика | Свой Git, БД, secrets, Swarm stack, state, backup; без общей tenant DB |
| 2 | Сначала физические товары | `multivendor_goods` как первый domain blueprint |
| 3 | СНГ и соседние рынки | Country pack, locale/currency/PSP/privacy зависят от проекта |
| 4 | Marketplace PSP split payments + payouts | Контракт PSP с capability discovery; fake PSP в dev |
| 5 | Dev-ресурсы неизвестны | Обязательный preflight ресурсов, профили нагрузки и честный HOLD |
| 6 | Сначала локальный Docker Swarm | Single-host developer stack, не production HA |
| 7 | Единое ядро + модули/темы | Versioned extension points, upgrade procedure |
| 8 | Первый результат — путь через 5 сервисов | Вертикальный интеграционный acceptance, а не только «контейнеры запустились» |

## Уже согласовано ранее

Django + DRF/PostgreSQL, Next.js/TypeScript, Nginx edge + **отдельный** Kong Gateway OSS, OpenSearch Search, RabbitMQ/Celery Notifications, FastAPI/LightGBM Recommendations, FastAPI/rules/ONNX Moderation, FastAPI/ClickHouse Analytics; Prometheus/Grafana/Alertmanager/Loki/Alloy/Tempo; S3/MinIO; SEO + GEO Generative Engine Optimization; GraphQL опционален; OpenCode/OMO через независимый Harness; пять сервисов обязательны в basic; live models пока не запускать.

## Открытые бизнес-решения (решаются перед реальным запуском в соответствующей стране)

- **COUNTRY-01:** точная страна первой реализации, валюты, локали, фискальные/налоговые правила, residency/retention.
- **PSP-01:** первый реальный PSP, подтверждённые API-возможности split/payouts для выбранной юрисдикции, merchant onboarding/KYC, refunds, chargebacks и договорные ограничения.
- **LEGAL-01:** договорная роль платформы и продавцов, правила фискализации, персональных данных, рекламных материалов, локальных особенностей модерации.
- **OPS-01:** параметры локального dev-хоста (CPU/RAM/storage/OS/допуск namespaces), требования по времени запуска и расходу памяти.
- **SLO-01:** целевые SLO и нагрузочная модель, retention аналитики и бюджеты инфраструктуры.

**До ответа:** использовать sandbox PSP, synthetic data, демонстрационный country pack с явным `non_production` и блокировать любой live deployment, требующий неподтверждённых регуляторных условий.
