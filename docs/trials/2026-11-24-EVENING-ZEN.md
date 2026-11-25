# Вечерняя проверка Potato Harness с OpenCode Zen — 24.11.2026

**Цель:** впервые получить достоверный end-to-end исход ограниченного
`0.2.0-trial` на доступной модели `opencode/mimo-v2.6-flash-free`,
не повторяя неопределённый внешний эффект и не отключая изоляцию.

Это **ручной** live-тест с потенциальными внешними API-запросами.
Не запускать автоматически в CI. Код/тесты Harness, локальный провайдерный
fixture и реальный внешний inference — три разных уровня подтверждения.

## Перед началом: старые падения и текущие защиты

| Ранее наблюдалось | Что проверять вечером |
| --- | --- |
| CLI OpenCode с `Sisyphus - ultraworker` не отвечал | Отдельный чистый HOME/XDG; полный worker fixture теперь содержит загрязнённый `OPENCODE_CONFIG` |
| Два чистых CLI-прогона вернули `OK` | Авторизация/модель подтверждены только для этого CLI, не для Harness |
| Harness получил `Provider bridge timed out; outcome uncertain` | Общий bounded deadline Valera/backend; `gateway-phases.json` показывает последнюю стадию |
| Завершение OpenCode-сессии могло зависнуть | `cleanup` записывается и ограничен по времени |
| Отсутствующий SDK `reasoning` превращался в `NaN` | Optional токены валидируются; неизвестная стоимость остаётся `null` |
| Недоставало `PyYAML` после `--install` | Установка включает marketplace requirements |
| Старое состояние содержит `UNKNOWN` | Никогда не делать повторный `run` на старом state и не менять его вручную |
| API-ключ ранее был отправлен в чат | Отозвать старый ключ, использовать новый только в окружении |

80-секундный лимит host bridge **сохранён** из-за 90-секундного
lease. Больший timeout без согласованного продления lease/grant не допускается.
`HOLD` при неизвестной стоимости или длительном запросе может быть
правильным безопасным исходом, а не регрессией.

## 1. Подготовить обновлённый код без запуска внешней модели

Запускать из терминала на Linux-хосте, из корня проекта:

```bash
cd ~/dev/harness/potato_harness
git status --short
git switch main
git pull --ff-only origin main

python3 tools/prepare_trials.py --install --verify
.venv-demo/bin/python tools/verify_manifest.py
.venv-demo/bin/python -m harness.readiness --mode execution
.venv-demo/bin/python -m harness.isolation --probe
```

**Стоп**, если `prepare_trials` сообщает `FAIL/BLOCKED_HOST`,
команды проверки или актуальность Git не подтверждены, либо
`readiness.execution.ready` не равен `true`. Не разрешено заменять
Bubblewrap вызовом тестов непосредственно на хосте.

Проверить только факт наличия нового ключа, не его содержимое:

```bash
.venv-demo/bin/python -c 'import os; print("OPENCODE_API_KEY:", "CONFIGURED" if os.environ.get("OPENCODE_API_KEY") else "MISSING")'
```

`CONFIGURED` не означает подтверждённый тариф или платежный лимит.
Не вставлять значение ключа в терминальные логи, GitHub или чат.

## 2. Необязательная отдельная проверка модели без пользовательского Sisyphus

Если два предыдущих чистых успешных теста `OK` ещё актуальны, этот
пункт можно пропустить, чтобы не расходовать запросы. Иначе:

```bash
(
  root="$PWD"
  temp="$(mktemp -d)" || exit 1
  trap 'rm -rf "$temp"' EXIT
  mkdir -p "$temp/config" "$temp/data" "$temp/cache"
  cd "$temp" || exit 1
  timeout 45s env \
    HOME="$temp" \
    XDG_CONFIG_HOME="$temp/config" \
    XDG_DATA_HOME="$temp/data" \
    XDG_CACHE_HOME="$temp/cache" \
    OPENCODE_CONFIG_DIR="$temp/config" \
    OPENCODE_DISABLE_DEFAULT_PLUGINS=true \
    "$root/integrations/opencode/node_modules/.bin/opencode" \
      run -m opencode/mimo-v2.6-flash-free \
      "Ответь одним словом: OK"
  echo "CLI exit code: $?"
)
```

