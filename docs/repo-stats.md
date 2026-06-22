# CRM Copilot — Статистика репозитория

> Сгенерировано: 2026-03-11

---

## Временная шкала

| Метрика | Значение |
|---------|---------:|
| Первый коммит | 28 февраля 2026 |
| Последний коммит | 11 марта 2026 |
| Активная разработка | **12 дней** |
| Автор | 1 (Сергей Тетерин) |
| Веток | 1 (main) |
| Всего коммитов | **32** |

### Активность по дням

| Дата | Коммитов |
|------|--------:|
| 2026-03-11 | 12 |
| 2026-03-10 | 5 |
| 2026-03-09 | 4 |
| 2026-03-08 | 3 |
| 2026-03-01 | 3 |
| 2026-03-07 | 2 |
| 2026-03-04 | 2 |
| 2026-02-28 | 1 |

---

## Объём кода

| Язык | Файлов | Строк |
|------|-------:|------:|
| Python | 59 | 9,782 |
| TypeScript / JS | 11 | 2,413 |
| CSS / HTML / JSON | — | 2,609 |
| **Итого** | **70+** | **~14,800** |

### Структура Python-кода (backend)

| Метрика | Значение |
|---------|---------:|
| Функций (def) | 256 |
| Классов | 40 |
| async def | 143 |
| API эндпоинтов (@app./@router.) | 7 |
| TODO / FIXME комментариев | 2 |

---

## Тесты

| Метрика | Значение |
|---------|---------:|
| Тест-файлов | 20 |
| Всего тестов | **116** (116 pass / 0 fail) |
| Время прогона | ~1 сек |
| Строк тестового кода | 3,639 |
| Соотношение тест/код | ~1 строка теста на 2.7 строки кода |

### Покрытие тестами (pytest-cov)

| Метрика | Значение |
|---------|---------:|
| Общее покрытие | **64%** |
| Измерено | 2026-03-11 |
| Порог (fail_under) | 0 (baseline; установить порог после ревью) |

Запустить: `uv run pytest backend/tests/ -q`

---

## Качество кода (Ruff)

Найдено **23 замечания**, автоматически исправляемых: **0** (32 было исправлено в FEAT-008):

| Код | Описание | Кол-во |
|-----|---------|-------:|
| E501 | Длинная строка (>100 символов) | 12 |
| N806 | Переменная не в lowercase | 6 |
| F841 | Неиспользуемая переменная | 3 |
| Прочее | — | 2 |

Запуск: `uv run ruff check backend/`

---

## Зависимости

| Слой | Зависимостей |
|------|------------:|
| Backend (prod) | 16 |
| Backend (dev/test, группа) | 6 |
| Backend (runtime, группа) | 11 |
| Extension | 4 |

Ключевые: FastAPI, Pydantic v2, gRPC, Redis, ChromaDB, sentence-transformers, Loguru, pytest

### Установка окружения

```bash
uv sync       # устанавливает все группы dev + backend автоматически
uv run pytest # 116 тестов, ~1 сек
```

---

## Горячие файлы (больше всего правок)

| Файл | Правок |
|------|-------:|
| `extension/src/shared/messages.ts` | 8 |
| `backend/main.py` | 8 |
| `extension/src/popup/popup.ts` | 7 |
| `extension/src/offscreen/offscreen.ts` | 7 |
| `extension/src/background/service-worker.ts` | 7 |
| `backend/pipeline/stt.py` | 7 |
| `extension/src/sidepanel/sidepanel.ts` | 6 |
| `backend/pipeline/orchestrator.py` | 6 |

---

## Что ещё можно собрать

| Метрика | Инструмент | Команда |
|---------|-----------|---------:|
| Покрытие тестами (%) | pytest-cov | `uv run pytest --cov=backend --cov-report=term-missing` |
| Цикломатическая сложность | radon | `uv run radon cc backend/ -s -a` |
| Мёртвый код | vulture | `uv run vulture backend/ --min-confidence 80` |
| Дублирование кода | pylint | `uv run pylint backend/ --disable=all --enable=duplicate-code` |
| Ошибки типов | mypy | `uv run mypy backend/ --ignore-missing-imports` |
| Bundle size extension | — | `du -sh extension/dist/` → **100K** |
| Время сборки extension | — | `npm run build` в extension/ |
| Размер Docker-образа | docker | `docker build . && docker images` |
| Latency API эндпоинтов | locust / k6 | нагрузочное тестирование |
| Secrets scan | gitleaks | `gitleaks detect --source .` |
