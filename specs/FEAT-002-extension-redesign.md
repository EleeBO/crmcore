# FEAT-002: Audio Pipeline Fix (End-to-End)

Status: ACTIVE
Created: 2026-03-01
Last Modified: 2026-03-02

## Overview

Починить полностью нерабочий audio pipeline Chrome-расширения AI Sales Copilot. Текущее состояние: кнопка "Начать звонок" падает с ошибкой, AudioWorklet отправляет моно вместо стерео, offscreen port не подключён к service worker — хинты теряются. Цель: рабочий сквозной сценарий загрузка файлов → начало звонка → аудио → транскрипция → подсказки в виджете.

## Current State

### Что работает
- Загрузка файлов через popup → backend генерирует Scenario JSON (FEAT-001)
- Генерация брифинга через API `/api/v1/briefing`
- Content-script виджет отображается на странице CRM (pill + panel)
- WebSocket клиент и offscreen document реализованы (но не работают вместе)

### Fixed (FEAT-002 implementation, 2026-03-02)
1. **Popup → SW:** Popup now queries `chrome.tabs.query()` for active tab and sends `tabId` in message payload
2. **Offscreen → SW:** SW has `onConnect` listener for offscreen port — relays WS messages to session tab only
3. **AudioWorklet:** Reads both channels (mic L, tab R) and outputs interleaved stereo PCM16
4. **WS lifecycle:** `waitForOpen()` replaces `setTimeout(200)` race; `onReconnect` replays `session_start`
5. **Backend hardening:** SessionManager + briefing guard against Redis=None; error frames sent to extension on failure

### Components
- `extension/src/popup/popup.ts` — логика popup (session start)
- `extension/src/background/service-worker.ts` — message routing, tabCapture
- `extension/src/offscreen/offscreen.ts` — audio capture pipeline
- `extension/src/audio-worklet.ts` — stereo PCM interleaving (fixed)
- `extension/src/lib/ws-client.ts` — WebSocket клиент
- `extension/src/shared/messages.ts` — типы сообщений
- `extension/src/content/widget.ts` — Shadow DOM виджет
- `backend/pipeline/audio.py` — deinterleave_stereo
- `backend/pipeline/orchestrator.py` — hint pipeline
- `backend/session/manager.py` — Redis session state

## Acceptance Criteria

### AC-1: Audio pipeline работает end-to-end
- Given пользователь загрузил файлы и нажал "Начать звонок"
- When идёт звонок (аудио с микрофона и вкладки)
- Then backend получает stereo аудио, разделяет на mic/tab каналы
- And STT транскрибирует оба канала
- And LLM генерирует подсказки на основе сценария + транскрипта
- And подсказки отображаются в виджете на странице

### AC-2: Popup корректно передаёт tabId
- Given пользователь на странице CRM нажимает "Начать звонок"
- When popup отправляет START_SESSION
- Then сообщение содержит tabId активной вкладки
- And service worker использует tabId для tabCapture

### AC-3: Offscreen → SW → Widget relay работает
- Given backend отправляет hint/transcript через WS
- When offscreen получает сообщение
- Then оно доставляется через port → SW → content script → widget

### AC-4: WS подключение надёжное
- Given offscreen создаёт WsClient
- When WS ещё не открыт
- Then session_start отправляется только после подтверждения open
- When WS обрывается mid-session
- Then автореконнект + повторный session_start

### AC-5: Backend устойчив к Redis = None
- Given Redis недоступен
- When идёт WS сессия
- Then SessionManager не падает, pipeline продолжает работать (без истории)
- And briefing endpoint возвращает осмысленный ответ (не HTTP 500)

## Edge Cases

- **Нет активной вкладки / chrome:// page:** Показать ошибку "Откройте вкладку с CRM"
- **Offscreen убит Chrome mid-call:** SW обнаруживает, сбрасывает captureInProgress, уведомляет popup
- **WS reconnect без session_start:** После reconnect offscreen повторно отправляет session_start
- **Двойной клик на "Начать звонок":** captureInProgress guard + popup disable кнопки
- **Popup закрыт во время записи:** Сессия продолжается, при открытии popup восстанавливает состояние
- **Хинты только в целевую вкладку:** SW отправляет хинты только в tab из session, не во все вкладки

## Change History

### v1 (2026-03-01) — Initial specification
- ADDED: Initial spec from `docs/extension-issues.md` (all issues)

### v2 (2026-03-01) — Split into phases after multi-agent review
- MODIFIED: Scope reduced to audio pipeline fix only (Phase A)
- REMOVED: UI redesign (moved to FEAT-003)
- REMOVED: Briefing formatting, REC button, widget animation (moved to FEAT-003)
- ADDED: AC-2 through AC-5 based on architect/backend/frontend review findings
- ADDED: New blockers found: mono AudioWorklet, orphaned offscreen port, WS race condition
- Plan: [FEAT-002 plan](../docs/plans/FEAT-002-audio-pipeline-fix.md)

### v3 (2026-03-02) — Implementation complete
- MODIFIED: messages.ts — START_SESSION includes tabId, STOP_SESSION includes sessionId
- MODIFIED: popup.ts — queries active tab, disables start button during async op
- MODIFIED: service-worker.ts — uses message.tabId, onConnect for offscreen port, targeted broadcast
- MODIFIED: audio-worklet.ts — reads both channels, outputs interleaved stereo PCM16
- MODIFIED: ws-client.ts — waitForOpen(), onReconnect callback
- MODIFIED: offscreen.ts — uses waitForOpen(), stores session params for reconnect
- MODIFIED: session/manager.py — Redis=None guards on all methods
- MODIFIED: briefing/portrait.py — Redis=None guard returns empty BriefingResponse
- MODIFIED: pipeline/orchestrator.py — sends error frames on LLM failure
- MODIFIED: main.py — wraps session_start in try/except, sends error frames
- ADDED: backend/tests/test_redis_none.py (4 tests)
- ADDED: backend/tests/test_error_frames.py (2 tests)
- Plan: [FEAT-002 plan](../docs/plans/FEAT-002-audio-pipeline-fix.md)
