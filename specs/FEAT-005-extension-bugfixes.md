# FEAT-005: Исправление критических багов расширения

**Статус:** COMPLETE
**Дата:** 2026-03-07
**Приоритет:** Высокий

---

## Проблема

Расширение AI Sales Copilot имеет три критических бага, которые делают продукт непригодным для использования:

1. **Брифинг исчезает** — при закрытии и повторном открытии popup текст брифинга пропадает
2. **Виджет нельзя двигать** — плавающий элемент «AI Слушаю» застрял внизу справа, перекрывает элементы CRM
3. **Подсказки не работают** — основной сценарий продукта (аудио → распознавание → подсказки менеджеру) полностью сломан

---

## Задача 1: Сохранение брифинга между сессиями popup

### Текущее поведение
- Пользователь загружает файл → брифинг генерируется и отображается
- Пользователь закрывает popup (Chrome уничтожает DOM)
- Пользователь открывает popup → брифинг пуст, как будто ничего не было

### Ожидаемое поведение
- Брифинг сохраняется при закрытии popup
- При повторном открытии — брифинг отображается сразу из кэша
- При новой загрузке файла — старый брифинг очищается

### Корневая причина
`PopupState` (popup.ts:30-35) хранит только метаданные:
```typescript
interface PopupState {
  sessionId: string;
  kbId: string;
  capturing: boolean;
  chunksCount: number;
  // briefing — НЕ ХРАНИТСЯ!
}
```

JSON брифинга (`BriefingData`) получается с API, рендерится в DOM, но никуда не сохраняется. При переоткрытии `init()` восстанавливает только состояние REC-кнопки.

### Технический план

**Файл:** `extension/src/popup/popup.ts`

1. **Расширить `PopupState`** (строка 30):
   ```typescript
   interface PopupState {
     sessionId: string;
     kbId: string;
     capturing: boolean;
     chunksCount: number;
     briefing: BriefingData | null;  // НОВОЕ
   }
   ```

2. **Обновить `loadState()`** (строка 37) — добавить `briefing: null` в дефолт

3. **Кэшировать брифинг после получения** — в `fetchAndRenderBriefing()` (строка 548), после рендера:
   ```typescript
   await saveState({ briefing: data });
   ```

4. **Восстанавливать при инициализации** — в `init()` (строка 622), после восстановления REC:
   ```typescript
   if (state.briefing) {
     renderPortrait(state.briefing.portrait, portraitEl);
     renderStrategy(state.briefing.strategy, strategyEl);
     renderObjections(state.briefing.objections, objList);
     show(content); show(refreshBtn); hide(loading);
   }
   ```

5. **Очищать при новой загрузке** — в `doUpload()` (строка 254):
   ```typescript
   await saveState({ briefing: null });
   ```

### Критерии приёмки
- [x] Загрузить файл → увидеть брифинг → закрыть popup → открыть → брифинг на месте
- [x] Загрузить новый файл → старый брифинг очищается → новый отображается
- [x] Кнопка «Обновить брифинг» перезаписывает кэш
- [x] chrome.storage.session содержит ключ `briefing` с данными

---

## Задача 2: Перетаскивание виджета

### Текущее поведение
- Виджет зафиксирован в правом нижнем углу (`position:fixed; bottom:16px; right:16px`)
- Нельзя переместить
- Перекрывает элементы CRM-интерфейса

### Ожидаемое поведение
- Виджет можно перетаскивать мышкой за pill-элемент
- Клик (без движения) по-прежнему открывает/закрывает панель
- Виджет не выходит за границы viewport
- Курсор меняется на `grab`/`grabbing`

### Корневая причина
Позиционирование захардкожено в widget.ts:245-246:
```typescript
this.host.style.cssText = "position:fixed;z-index:2147483647;bottom:16px;right:16px;";
```
Обработчиков перетаскивания (mousedown/mousemove/mouseup) нет.

### Технический план

**Файл:** `extension/src/content/widget.ts`

1. **Добавить поля состояния** в класс `CopilotWidget`:
   ```typescript
   private isDragging = false;
   private dragStartX = 0;
   private dragStartY = 0;
   private hostStartX = 0;
   private hostStartY = 0;
   private dragMoved = false;
   ```

2. **Хелпер `convertToTopLeft()`** — при первом перетаскивании конвертирует `bottom/right` в `left/top`:
   ```typescript
   private convertToTopLeft(): void {
     const rect = this.host.getBoundingClientRect();
     this.host.style.bottom = "";
     this.host.style.right = "";
     this.host.style.left = `${rect.left}px`;
     this.host.style.top = `${rect.top}px`;
   }
   ```

3. **Заменить `click` на `mousedown`** в `bindEvents()` (строка 277):
   - `mousedown` на pill: записать начальную позицию, флаг `isDragging = true`
   - `mousemove` на window: если смещение > 5px — двигать виджет
   - `mouseup` на window: если не двигали → `toggle()` (клик), если двигали → стоп

4. **Ограничить позицию** — `Math.max(0, Math.min(window.innerWidth - 60, newLeft))`

5. **CSS курсор** — в `WIDGET_CSS` изменить `#pill { cursor: grab; }` и `#pill:active { cursor: grabbing; }`

### Критерии приёмки
- [x] Виджет перетаскивается мышкой за pill
- [x] Клик без движения по-прежнему открывает/закрывает панель
- [x] Виджет не выходит за пределы экрана
- [x] Курсор меняется на grab/grabbing при наведении/зажатии
- [x] Панель остаётся привязанной к pill при перетаскивании

