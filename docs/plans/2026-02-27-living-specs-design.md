# Living Specs + Unified Workflow — Design Document

Created: 2026-02-27
Status: APPROVED

## Summary

**Goal:** Интеграция living specifications, FEAT-NNN нумерации, мульти-агентного ревью планов, генерации тест-сценариев и переноса лучших компонентов из проекта "claude code" в CodeRush2.

**Architecture:** Подход A — раздельные файлы spec и plan. Specs в `specs/`, планы в `docs/plans/`, привязка через FEAT-ID. Новые команды `/specify`, `/review-plan`, `/generate-tests`. Перенос Rules Supervisor, Context Monitor, `/remember`, расширенного `/verify` и дополнительных rules.

**Tech Stack:** Claude Code agents (Task tool, fan-out/fan-in), Gemini API (Rules Supervisor), Playwright MCP / Chrome MCP (E2E тесты), Cipher (persistent memory).

---

## 1. Структура файлов и нумерация

### Новые директории

```
specs/                              # Living specifications
├── registry.md                     # Центральный реестр FEAT-NNN → статус
├── FEAT-001-auth-system.md         # Living spec
├── FEAT-002-payments.md
└── archive/                        # Закрытые спецификации

docs/plans/                         # Implementation plans (одноразовые)
├── FEAT-001-auth-system.md         # План v1
├── FEAT-001-auth-system-v2.md      # План v2 (второй раунд изменений)
└── FEAT-002-payments.md

.claude/reviews/                    # Результаты ревью (генерируются /review-plan)
├── REVIEW_ARCHITECT.md
├── REVIEW_BACKEND.md
├── REVIEW_FRONTEND.md
└── REVIEW_CONSOLIDATED.md

tests/scenarios/                    # Тест-сценарии (генерируются /generate-tests)
├── FEAT-001-scenarios.md           # Given/When/Then
├── FEAT-001-matrix.md              # Классификация и приоритеты
└── FEAT-001-coverage.md            # Отчёт о покрытии
```

### registry.md — центральный реестр

```markdown
# Feature Registry

| ID | Name | Status | Spec | Plans | Created |
|----|------|--------|------|-------|---------|
| FEAT-001 | Auth System | ACTIVE | [spec](FEAT-001-auth-system.md) | [v1](../docs/plans/FEAT-001-auth-system.md) | 2026-02-27 |
| FEAT-002 | Payments | DRAFT | [spec](FEAT-002-payments.md) | — | 2026-02-28 |

## Statuses
- DRAFT — спецификация в разработке
- ACTIVE — реализовано и поддерживается
- MODIFIED — есть незавершённые изменения
- DEPRECATED — планируется к удалению
- ARCHIVED — перемещено в archive/

## Next ID: FEAT-003
```

### Living Spec формат (specs/FEAT-NNN-name.md)

```markdown
# FEAT-NNN: Feature Name

Status: DRAFT | ACTIVE | MODIFIED | DEPRECATED
Created: YYYY-MM-DD
Last Modified: YYYY-MM-DD

## Overview
Краткое описание фичи (2-3 предложения).

## Current State
Описание текущей реализации — обновляется после каждого /implement.

### Components
- path/to/file.py — описание роли

### Behavior
- Endpoint/Function: описание входов → выходов

### Acceptance Criteria
- Given [precondition] When [action] Then [expected]

### Edge Cases
- [Category]: [description]

## Change History

### vN (YYYY-MM-DD) — Title
- ADDED: что добавлено
- MODIFIED: что изменено
- REMOVED: что удалено
- Plan: [link to plan](../docs/plans/FEAT-NNN-name-vN.md)
```

---

## 2. Команды (workflow)

### Полный workflow

```
/specify → /plan FEAT-NNN → /review-plan → /implement → /verify → /generate-tests
                                ↑ корректировка спеки                ↑ или после /specify
```

### /specify (НОВАЯ)

**Назначение:** Создание или обновление living spec.

**Если FEAT не существует:**
1. Берёт Next ID из registry.md
2. Создаёт specs/FEAT-NNN-name.md (Status: DRAFT)
3. Обновляет registry.md (добавляет строку, инкрементирует Next ID)
4. Собирает требования через AskUserQuestion
5. Записывает Overview, Acceptance Criteria, Edge Cases

**Если FEAT уже существует:**
1. Читает текущую спеку
2. Спрашивает что меняем через AskUserQuestion
3. Создаёт delta-секцию в Change History с ADDED/MODIFIED/REMOVED
4. Обновляет Status: MODIFIED

### /plan (ИЗМЕНЁННЫЙ)

**Изменения:**
- Принимает FEAT-ID: /plan FEAT-001 или /plan FEAT-001 --delta
- Phase 0: Читает living spec вместо описания от пользователя
- Phase 3: Задачи нумеруются Section.Task (1.1, 1.2...)
- Phase 4: Сохраняет как docs/plans/FEAT-NNN-name.md (или -v2, -v3 для повторных)
  - Убраны даты из имён файлов, дата только внутри файла
- В план добавляется секция Delta с ADDED/MODIFIED/REMOVED из спеки
- Обновляет registry.md (добавляет ссылку на план)

