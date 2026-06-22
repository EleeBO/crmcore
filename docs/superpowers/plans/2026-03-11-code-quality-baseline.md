# Code Quality Baseline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подключить покрытие тестами, устранить 32 авто-фиксируемых ruff-нарушения и заглушить ложные N802/N806 в gRPC-сгенерированных файлах.

**Architecture:** Все изменения — конфигурационные. Только `pyproject.toml` + запуск `ruff --fix`. Исходный код приложения не трогается.

**Tech Stack:** uv, ruff, pytest-cov, pytest-asyncio (уже установлены)

**Spec:** `docs/superpowers/specs/2026-03-11-code-quality-baseline-design.md`

---

## Pre-flight: что уже есть и что нужно менять

Перед началом — что уже корректно настроено в `pyproject.toml`:

| Настройка | Состояние | Действие |
|-----------|-----------|---------|
| `asyncio_mode = "auto"` | ✅ уже есть | не трогаем |
| `[tool.mypy]` (strict) | ✅ уже есть, но `warn_unused_ignores = true` | обновить: `false`, добавить `ignore_missing_imports = true` |
| `pytest-cov`, `ruff`, `mypy` в dev-deps | ✅ | не устанавливаем |

Что сломано:
- `[tool.coverage.run]` имеет `source = ["src"]` — исходники в `backend/`, не `src/`
- `[tool.coverage.report]` имеет `fail_under = 80` — сработает после фикса source и может заблокировать pytest если реальное покрытие < 80%
- `testpaths = ["tests"]` — неправильный путь, должен быть `backend/tests`
- `addopts` не содержит `--cov` → coverage не запускается
- `[tool.ruff.lint.per-file-ignores]` — нет записей для gRPC-стабов → 10 ложных N802/N806

> **Baseline** (текущее состояние перед правками): `113 passed, 8 warnings`.
> 3 из 8 — `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` из внутренностей `AsyncMock`. Они появляются даже с `asyncio_mode = "auto"` и **не устраняются конфигурационными изменениями**. 5 остальных — `DeprecationWarning` от сторонней библиотеки sounddevice/swig. Оба типа принимаем как данность.

---

## Chunk 1: pyproject.toml + ruff auto-fix

### Task 1: Исправить pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1.1: Добавить per-file-ignores для gRPC-стабов**

Открыть `pyproject.toml`. Найти секцию:

```toml
[tool.ruff.lint.per-file-ignores]
"tests/**/*" = ["S101", "ARG"]  # Allow assert and unused args in tests
```

Добавить две строки для gRPC-файлов (они генерируются protoc, переименовывать нельзя):

```toml
[tool.ruff.lint.per-file-ignores]
"tests/**/*" = ["S101", "ARG"]
"backend/pipeline/salutespeech/*_pb2*.py" = ["N802", "N806", "E501"]
"backend/pipeline/yandexstt/*_pb2*.py" = ["N802", "N806", "E501"]
```

- [ ] **Step 1.2: Проверить что N802/N806 исчезли для gRPC**

```bash
uv run ruff check backend/pipeline/salutespeech/ --select N802,N806
uv run ruff check backend/pipeline/yandexstt/ --select N802,N806
```

Ожидаемый результат: `All checks passed!` для обеих директорий.

- [ ] **Step 1.3: Исправить testpaths и addopts в pytest**

Найти секцию `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = [
    "-v",
    "--strict-markers",
    "-ra",
]
```

Заменить на (добавить `backend/tests` в testpaths и `--cov` в addopts):

```toml
[tool.pytest.ini_options]
testpaths = ["backend/tests"]
asyncio_mode = "auto"
addopts = [
    "-v",
    "--strict-markers",
    "-ra",
    "--cov=backend",
    "--cov-report=term-missing",
]
```

- [ ] **Step 1.4: Исправить source в coverage и убрать преждевременный порог**

Найти секцию `[tool.coverage.run]` и `[tool.coverage.report]`:

```toml
[tool.coverage.run]
source = ["src"]
branch = true
omit = ["tests/*", "*/__pycache__/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
fail_under = 80
```

Исправить:
- `source = ["src"]` → `source = ["backend"]`
- `fail_under = 80` → `fail_under = 0` (порог установим позже, когда измерим реальный baseline)

```toml
[tool.coverage.run]
source = ["backend"]
branch = true
omit = ["tests/*", "*/__pycache__/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
fail_under = 0
```

- [ ] **Step 1.5: Обновить конфиг mypy**

Найти секцию `[tool.mypy]`:

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true
plugins = ["pydantic.mypy"]
```

Добавить `ignore_missing_imports = true` и изменить `warn_unused_ignores` на `false` (иначе strict-режим будет жаловаться на наши `# type: ignore` в местах, где mypy неполон):

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_ignores = false
disallow_untyped_defs = true
ignore_missing_imports = true
plugins = ["pydantic.mypy"]
```

- [ ] **Step 1.6: Убедиться что coverage запускается**

```bash
uv run pytest backend/tests/ -q --no-header 2>&1 | tail -10
```

Ожидаемый результат: в конце вывода присутствует таблица вида:
```
Name                                       Stmts   Miss Branch BrPart  Cover
------------------------------------------------------------------------------
backend/config.py                             XX     XX     XX     XX    XX%
...
TOTAL                                        XXX    XXX    XXX    XXX    XX%
```
Если строки `TOTAL` нет — coverage не подхватился; проверить `addopts` из шага 1.3.

- [ ] **Step 1.7: Закоммитить изменения конфига**

```bash
git add pyproject.toml
git commit -m "chore: fix coverage source/threshold, testpaths, --cov addopts, gRPC per-file-ignores, mypy ignore_missing_imports"
```

---

### Task 2: Ruff auto-fix

**Files:**
- Modify: файлы в `backend/` где ruff найдёт авто-фиксируемые нарушения

- [ ] **Step 2.1: Dry run — просмотреть что изменится**

```bash
uv run ruff check backend/ --fix --diff 2>&1 | head -80
```

Просмотреть diff. Ожидаем изменения типа:
- Удаление неиспользуемых импортов (`import X` → строка удалена) — F401
- Сортировка блоков импортов (isort) — I001
- Удаление `(object)` в `class Foo(object):` → `class Foo:` — UP004
- Удаление `# -*- coding: utf-8 -*-` строк — UP009
- Исправление `f"строка без {переменных}"` → `"строка без переменных"` — F541

