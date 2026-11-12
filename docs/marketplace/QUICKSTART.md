# Единый репозиторий: Potato Harness + Marketplace Blueprint

**Архитектурное решение:** один клонируемый Git-репозиторий `potato_harness`, один
корневой `AGENTS.md` и доверенные `rules/*`. Доменные контракты R1 живут в
`blueprints/marketplace/`, но НЕ имеют права переопределять общие разрешения Harness.

## Желаемый конечный интерфейс

```sh
git clone https://github.com/two-potato/potato_harness.git
cd potato_harness
opencode
# в OpenCode: /marketplace demo-market-kz
```

Это **целевой UX**, пока не полностью реализованный. Простая команда в TUI не
обходит отказ изоляции, бюджет, grants, leases и независимую приёмку. OpenCode и
OMO являются подключаемым исполнителем, а не владельцами правил безопасности.

## Что можно выполнить сегодня без AI и без сети

Установить зависимости в локальное виртуальное окружение:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r blueprints/marketplace/requirements-dev.txt
.venv/bin/python tools/marketplace.py status
.venv/bin/python tools/marketplace.py validate blueprints/marketplace/examples/marketplace.factory.example.yaml
.venv/bin/python tools/marketplace.py init demo-market-kz
```

Последняя команда создаёт **отдельный Git-репозиторий** рядом с `potato_harness`,
с файлом `marketplace.factory.yaml` и документом `NEXT_STEPS.md`.
Существующие каталоги не перезаписываются. Из `init` не вызываются API моделей,
Docker, внешние PSP или код генерируемого проекта.

**Ограничение:** это контрактный seed, не готовый marketplace и не даже Django
MVP. R2–R5 необходимы для получения работающего продукта. R1 валидирует
компоненты, но не реализует их. Дев-фикстуры имеют фиктивные SHA/платежи,
которые запрещены для production.

## Размещение компонентов

- `harness/`, `rules/`, `agents/`, `policy/` — общие правила и механизмы.
- `integrations/opencode/` — проверенный pinned OpenCode/OMO gateway.
- `blueprints/marketplace/` — контракты и ADR только маркетплейса.
- `.opencode/commands/marketplace.md` — единая точка входа для TUI, без
  встраивания опасных команд в prompt.
- `tools/marketplace.py` — доверенная детерминированная проверка и bootstrap.
- `../<slug>/` — отдельный проект, который фабрика должна создать и развить.

На компьютере без проверенного Bubblewrap нельзя автоматически исполнять
AI-изменённый код. Проверка разработки не даёт права на execution.

## Последующие инженерные этапы

1. R2: настоящий Django/Next.js generator с версионированными шаблонами.
2. R3: Nginx + Kong + Swarm и интеграционная инфраструктура.
3. R4: пять обязательных микросервисов, basic режимы без GPU.
4. R5: сквозной подтверждённый тест продавец → модерация → поиск → рекомендации →
   аналитика → уведомление, все события и повторные доставки.
5. Отдельная приёмка защищённого runner и исполняющего OpenCode/OMO контура.