### /review-plan (НОВАЯ)

**Паттерн:** Fan-out/Fan-in — 3 агента параллельно.

**Шаг 1 — Fan-out (параллельно, 3 Task агента с model: sonnet):**

| Агент | Чеклист (8 пунктов) | Output |
|-------|---------------------|--------|
| Architect | Boundaries, data flow, tech choices, scalability, security, API contracts, error handling, dependencies | .claude/reviews/REVIEW_ARCHITECT.md |
| Backend | DB schema, API endpoints, auth flow, validation, async ops, migrations, error responses, performance | .claude/reviews/REVIEW_BACKEND.md |
| Frontend | UI states, component hierarchy, Server/Client components, form validation, optimistic updates, a11y, responsive, error boundaries | .claude/reviews/REVIEW_FRONTEND.md |

Каждый агент:
- Оценивает каждый пункт: PASS / FAIL
- Для FAIL: severity (BLOCKER/MAJOR/MINOR) + fix
- Генерирует 3-5 edge cases своего домена

**Шаг 2 — Консолидация (orchestrator):**
- Читает все 3 файла
- Дедуплицирует
- Группирует edge cases по категориям: Data, State, Concurrency, Integration, UX
- Выносит вердикт: APPROVED / NEEDS REVISION / BLOCKED
- Пишет .claude/reviews/REVIEW_CONSOLIDATED.md

**Шаг 3 — Если NEEDS REVISION:**
- Обновляет план и спеку
- Добавляет edge cases в acceptance criteria спеки
- Повторяет ревью для затронутых доменов

### /implement (ИЗМЕНЁННЫЙ)

**Новый шаг после "When All Tasks Complete" — ARCHIVE:**

После шага 4 (Status: COMPLETE):
5. Читает specs/FEAT-NNN.md
6. Мержит дельту из плана в секцию "Current State"
7. Обновляет список Components (файлы/пути)
8. Обновляет Behavior (endpoints/functions)
9. Добавляет запись в Change History (vN, дата, ADDED/MODIFIED/REMOVED, ссылка на план)
10. Обновляет Status спеки: DRAFT→ACTIVE или MODIFIED→ACTIVE
11. Обновляет registry.md (статус)

### /verify (ЗАМЕНА — расширенный из "claude code")

10-шаговый процесс:
1. Unit tests — запуск + фикс
2. Integration tests — запуск + фикс
3. Program execution (MANDATORY — тесты ≠ работающая программа)
4. Feature parity check (для миграций)
5. Call chain analysis (trace up/down, side effects)
6. Coverage check (>=80%)
7. Quality checks (ruff, mypy)
8. Code review simulation (чеклист: logic, architecture, performance, security, readability, error handling, conventions)
9. E2E verification (API testing или browser testing)
10. Final verification + plan status update (COMPLETE → VERIFIED)

### /generate-tests (НОВАЯ)

**Паттерн:** Pipeline — PM → Tester → Writer → Validation.

**Вызов:**
```
/generate-tests FEAT-001
/generate-tests FEAT-001 --e2e --url=http://localhost:3000
```

**Шаг 1 — PM Agent (acceptance criteria):**
- Читает specs/FEAT-NNN.md
- Извлекает user-facing behaviors
- Генерирует Given/When/Then для каждого сценария
- Добавляет edge cases и boundary conditions
- Output: tests/scenarios/FEAT-NNN-scenarios.md

**Шаг 2 — Tester Agent (test matrix):**
- Читает scenarios.md
- Классифицирует: smoke / regression / edge_case / negative / boundary
- Приоритизирует: P0 / P1 / P2
- Проверяет покрытие vs acceptance criteria
- Output: tests/scenarios/FEAT-NNN-matrix.md

**Шаг 3 — Test Writer Agent (executable tests):**
- Для unit/integration: pytest (Python) или Jest (TypeScript)
- Для E2E (если --e2e): Playwright MCP или Chrome MCP
  - Навигирует по приложению
  - Верифицирует селекторы live
  - Генерирует Playwright тесты
- Output: tests/unit/test_feat_NNN_*.py и/или tests/e2e/feat_NNN_*.spec.ts

**Шаг 4 — Tester Agent (validation):**
- Запускает сгенерированные тесты
- Фиксит failing тесты
- Генерирует coverage report
- Output: tests/scenarios/FEAT-NNN-coverage.md

### /remember (НОВАЯ — перенос из "claude code")

Переносим as-is. Сохраняет learnings в Cipher перед /clear:
1. Обновляет progress в плане
2. Собирает learnings (архитектура, call chains, side effects, gotchas)
3. Сохраняет в Cipher в структурированном формате
4. Подтверждает: "Stored N learnings. Run /clear → /implement"

---

## 3. Новые агенты

### Для ревью планов (3 агента)

**.claude/agents/plan-reviewer-arch.md**
- Role: Архитектурное ревью
- Tools: Read, Glob, Grep (read-only)
- Model: sonnet
- Чеклист: 8 пунктов (boundaries, data flow, tech choices, scalability, security, API contracts, error handling, dependencies)
- Output: severity + fix + 3-5 edge cases

