# SaluteSpeech STT — Code Review

> Дата: 2026-03-10
> Ревьюверы: Architect, Backend

---

## Общий вердикт: ⚠️ ТРЕБУЕТСЯ ИСПРАВЛЕНИЕ

---

## Сравнение: Production vs Test

| Параметр | Production (`stt.py`) | Test (`test_salutespeech_synthetic.py`) | OK? |
|----------|----------------------|----------------------------------------|-----|
| `enable_multi_utterance` | ❌ НЕ УСТАНОВЛЕН | ✅ `True` | **НЕТ** |
| `no_speech_timeout` | 20s | 10s | ✅ (OK) |
| `enable_partial_results` | `True` | `True` | ✅ |
| `language` | `ru-RU` | `ru-RU` | ✅ |
| Token refresh | При реконнекте | При реконнекте | ✅ |
| SSL сертификат | Russian Trusted CA | Russian Trusted CA | ✅ |

---

## Критические проблемы

### 1. MISSING `enable_multi_utterance=True` 🔴 HIGH

**Файл:** `backend/pipeline/stt.py:274-280`

**Проблема:** Production код НЕ устанавливает `enable_multi_utterance=True`, а тест — устанавливает.

**Последствия:**
- Без этого флага сервер закрывает поток после первой фразы (EOU)
- Для продолжения распознавания требуется реконнект
- В реальном разговоре это приведёт к потере аудио

**Исправление:**
```python
# stt.py:274-281
yield recognition_pb2.RecognitionRequest(
    options=recognition_pb2.RecognitionOptions(
        audio_encoding=recognition_pb2.RecognitionOptions.PCM_S16LE,
        sample_rate=16000,
        language="ru-RU",
        enable_partial_results=True,
        enable_multi_utterance=True,  # ← ДОБАВИТЬ
        no_speech_timeout=_nst,
    )
)
```

---

### 2. Unbounded Queue — Memory Leak 🟡 MEDIUM

**Файл:** `backend/pipeline/stt.py:252`

**Проблема:** `asyncio.Queue()` без `maxsize` может расти бесконтрольно.

**Исправление:**
```python
q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=100)  # ~20s audio
```

---

### 3. Token Error Handling 🟡 MEDIUM

**Файл:** `backend/pipeline/stt.py:197-223`

**Проблема:** Ошибки при получении токена не логируются специфично.

**Исправление:**
```python
async def _get_token(self) -> str:
    try:
        # ... existing code ...
    except httpx.HTTPStatusError as e:
        logger.error(f"SaluteSpeech token request failed: {e.response.status_code}")
        raise
    except Exception as e:
        logger.error(f"SaluteSpeech token acquisition error: {e!r}")
        raise
```

---

### 4. gRPC Error Specificity 🟡 MEDIUM

**Файл:** `backend/pipeline/stt.py:315-323`

**Проблема:** Все ошибки gRPC обрабатываются одинаково.

**Исправление:**
```python
except grpc.aio.AioRpcError as exc:
    if exc.code() == grpc.StatusCode.UNAUTHENTICATED:
        logger.error(f"SaluteSpeech [{channel}] auth failed")
        self._token = ""  # Force refresh
    # ... rest
```

---

## Проверенные Edge Cases

| Edge Case | Обработан? | Где |
|-----------|------------|-----|
| `resp.results` is empty | ✅ ДА | `stt.py:303` — `if resp.results else ""` |
| Token expiry (>30 min) | ✅ ДА | Реконнект с refresh |
| Network interrupt | ✅ ДА | 5 попыток реконнекта |
| CancelledError | ✅ ДА | `stt.py:312-314` |
| Empty audio chunk | ⚠️ НЕТ | Передаётся в gRPC как есть |
| Queue assignment vs del | ⚠️ OK | Только 2 канала, не критично |

---

## Ответы на вопросы

### 1. Совпадает ли production код с тестовым?

**НЕ СОВСЕМ.** Основное отличие:
- **Test:** `enable_multi_utterance=True` — непрерывное распознавание
- **Production:** `enable_multi_utterance` не установлен — обрыв после первой фразы

### 2. Можно ли считать код работоспособным?

**ЧАСТИЧНО.**
- ✅ Базовая функциональность работает (проверено тестом)
- ❌ Для длинных разговоров требуется исправление `enable_multi_utterance`

### 3. Обрабатываются ли ошибки и edge cases?

**ДА, НО НЕ ВСЕ.**
- ✅ Реконнект при ошибках
- ✅ Token refresh
- ✅ Empty results
- ⚠️ Специфичные gRPC ошибки
- ⚠️ Empty audio chunks

---

## Рекомендации

### Must Fix (до production)
1. Добавить `enable_multi_utterance=True`

### Should Fix (улучшение качества)
2. Добавить `maxsize` для Queue
3. Улучшить логирование ошибок токена
4. Добавить специфичную обработку gRPC ошибок

### Nice to Have
5. Проверять empty chunks в `send_audio()`
6. Добавить metrics для мониторинга

---

## Файлы для исправления

| Файл | Строки | Изменение |
|------|--------|-----------|
| `backend/pipeline/stt.py` | 274-281 | Добавить `enable_multi_utterance=True` |
| `backend/pipeline/stt.py` | 252 | Добавить `maxsize=100` |
| `backend/pipeline/stt.py` | 197-223 | Улучшить error handling |
| `backend/pipeline/stt.py` | 315-323 | Специфичная обработка gRPC |
