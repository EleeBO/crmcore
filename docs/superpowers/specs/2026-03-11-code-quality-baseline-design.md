# FEAT-008: Code Quality Baseline

**Date:** 2026-03-11
**Status:** APPROVED
**Author:** Сергей Тетерин

---

## Problem

Анализ репозитория выявил несколько проблем с инфраструктурой качества кода:

1. `pytest-cov` не подключён к pytest-конфигу → покрытие не измеряется при `uv run pytest`
2. Три теста кидают `RuntimeWarning: coroutine was never awaited` → потенциальные async-баги
3. 71 ruff-замечание, из которых 32 авто-фиксируемых (F401, I001, UP004, UP009, F541)
4. 10 нарушений N802 в gRPC-сгенерированных файлах — ruff не знает, что это генерируемый код
5. `mypy` не запускается из-за конфликта с pydantic-плагином

---

## Scope

**Входит (только автоматизируемое, без ручной правки строк кода):**
- Запуск `ruff check --fix` — устранение 32 авто-фиксируемых нарушений
- Настройка `per-file-ignores` в `pyproject.toml` для gRPC-стабов (N802, N806)
- Активация `pytest-cov` через `[tool.pytest.ini_options]` в `pyproject.toml`
- Добавление `asyncio_mode = "auto"` в pytest-конфиг — устраняет 3 async-предупреждения
- Базовая конфигурация `[tool.mypy]` в `pyproject.toml`

**Не входит:**
- Ручная правка E501 (длинные строки), E402, F841, SIM117, N806 — требуют ревью кода
- Установка radon, vulture, gitleaks — отдельная фича
- CI/CD интеграция — не требуется

---

## Architecture

Все изменения — конфигурационные. Исходный код приложения не изменяется.

```
pyproject.toml
├── [tool.ruff.lint]
│   └── per-file-ignores: gRPC stubs → ignore N802, N806
├── [tool.pytest.ini_options]
│   ├── addopts: --cov=backend --cov-report=term-missing
│   └── asyncio_mode: auto
└── [tool.mypy]
    ├── python_version: "3.11"
    └── ignore_missing_imports: true
```

---

## Components

### 1. Ruff auto-fix

**Команда:** `uv run ruff check backend/ --fix`

Нарушения, которые будут устранены автоматически:

| Код | Описание | Кол-во |
|-----|---------|--------|
| F401 | Неиспользуемые импорты | 16 |
| I001 | Неотсортированные импорты | 7 |
| UP004 | Лишнее `object` в наследовании | 6 |
| UP009 | UTF-8 encoding declaration | 2 |
| F541 | f-string без плейсхолдеров | 1 |

**per-file-ignores** для gRPC-стабов (генерируемые файлы, не трогаем):
```toml
[tool.ruff.lint.per-file-ignores]
"backend/pipeline/salutespeech/*_pb2*.py" = ["N802", "N806", "E501"]
"backend/pipeline/yandexstt/*_pb2*.py" = ["N802", "N806", "E501"]
```

### 2. pytest-cov активация

**Было:** `pytest-cov` в dev-deps, но не запускается автоматически
**Будет:** запускается при каждом `uv run pytest`

```toml
[tool.pytest.ini_options]
addopts = "--cov=backend --cov-report=term-missing"
```

HTML-репорт (`--cov-report=html:htmlcov`) опционально — замедляет прогон.

### 3. pytest-asyncio: asyncio_mode = "auto"

**Диагностика:** Три теста в `test_edge_cases.py` кидают `RuntimeWarning`:
- `TestEdgeCases::test_crosstalk_prioritises_client`
- `TestEdgeCases::test_empty_scenario_no_crash`
- `TestLatency::test_latency_full_pipeline_under_2s`

Все три уже помечены `@pytest.mark.asyncio` и используют `AsyncMock`. Предупреждение исходит из `AsyncMockMixin._execute_mock_call` — это известная несовместимость между pytest-asyncio без `asyncio_mode=auto` и `AsyncMock` из `unittest.mock`. Это не баги в тест-логике, а инфраструктурная настройка.

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### 4. mypy базовый конфиг

Mypy падает при `mypy backend/` из-за того, что pydantic-плагин не находится в PATH при прямом вызове. Правильный вызов через `uv run mypy`. Добавляем конфиг:

```toml
[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
warn_unused_ignores = false
```

Плагин `pydantic.mypy` оставляем в конфиге — он работает корректно через `uv run mypy`.

---

## Data Flow

```
Developer runs: uv run pytest
                      │
                      ▼
         pytest collects 110 tests
                      │
                      ▼
         asyncio_mode=auto → async tests wrapped correctly
                      │
                      ▼
         Tests execute → 110 passed, 0 warnings
                      │
                      ▼
         pytest-cov collects coverage data
                      │
                      ▼
         Coverage report: term-missing output
```

---

## Error Handling

- Если после `ruff --fix` остаются авто-фиксируемые ошибки → ошибка в дизайне, нужно разобраться
- Если `asyncio_mode=auto` сломает тесты → откатить; конкретные тесты (`test_crosstalk_prioritises_client`, `test_empty_scenario_no_crash`, `test_latency_full_pipeline_under_2s`) уже проверены — они имеют `@pytest.mark.asyncio` и не содержат логических багов с await
- Если mypy выдаёт слишком много ошибок → не блокируем пайплайн, только информируем

---

## Testing

**Критерии готовности:**

| Проверка | Команда | Ожидаемый результат |
|---------|---------|-------------------|
| Ruff авто-фиксы применены | `uv run ruff check backend/ --fix && uv run ruff check backend/ --statistics` | 0 авто-фиксируемых; остаётся ≤39 non-auto (E501, E402, F841, SIM117, N806) |
| gRPC ignored | `uv run ruff check backend/pipeline/salutespeech/` | 0 N802 ошибок |
| Тесты зелёные | `uv run pytest --tb=short -q` | 110 passed, 0 warnings |
| Coverage видна | `uv run pytest -q` | Coverage report в stdout с итоговым % |
| mypy запускается | `uv run mypy backend/` | Не падает с plugin/import error |

---

## Implementation Order

1. Обновить `pyproject.toml` за один проход: per-file-ignores для gRPC + `[tool.pytest.ini_options]` с cov и asyncio_mode + `[tool.mypy]` конфиг
2. Запустить `uv run ruff check backend/ --fix`
3. Прогнать `uv run pytest -q` — проверить: 110 passed, 0 warnings, coverage output
4. Прогнать `uv run mypy backend/` — проверить: нет crash при старте