**.claude/agents/plan-reviewer-backend.md**
- Role: Backend feasibility
- Tools: Read, Glob, Grep (read-only)
- Model: sonnet
- Чеклист: 8 пунктов (DB schema, API endpoints, auth, validation, async, migrations, error responses, performance)

**.claude/agents/plan-reviewer-frontend.md**
- Role: Frontend feasibility
- Tools: Read, Glob, Grep (read-only)
- Model: sonnet
- Чеклист: 8 пунктов (UI states, components, Server/Client, forms, optimistic updates, a11y, responsive, error boundaries)

### Для генерации тестов (2 агента)

**.claude/agents/test-pm.md**
- Role: Извлечение acceptance criteria из спеки
- Tools: Read, Glob, Grep
- Model: sonnet
- Output: structured Given/When/Then + edge cases

**.claude/agents/test-writer.md**
- Role: Генерация executable тестов
- Tools: Read, Write, Edit, Bash, Playwright MCP / Chrome MCP
- Model: opus
- Output: pytest/Jest/Playwright файлы

---

## 4. Хуки и Rules (перенос из "claude code")

### Новые хуки

| Хук | Тип | Trigger | Назначение |
|-----|-----|---------|-----------|
| rules_supervisor.py | Stop | Конец сессии, /implement + Status: COMPLETE | Парсит транскрипт → Gemini API → compliance report → REVIEWED/NEEDS_FIX |
| context_monitor.py | PostToolUse | После каждого tool use | Предупреждает при 85% контекста, блокирует при 95% |

### Новые Rules

| Rule | Что добавляет |
|------|--------------|
| workflow-enforcement.md | Строгий lifecycle PENDING→COMPLETE→VERIFIED, mandatory task tracking |
| verification-before-completion.md | Evidence before claims |
| execution-verification.md | Обязательный запуск программы |
| git-operations.md | Git best practices |
| systematic-debugging.md | Системный подход к дебагу |

### Адаптация Rules Supervisor

Добавить в проверки:
- spec status обновлён (MODIFIED → ACTIVE после implement)
- registry.md обновлён
- Change History содержит запись для текущего плана

---

## 5. Обновление CLAUDE.md

Добавить:
- Описание living specs workflow
- Новые команды: /specify, /review-plan, /generate-tests, /remember
- Новые агенты: plan-reviewer-arch/backend/frontend, test-pm, test-writer
- Обновлённую таблицу workflow

---

## 6. Список изменяемых файлов

### Создать (19 новых)

| Файл | Тип |
|------|-----|
| specs/registry.md | Living specs registry |
| .claude/commands/specify.md | /specify command |
| .claude/commands/review-plan.md | /review-plan command |
| .claude/commands/generate-tests.md | /generate-tests command |
| .claude/commands/remember.md | /remember command (из "claude code") |
| .claude/agents/plan-reviewer-arch.md | Architect reviewer |
| .claude/agents/plan-reviewer-backend.md | Backend reviewer |
| .claude/agents/plan-reviewer-frontend.md | Frontend reviewer |
| .claude/agents/test-pm.md | Test PM agent |
| .claude/agents/test-writer.md | Test writer agent |
| .claude/hooks/rules_supervisor.py | Rules Supervisor (адаптированный) |
| .claude/hooks/context_monitor.py | Context Monitor |
| .claude/rules/standard/workflow-enforcement.md | Workflow rules |
| .claude/rules/standard/verification-before-completion.md | Verification rules |
| .claude/rules/standard/execution-verification.md | Execution rules |
| .claude/rules/standard/git-operations.md | Git rules |
| .claude/rules/standard/systematic-debugging.md | Debugging rules |
| .claude/reviews/.gitkeep | Placeholder для review outputs |
| tests/scenarios/.gitkeep | Placeholder для test scenarios |

### Изменить (6 существующих)

| Файл | Изменения |
|------|----------|
| .claude/commands/plan.md | FEAT-ID вместо дат, чтение спеки, delta-секция |
| .claude/commands/implement.md | Archive-шаг, обновление спеки и registry |
| .claude/commands/verify.md | Замена на 10-шаговый из "claude code" |
| .claude/settings.local.json | Добавить rules_supervisor и context_monitor в hooks |
| CLAUDE.md | Новые команды, агенты, workflow |
| .ai-rules.md | Обновить workflow section |

---

## Риски и митигации

| Риск | Вероятность | Влияние | Митигация |
|------|------------|---------|-----------|
| Gemini API недоступен | Низкая | Средний | Fallback: skip supervisor, только /verify |
| 3 параллельных агента → расход токенов | Высокая | Средний | sonnet для reviewers, scope narrowing |
| Рассинхрон spec и plan | Средняя | Высокий | Archive-шаг в /implement + supervisor |
| Verbose для мелких фич | Средняя | Средний | Быстрый путь: /plan без /specify |

---

## Open Questions

- Нужен ли MCP Cipher или достаточно file-based памяти?
- Playwright MCP vs Chrome MCP для E2E тестов?