---

## Задача 3: Починить пайплайн подсказок

### Текущее поведение
- Аудио захватывается и передаётся на бэкенд (пользователь подтверждает)
- Подсказки НЕ отображаются в виджете
- Ошибок в логах НЕТ (ошибки проглатываются)

### Ожидаемое поведение
- Менеджер говорит → речь распознаётся → LLM сравнивает со сценарием → подсказка отображается в виджете
- Ошибки пайплайна логируются и видны в терминале
- VAD не отсеивает нормальную речь

### Корневая причина

**Пайплайн полностью реализован**, но имеет критические runtime-баги:

```
Аудио фрейм (main.py:419)
→ parse_frame() + deinterleave_stereo()
→ vad.detect_speech() — энергия/10000 >= 0.5 ← ПОРОГ СЛИШКОМ ВЫСОК
→ stt.send_audio() — gRPC к SaluteSpeech
→ on_transcript callback → orchestrator.handle_transcript()
→ _run_pipeline() → _stream_hint() ← ОШИБКИ ПРОГЛАТЫВАЮТСЯ
→ hint_start/chunk/end → WebSocket → service-worker → виджет
```

**Три `contextlib.suppress(Exception)`** в orchestrator.py:

| Строка | Что оборачивает | Последствия |
|--------|-----------------|-------------|
| 45 | Отправка транскрипта по WS | Транскрипт не доходит, тишина |
| 56 | Сохранение реплики в Redis | Контекст сессии теряется |
| **99** | **Весь `_stream_hint()` — LLM вызов** | **Подсказки молча не работают** |

### Технический план

#### 3a. Оркестратор — убрать подавление ошибок и добавить логирование

**Файл:** `backend/pipeline/orchestrator.py`

**Строка 45-53** — транскрипт:
```python
# БЫЛО: with contextlib.suppress(Exception):
# СТАЛО:
try:
    await self._ws.send_json({...})
except Exception as exc:
    logger.warning("Не удалось переслать транскрипт: %r", exc)
```

**Строка 56-59** — сохранение реплики:
```python
try:
    await self._session.add_utterance(...)
except Exception as exc:
    logger.warning("Не удалось сохранить реплику: %r", exc)
```

**Строка 99-100** — генерация подсказки (КРИТИЧНО):
```python
try:
    await self._stream_hint(hint_ctx)
except Exception as exc:
    logger.error("Ошибка пайплайна подсказок: %r (сессия=%s)", exc, self._session_id)
    try:
        await self._ws.send_json({
            "type": "error",
            "code": "HINT_PIPELINE_FAILED",
            "message": str(exc)[:200],
        })
    except Exception:
        pass
```

**Убрать** `import contextlib` (строка 6)

**Добавить логирование** при запуске пайплайна (после строки 84):
```python
logger.info("Пайплайн запущен: session=%s query=%s", self._session_id, query[:80])
```

#### 3b. Оркестратор — починить пустой hint_end

**Строка 128-129:** когда `tokens` пуст, виджет застревает в состоянии HINT_ACTIVE. Добавить:
```python
if not tokens:
    await self._ws.send_json({
        "type": "hint_end", "hint": "", "source": "",
        "sentiment": "neutral", "color": "blue",
    })
    return
```

#### 3c. VAD — снизить порог

**Файл:** `backend/pipeline/vad.py`

**Строка 64:** добавить info-лог при обнаружении речи:
```python
if is_speech:
    logger.info("VAD: речь обнаружена [%s] prob=%.3f", channel, prob)
```

**Файл:** `backend/config.py`

**Строка 17:** изменить дефолт с `0.5` на `0.3`:
```python
vad_threshold: float = 0.3
```

**Файл:** `backend/.env`

Установить `VAD_THRESHOLD=0.3`

**Обоснование:** Формула энергии: `sum(abs(s)) / n / 10000.0`. При захвате звука вкладки средняя амплитуда ~2000-4000, что даёт вероятность 0.2-0.4. Порог 0.5 отсеивает нормальную речь.

#### 3d. Виджет — логировать ошибки бэкенда

**Файл:** `extension/src/content/widget.ts`

В обработчике сообщений, для типа `"error"`:
```typescript
case "error":
  console.error(`[Copilot] Ошибка бэкенда: ${msg.code} — ${msg.message}`);
  break;
```

### Критерии приёмки
- [x] Все `contextlib.suppress(Exception)` заменены на try/except с логированием
- [x] При запуске сессии и обнаружении речи видны логи в терминале
- [x] VAD порог снижен до 0.3
- [x] При ошибке LLM — ошибка видна в логах бэкенда и в консоли расширения
- [x] При пустом ответе LLM — виджет не застревает в HINT_ACTIVE
- [ ] При работающем STT и LLM — подсказки отображаются в виджете

---

## Порядок реализации

| # | Задача | Файлы | Риск |
|---|--------|-------|------|
| 1 | Сохранение брифинга | popup.ts | Низкий |
| 2 | Перетаскивание виджета | widget.ts | Средний |
| 3 | Пайплайн подсказок | orchestrator.py, vad.py, config.py, .env, widget.ts | Высокий |

## Проверка

| Задача | Как проверить |
|--------|---------------|
| Брифинг | Загрузить файл → увидеть брифинг → закрыть popup → открыть → брифинг на месте |
| Перетаскивание | Открыть страницу → зажать pill → тянуть → двигается; клик → переключает |
| Пайплайн | Начать сессию → говорить → логи VAD/STT/LLM в терминале → подсказки в виджете |