Если diff выглядит неожиданно (трогает логику, не только стиль) — остановиться и разобраться.

- [ ] **Step 2.2: Применить auto-fix**

```bash
uv run ruff check backend/ --fix
```

Ожидаемый результат: команда завершается, в stdout перечислены исправленные файлы.

- [ ] **Step 2.3: Проверить статистику оставшихся нарушений**

```bash
uv run ruff check backend/ --statistics
```

Ожидаемый результат: в выводе **нет строк с `[*]`** (маркер авто-фиксируемых). Допустимые остатки — только non-auto-fixable:

| Код | Допустимо | Описание |
|-----|-----------|---------|
| E501 | ≤19 | Длинные строки — ручная правка |
| N806 | ≤6 | Не-lowercase переменные вне gRPC |
| E402 | ≤3 | Импорт не вверху файла |
| F841 | ≤3 | Неиспользуемые переменные |
| SIM117 | ≤1 | Multiple with statements |

Суммарно: ≤32 нарушений (было 74, авто-фиксируемых 32 + N802/N806 в gRPC исчезнут после per-file-ignores из Task 1).

- [ ] **Step 2.4: Убедиться что тесты не сломались**

```bash
uv run pytest backend/tests/ -q --no-header 2>&1 | grep -E "passed|failed|error" | tail -3
```

Ожидаемый результат: `113 passed` (или более, если тесты добавились).

- [ ] **Step 2.5: Закоммитить ruff-исправления**

```bash
git add -u
git commit -m "chore: apply ruff auto-fix (F401 unused imports, I001 sort, UP004 object inheritance, UP009 encoding, F541 f-string)"
```

---

### Task 3: Финальная верификация

- [ ] **Step 3.1: Полный прогон тестов с coverage**

```bash
uv run pytest backend/tests/ --tb=short -q 2>&1
```

Ожидаемый результат:
- Строка `XXX passed, 8 warnings` (предупреждения от AsyncMock и SwigPy — ожидаемы)
- Таблица coverage в stdout
- Строка `TOTAL ... XX%` присутствует — запомнить этот %

- [ ] **Step 3.2: Проверить mypy**

```bash
uv run mypy backend/ 2>&1 | tail -5
```

Ожидаемый результат: вывод содержит `Found N errors in M files` (ошибки типов — нормально, это baseline) **и не содержит** строк:
- `error: Error importing plugin "pydantic.mypy"`
- `No module named 'pydantic'`

Если одна из этих строк есть — mypy запускается вне uv-окружения. Убедиться что команда `uv run mypy`, а не голый `mypy`.

- [ ] **Step 3.3: Обновить repo-stats с реальным покрытием**

Открыть `docs/repo-stats.md`. Найти секцию `### Покрытие тестами (pytest-cov)`:

```markdown
> `pytest-cov` не установлен в активном окружении. Установить:
> ```bash
> uv add --dev pytest-cov
> uv run pytest backend/tests/ --cov=backend --cov-report=term-missing
> ```
```

Заменить на реальные цифры из Step 3.1:

```markdown
| Метрика | Значение |
|---------|---------|
| Общее покрытие | XX% |
| Измерено | 2026-03-11 |
| Порог (fail_under) | установить после ревью (текущий baseline: XX%) |

Запустить: `uv run pytest backend/tests/ -q`
```

- [ ] **Step 3.4: Финальный коммит**

```bash
git add docs/repo-stats.md
git commit -m "docs: update repo-stats with actual test coverage baseline"
```

---

## Acceptance Criteria

| Проверка | Команда | Ожидание |
|---------|---------|---------|
| gRPC N802/N806 подавлены | `uv run ruff check backend/pipeline/salutespeech/` | `All checks passed!` |
| Нет авто-фиксируемых | `uv run ruff check backend/ --statistics` | Нет строк с `[*]` |
| Тесты зелёные | `uv run pytest backend/tests/ -q` | `XXX passed` (≥113) |
| Coverage работает | (тот же запуск) | Строка `TOTAL ... XX%` в stdout |
| mypy запускается | `uv run mypy backend/` | Нет `Error importing plugin` или `No module named 'pydantic'` |
| Warnings не выросли | (тот же запуск) | ≤8 warnings (baseline) |

---

## Что НЕ делаем (out of scope)

- E501 (длинные строки) — ручная правка, отдельная задача
- E402, F841, SIM117, N806 вне gRPC — ручная правка
- Установка radon, vulture — отдельная фича
- CI/CD — не требуется
- Исправление AsyncMock warnings в тестах — требует ручного рефакторинга