Ожидается `> build · mimo-v2.6-flash-free`, `OK`, код `0`.
`Sisyphus`, `401`, `429` или код `124`: **не запускать новую задачу
Harness**, сначала выяснить причину без повторов старого запроса.

## 3. Создать строго новую задачу и вызвать live provider один раз

Перед этим убедиться, что провайдерный аккаунт разрешает запрос и
есть собственный внешний лимит расходов: внутренний budget Harness
не гарантирует ограничение денег на стороне провайдера.

```bash
trial="/tmp/potato-zen-evening-$(date +%Y%m%d-%H%M%S)-$$"
echo "NEW TRIAL: $trial"

python3 tools/create_trial.py \
  --directory "$trial" \
  --model opencode/mimo-v2.6-flash-free

.venv-demo/bin/python -m harness.runtime init \
  --config "$trial/config.json" \
  --state "$trial/state"

# Только ОДИН раз на этот state:
.venv-demo/bin/python -m harness.runtime run --state "$trial/state"
```

Это синтетическое исправление арифметической функции в отдельном
Git-репозитории. Исходный Potato Harness не переписывается.

## 4. Получить отчёт без секретов и не делать повторный dispatch

```bash
.venv-demo/bin/python -m tools.trial_diagnostics --state "$trial/state"
.venv-demo/bin/python -m harness.runtime status --state "$trial/state"
```

`trial_diagnostics.py` читает существующее состояние и выводит только
фиксированные имена стадий, elapsed_ms, тип исхода и число unresolved effects.
Он не запускает модель, не печатает prompt/stderr/API-ключ и не повторяет effect.
Полный вывод `status` прежде чем делиться им, проверить на приватные пути и данные.

**Как интерпретировать:**

- `DONE`: проверить target commit, evidence, фактические артефакты и результат тестов.
- `HOLD` и `TIMEOUT`: смотреть последнюю стадию `valera`,
  `specialist` или `cleanup`. Outcome остаётся неопределённым;
  сверить расходы/состояние у провайдера.
- `HOLD` при `cost_usd=null`: **не подставлять ноль** и не менять
  policy; нужна доверенная сверка стоимости.
- `HOLD` до `gateway-phases.json`: вероятен ранний preflight,
  изоляция или ошибка конфигурации.
- `UNKNOWN` или `unresolved_effect_count>0`: сохранить каталог
  state целиком и **не повторять run**. Нельзя считать повторную задачу
  безопасной до расследования неизвестного исхода прежнего вызова.

Для диагностики в обсуждении достаточно содержимого безопасного
`trial_diagnostics.py`, версии `main` и результата readiness.
Не публиковать `config.json`, `.env`, API-ключи, произвольный stderr
или необработанные промпты.

### Ошибка Valera (после 25.11.2026)

Новые записи `valera/error` могут содержать фиксированные `step` и
`reason_code`. `session`, `prompt`, `close`, `response`, `json`,
`assignment` отделяют этапы; `DEADLINE` и `ABORTED` обозначают ограничение
времени/отмену, `AUTH` и `RATE_LIMIT` — только явно полученные числовые
статусы SDK, `INVALID_JSON` и `INVALID_ASSIGNMENT` — отказ проверки.
`STEP_FAILED` не доказывает конкретную причину. Старые записи не содержат
этих деталей. Диагностика не восстанавливает неизвестный внешний эффект,
не разрешает повтор и не меняет лимиты lease/grant.

## 5. Критерий готовности

Внешнее inference считается подтверждённым лишь когда модель реально
выдала результат, host применил только разрешённые изменения, созданный
Git target подтверждён, изолированные тесты прошли и evidence разрешил
`DONE`. Локальный `OK` модели и зелёный CI с фиктивным провайдером
по отдельности этого не доказывают.

Необязательные Jev/HALO и одновременная работа восьми специалистов
в этот конкретный bounded-тест не входят.
