# Анализ: Аудио → Транскрипт → Хинты

> Ответы на вопросы по текущему коду (2026-03-09)

---

## Вопрос 1: Появляется ли транскрипт в реальном времени?

**Ответ: ДА** (гибридный режим)

### Как это работает

```
Аудио → STT → Backend WS → Offscreen → Sidepanel → DOM
```

### Этапы (с кодом)

| # | Этап | Файл:строка | Что происходит |
|---|------|-------------|----------------|
| 1 | STT генерирует | `backend/pipeline/stt.py:299-310` | `is_final: bool = resp.eou` |
| 2 | Backend отправляет | `backend/pipeline/orchestrator.py:44-52` | `{"type": "transcript", "is_final": ...}` |
| 3 | Offscreen пересылает | `offscreen.ts:40-48` | `port.postMessage({type: "WS_MESSAGE", payload})` |
| 4 | Sidepanel рендерит | `sidepanel.ts:462-529` | `handleTranscript()` |

### Гибридный режим

**Interim** (`is_final=false`):
- Появляется сразу при распознавании слов
- Обновляется на месте (in-place update)
- Код: `sidepanel.ts:472-487`

```typescript
if (lastEntry?.classList.contains("interim")) {
    lastEntry.querySelector(".transcript-text").textContent = msg.text;
}
```

**Final** (`is_final=true`):
- Фиксируется при конце фразы (EOU)
- Создаётся новая запись с анимацией
- Код: `sidepanel.ts:489-512`

### Ограничения

- Только один interim на спикера (перезаписывается)
- Previous interim не накапливаются

---

## Вопрос 2: Скроллируется ли транскрипт автоматически?

**Ответ: ДА** (с определением вмешательства пользователя)

### Логика авто-скролла

**Код:** `sidepanel.ts:515-521`

```typescript
if (isAtBottom || isAutoScrolling) {
    list.scrollTop = list.scrollHeight;
    hide($("jump-to-latest"));
} else {
    show($("jump-to-latest"));
}
```

### Определение "на дне"

**Код:** `sidepanel.ts:467-468`

```typescript
const isAtBottom =
    list.scrollHeight - list.scrollTop - list.clientHeight < 30;  // 30px порог
```

### Поведение

| Действие пользователя | Реакция |
|----------------------|---------|
| Находится внизу | Авто-скролл продолжается |
| Прокрутил вверх | Появляется кнопка "Jump to latest" |
| Нажал кнопку | Скроллит вниз, включает авто-скролл |
| Прокрутил обратно вниз | Авто-скролл включается автоматически |

### Код отслеживания скролла

**Код:** `sidepanel.ts:535-540`

```typescript
list?.addEventListener("scroll", () => {
    const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 30;
    isAutoScrolling = atBottom;
    if (atBottom) hide(jumpPill);
});
```

---

## Вопрос 3: Появляются ли хинты и подсказки?

**Ответ: ДА** (потоковая генерация token-by-token)

### Триггер хинта

Хинт генерируется когда:
1. **Спикер = client** (клиент говорит)
2. **is_final = true** (фраза закончена)
3. **Debounce** пройден (500ms с прошлого хинта)

**Код:** `orchestrator.py:64`, `orchestrator.py:81`

```python
if transcript.speaker != "client":
    return
if not transcript.is_final:
    return
```

### Поток хинта (3 сообщения)

| Сообщение | Когда | Код |
|-----------|-------|-----|
| `hint_start` | Начало генерации | `orchestrator.py:129-131` |
| `hint_chunk` | Каждый токен LLM | `orchestrator.py:135-137` |
| `hint_end` | Конец генерации | `orchestrator.py:172-180` |

### Рендеринг в UI

| Этап | Файл:строка | Что происходит |
|------|-------------|----------------|
| Start | `sidepanel.ts:413-427` | Очищает прошлый хинт, показывает область |
| Chunk | `sidepanel.ts:429-440` | Накапливает токены с rAF batching |
| End | `sidepanel.ts:442-456` | Финализирует текст, показывает source badge |

### Код рендеринга чанков

**Код:** `sidepanel.ts:429-440`

```typescript
hintPendingText += msg.text;
if (!hintRafPending) {
    hintRafPending = true;
    requestAnimationFrame(() => {
        hintRafPending = false;
        $("hint-text").textContent += hintPendingText;
        hintPendingText = "";
    });
}
```

### Где отображается хинт

**HTML:** `sidepanel.html:159-162`

```html
<div id="hint-area" class="hint-area">
    <div id="hint-text"></div>
    <div id="hint-source"></div>
</div>
```

- Расположение: Верх Phase 3 (sticky)
- Цвет: По sentiment (green/blue/red)
- Source badge: Показывает источник подсказки

### Ограничения

| Ограничение | Код |
|-------------|-----|
| Только для CLIENT | `orchestrator.py:62-63` |
| Debounce 500ms | `orchestrator.py:81` |
| Не сохраняются | Нет записи в Redis |

---

## Итоговая таблица

| Функция | Работает? | Ключевой код |
|---------|-----------|--------------|
| Real-time транскрипт | ✅ ДА | `sidepanel.ts:462-529` |
| Auto-scroll | ✅ ДА | `sidepanel.ts:515-548` |
| Хинты для менеджера | ✅ ДА | `orchestrator.py:125-183` |

---

## Полный путь данных

```
┌─────────────────────────────────────────────────────────────────────┐
│ EXTENSION                                                           │
│                                                                     │
│  1. Offscreen захватывает аудио (mic L + tab R)                    │
│  2. AudioWorklet → PCM16 interleaved                               │
│  3. WsClient → binary frames → Backend                             │
│                                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ WebSocket
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ BACKEND                                                             │
│                                                                     │
│  4. main.py: parse_frame() → deinterleave_stereo()                 │
│  5. VAD → есть речь?                                                │
│  6. STT → transcript (interim + final)                             │
│  7. WS → {"type": "transcript", "is_final": ...}                   │
│  8. Если client + final → LLM → hint_start/chunk/end               │
│                                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ WebSocket
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ EXTENSION (Sidepanel)                                               │
│                                                                     │
│  9. handleTranscript() → рендер в #transcript-list                 │
│ 10. Auto-scroll если isAtBottom                                     │
│ 11. handleHint*() → рендер в #hint-area                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```
