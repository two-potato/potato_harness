# Potato Harness

**Управляемая AI-разработка: постановка, ограниченное исполнение, проверяемые результаты и восстановление.**

[![Validation](https://github.com/two-potato/potato_harness/actions/workflows/validate.yml/badge.svg)](https://github.com/two-potato/potato_harness/actions/workflows/validate.yml)

Версия runtime: **0.2.0-trial**. Формат контрактов: **3.0.1**.
Кандидат для single-host испытаний 6 ноября 2026 года. Он выполняет одну ограниченную
LOW/BOUNDED задачу по явно заданным файлам и тестам. Полная production-активация
и произвольная автономная команда разработчиков ещё не сертифицированы.

## Подготовить машину

Linux, Python 3.12+, Git, Node/npm и разрешённые namespaces для Bubblewrap.

```bash
git clone https://github.com/two-potato/potato_harness.git
cd potato_harness
python3 tools/prepare_trials.py --install --verify
```

Команда устанавливает закреплённые зависимости в проект и пишет
`.runtime/trial-readiness.json`. Глобальную конфигурацию OpenCode не меняет.
`BLOCKED_HOST` требует исправить среду. Добавление ключа не устраняет запрет namespaces.

На машине разработки запуск изоляции блокируется NETLINK_ROUTE EPERM. Соответствующие
live-тесты пропущены с явной причиной. Запуска произвольного кода на хосте вместо
sandbox нет. На Windows нужен подходящий Linux/WSL-хост, native Windows не проверен.

[Пошаговый план испытаний](docs/trials/2026-11-06-RUNBOOK.md) содержит команды,
ожидаемые результаты и критерии остановки.

## Выполнить реальную задачу

Настройте `OPENCODE_API_KEY` в окружении через секретное хранилище. Не вводите ключ
в чат и не коммитьте `.env`. Модель должна быть доступна вашему аккаунту.

```bash
python3 tools/create_trial.py --directory /tmp/potato-trial --model opencode/gpt-6.1-sol
.venv-demo/bin/python -m harness.runtime init --config /tmp/potato-trial/config.json --state /tmp/potato-trial/state
.venv-demo/bin/python -m harness.runtime run --state /tmp/potato-trial/state
.venv-demo/bin/python -m harness.runtime status --state /tmp/potato-trial/state
```

Проверьте лимиты и область задачи в config.json перед запуском. Runtime сохраняет
состояние, доказательства, артефакты и настоящий Git target commit. Сбой не означает
разрешение повторить внешний вызов. Для разбора: `harness.runtime recover --state …`.

## Связь компонентов

| Компонент | Работа в кандидате |
| --- | --- |
| Valera | Отдельный модельный вызов: получает описание и scope без исходников, назначает одобренного исполнителя |
| OMO | Реальный закреплённый плагин, объединённые config/context hooks; второй координатор и обходные инструменты отключены |
| OpenCode | Реальный сервер и SDK, отдельные сессии координатора/исполнителя, модельные tools запрещены |
| Jev | Durable preflight перед назначением и completion после base gates; ключи только на хосте |
| Контроллер | Состояния/CAS, ревизии, атомарные события, запрет DONE/CANCELLED при неопределённых эффектах/арендах |
| Контекст | Роль, правила и выбранный навык внедряются хостом; данные ограничены и редактируются |
| Бюджет/outbox | Сохранённые резервы, реальный usage, запрет применения правок при перерасходе; UNKNOWN не переотправляется |
| Scheduler/leases | Проверка DAG и готовности зависимостей, атомарные аренды конфликтующих ресурсов |
| Broker/publisher | Привязка к сессии/ревизии/политике, проверки путей, приём артефакта с актуальной арендой |
| Изоляция | Bubblewrap с фактической пробой; недоступность запрещает запуск |
| Проверки | Доверенная команда внутри sandbox, точный Git target и независимая от текста модели проверка evidence |
| HALO | Трассы runtime, отдельные train/eval/holdout, оценка и PROPOSED без автоприменения |

Persistent runner использует одного backend-исполнителя и детерминированный host
review для LOW. Определения девяти ролей загружены в OpenCode; многозадачная параллельная
работа всей команды и MEDIUM/HIGH приёмка требуют отдельных интеграционных испытаний.

## Jev и HALO

В config.json укажите `jev_provider: "opencode"`, `jev_model: "jev-1.13-free"`;
`completion_jev: true` включает итоговую рекомендацию. Бесплатность не предполагается,
доступ проверяется у провайдера. Для TypeSafe доступны TYPESAFE_API_KEY и его model ID.
Без ключа фиксируется UNAVAILABLE. Замечание/недоступность включённого completion
не даёт завершить задачу.

```bash
.venv-demo/bin/python -m harness.runtime halo --state /tmp/potato-trial/state
.venv-demo/bin/python -m harness.runtime halo --state /tmp/potato-trial/state --train train.json --eval eval.json --holdout holdout.json
```

Первый вариант экспортирует трассу и HOLD при недостаточных данных. Второй реально
оценивает явные непересекающиеся наборы. Одна трасса не выдаётся за три выборки.
HALO не изменяет роли/права и ничего автоматически не вливает.

## Что проверено без внешнего ключа

- Python unit/integration тесты, включая настоящий SQLite и конкуренцию процессов.
- Actual OpenCode 1.19.5 + OMO 5.1.60 + Bun 1.4.4: загрузка плагина, запросы через
  локальный HTTP-провайдер, отдельный шлюз Valera → исполнитель, ограничение output.
- Зафиксированные npm зависимости и штатное отключение OMO telemetry во всех entrypoints.
- Контракты, хеши исходных ролей и manifest пакета.

Локальный HTTP-провайдер — проверка протокола, а не live-инференс Jev/модели.
Бюджет до запроса использует UTF-8 byte ceiling, не точный токенизатор. Контекст SDK,
стоимость Jev и общий provider spend требуют сверки и account-level budget.
Перерасход фактического worker usage блокирует применение правок. Изоляция оценщика
HALO в отдельном защищённом процессе и полная production eligibility не заявляются.
OpenCode 2.x отдельно не проверен: закреплён реально исполняемый 1.x API.

## Портфольное демо без модели

```bash
python3 tools/run_demo.py
```

Четыре сценария: исправление принято, тесты не прошли, устаревшие доказательства,
нет права на запись. Git/тесты/SQLite настоящие; proposer по умолчанию детерминирован.
[Видеоразбор](docs/demo/walkthrough.mp4) · [Кейс](docs/PORTFOLIO.md).

## Документы

[Trial runbook](docs/trials/2026-11-06-RUNBOOK.md) · [Runtime](docs/runtime/RUNTIME.md) ·
[OMO/OpenCode](integrations/opencode/README.md) · [Jev](docs/runtime/JEV.md) ·
[HALO](docs/runtime/HALO.md) · [Бюджет/outbox/контекст](docs/runtime/DURABLE_CORE.md) ·
[Контроллер](docs/runtime/STATE_CONTROLLER.md) · [Брокер](docs/runtime/BROKER.md) ·
[Аренда](docs/runtime/LEASES.md) · [Публикация](docs/runtime/PUBLISHER.md) ·
[Изоляция](docs/runtime/ISOLATION.md) · [План](IMPLEMENTATION_PLAN.md).

Индивидуальный AI-assisted проект. Код проекта — [MIT](LICENSE), внешние зависимости
сохраняют свои лицензии; OMO — SUL-1.0 и не перепубликуется как MIT-код.
