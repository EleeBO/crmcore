# FEAT-005: Post-call дiarization и аналитика звонка (Yandex AsyncRecognizer)

**Status:** DRAFT
**Date:** 2026-03-13
**Author:** Claude Code + Human
**Depends on:** FEAT-004 (call-evaluation-sgr)

---

## 1. Проблема

После завершения звонка evaluator (FEAT-004) оценивает менеджера **только по тексту** транскрипта. При этом:

- Текст получен в режиме `REAL_TIME` — без контекста следующих слов, с ошибками распознавания
- Нет данных о соотношении говорит/слушает — LLM угадывает по длине реплик
- Нет данных о темпе речи — LLM не может оценить коммуникативные навыки объективно
- Нет данных о паузах перед ответом на возражение — LLM не видит тайминги
- Нет данных о перебиваниях — LLM не может оценить навыки слушания

Три критерия оценки (суммарный вес 0.55) оцениваются приблизительно вместо точно:
- `needs_discovery` (0.25): talk ratio
- `objection_handling` (0.20): паузы перед ответом
- `communication` (0.10): темп речи, перебивания

## 2. Решение

Post-call пере-распознавание аудио через Yandex SpeechKit AsyncRecognizer в режиме `FULL_DATA`:

1. Буферизация PCM-чанков в памяти во время звонка (per channel)
2. По завершении — сборка WAV, отправка каждого канала отдельно в Yandex async API
3. Получение высококачественного транскрипта с таймкодами
4. Вычисление объективных метрик диалога из таймкодов
5. Обогащение evaluator промпта аналитикой **до** запуска оценки

Архитектурный принцип: **best-effort enrichment**. Если diarization упала — evaluator работает на real-time данных как раньше.

## 3. Scope (для демо)

### В scope

- `AudioBuffer` — буферизация PCM per channel в памяти
- `YandexAsyncRecognizer` — gRPC async recognition с FULL_DATA
- `PostCallProcessor` — оркестрация post-call обработки + вычисление аналитики
- Обновление proto-файлов Yandex SpeechKit (добавить AsyncRecognizer)
- Интеграция в pipeline: session_end → diarization → evaluation
- Обогащение evaluator промпта секцией АНАЛИТИКА ЗВОНКА
- Форматирование diarized транскрипта с таймкодами
- Fallback на real-time данные при ошибках diarization

### Вне scope

- Yandex Object Storage (S3) — для демо используем gRPC content upload
- Звонки > 26 минут (ограничение gRPC content ~50 MB)
- LLM-саммаризация через YandexGPT (SummarizationOptions)
- speaker_labeling от Yandex (не нужен — каналы уже разделены аппаратно)
- conversation_analysis от Yandex (не работает на раздельных каналах)
- UI для просмотра аналитики (данные попадают в evaluator промпт)
- Сохранение аудио на диск / в облако

## 4. Архитектура

### 4.1 Поток данных

```
Во время звонка (без изменений + буферизация):
┌─────────────┐     PCM chunks      ┌──────────────────┐
│  Extension  │ ──── WebSocket ───→  │  main.py handler  │
│  (offscreen)│                      │  deinterleave()   │
└─────────────┘                      └───────┬──────────┘
                                             │
                              ┌──────────────┼──────────────┐
                              ▼              ▼              ▼
                        ┌──────────┐  ┌───────────┐  ┌──────────────┐
                        │ STT live │  │ STT live  │  │ AudioBuffer  │
                        │ (rep)    │  │ (client)  │  │ (NEW)        │
                        └──────────┘  └───────────┘  │ rep: bytearray│
                              │              │       │ client: bytearr│
                              ▼              ▼       └──────────────┘
                        ┌─────────────────────┐
                        │   Orchestrator      │
                        │   (hints — как раньше)│
                        └─────────────────────┘

По завершении звонка (session_end):
┌──────────────┐                    ┌───────────────────┐
│ AudioBuffer  │──build WAV──────→  │ Yandex Async x2   │
│ rep + client │  per channel       │ RecognizeFile      │
│ (in-memory)  │  (parallel)        │ FULL_DATA          │
└──────────────┘                    │                    │
       │                            └────────┬──────────┘
       │ clear()                             │
       ▼                                     ▼
   RAM freed                        ┌───────────────────┐
                                    │ PostCallProcessor  │
                                    │ merge by start_ms  │
                                    │ compute analytics  │
                                    └────────┬──────────┘
                                             │
                              ┌──────────────┼──────────────┐
                              ▼              ▼              ▼
                        ┌──────────┐  ┌───────────┐  ┌──────────────┐
                        │ Redis:   │  │ Redis:    │  │ Evaluator    │
                        │ replace  │  │ save      │  │ (FEAT-004)   │
                        │ eval_    │  │ eval_     │  │ получает     │
                        │ transcript│  │ analytics │  │ enriched     │
                        └──────────┘  └───────────┘  │ prompt       │
                                                     └──────────────┘
```

### 4.2 Pipeline flow (session_end)

```
session_end получен
  │
  ▼
1. ws.send_json({"type": "evaluation_started"})
  │
  ▼
2. orchestrator.on_session_end(session_id, ws, audio_buffer)
     │  # Полная сигнатура:
     │  # async def on_session_end(
     │  #     self, session_id: str, ws: WebSocket,
     │  #     audio_buffer: AudioBuffer | None,
     │  # ) -> None
     │  # audio_buffer=None если enable_post_call_diarization=False
     │  # redis доступен через self._redis (инжектируется в __init__),
     │  # НЕ передаётся как параметр on_session_end
     │
     ├── Guard: _evaluation_started → return (idempotency)
     ├── _evaluation_started = True
     │
     ├── STEP A: Post-call diarization (best-effort)
     │   ├── Guard: duration < 5s → skip
     │   ├── Guard: yandex api key not configured → skip
     │   ├── Guard: buffer > 50 MB per channel → skip (log warning)
     │   ├── post_call_processor.process(audio_buffer)
     │   │   ├── asyncio.gather(recognize(rep_wav), recognize(client_wav))
     │   │   ├── merge utterances by start_ms (with offset compensation)
     │   │   ├── compute CallAnalytics
     │   │   ├── Redis: replace eval_transcript:{session_id}
     │   │   └── Redis: set eval_analytics:{session_id}
     │   └── audio_buffer.clear()  # free RAM
     │   # Если diarization skipped (guards) — audio_buffer.clear() тоже вызывается здесь
     │
     ├── STEP B: Evaluation (FEAT-004 — обогащённый)
     │   ├── Load eval_transcript (diarized if available, real-time otherwise)
     │   ├── Load eval_analytics (CallAnalytics or None)
     │   ├── Format transcript (with timestamps if diarized)
     │   ├── Format analytics section for prompt (if available)
     │   ├── evaluator.evaluate_call(transcript, config, briefing, analytics)
     │   └── ws.send_json({"type": "evaluation_result", ...})
     │
     └── STEP C: Fallback
         └── Diarization failed → evaluator uses real-time transcript
             (analytics=None, no АНАЛИТИКА ЗВОНКА section in prompt)
  │
  ▼
3. orchestrator.teardown()  # cancels hint tasks, NOT evaluation
  │
  ▼
4. await _evaluation_task (timeout=150s)
     # Budget: diarization polling ~55s + WAV assembly ~1s
     #       + evaluation LLM primary 15s + fallback 30s
     #       + overhead ~5s = ~106s worst case
     # 150s даёт запас для медленных сетей
     # ВАЖНО: в main.py FEAT-004 стоит timeout=35s — нужно заменить на 150s
  │
  ▼
5. cleanup (stt.close, audio_buffer.clear, ws.close)
```

### 4.3 Новые файлы

| Файл | Назначение |
|------|------------|
| `backend/pipeline/audio_buffer.py` | Буферизация PCM per channel, сборка WAV |
| `backend/pipeline/yandex_async.py` | gRPC async recognition client |
| `backend/pipeline/post_call.py` | Оркестрация post-call: diarization + analytics |

### 4.4 Изменяемые файлы

| Файл | Изменение |
|------|-----------|
| `backend/main.py` | Создание AudioBuffer, передача чанков в buffer, передача buffer в orchestrator.on_session_end() |
| `backend/pipeline/orchestrator.py` | on_session_end() вызывает PostCallProcessor перед evaluator |
| `backend/pipeline/evaluator.py` | Новый параметр analytics: CallAnalytics или None в evaluate_call() |
| `backend/pipeline/prompt_formatter.py` | format_diarized_transcript(), format_analytics(), _ms_to_timestamp() |
| `backend/pipeline/yandexstt/` | Обновлённые proto-файлы (AsyncRecognizer, RecognizeFileRequest) |
| `backend/config.py` | Новый флаг: enable_post_call_diarization: bool = False |

## 5. Компоненты

### 5.1 AudioBuffer (backend/pipeline/audio_buffer.py)

```python
@dataclass
class AudioBuffer:
    """In-memory PCM buffer per channel with WAV export."""

    _buffers: dict[str, bytearray]          # {"rep": ..., "client": ...}
    _start_ts: dict[str, float]             # monotonic timestamp первого чанка
    _sample_rate: int = 16000
    _sample_width: int = 2                  # PCM16

    def append(self, channel: str, chunk: bytes) -> None:
        """Добавить PCM-чанк. Записывает start_ts при первом чанке.
        Если канал > 50 MB — молча игнорирует (mid-call guard)."""

    def get_wav(self, channel: str) -> bytes:
        """Собрать WAV из буфера канала (stdlib wave module)."""

    def duration_s(self, channel: str) -> float:
        """Длительность записи в секундах."""

    def start_offset_ms(self) -> int:
        """Разница start_ts между каналами в ms (для компенсации при merge)."""

    def estimated_memory_mb(self) -> float:
        """Текущий расход RAM обоих каналов."""

    def exceeds_limit(self) -> bool:
        """True если любой канал > 50 MB (gRPC content limit)."""

    def clear(self) -> None:
        """Освободить память обоих буферов."""
```

Память: ~1.92 MB/мин на канал. Max ~26 мин на канал (50 MB gRPC limit).

### 5.2 YandexAsyncRecognizer (backend/pipeline/yandex_async.py)

```python
@dataclass
class TimedUtterance:
    text: str
    start_ms: int
    end_ms: int
    confidence: float

@dataclass
class AsyncRecognitionResult:
    utterances: list[TimedUtterance]


class YandexAsyncRecognizer:
    """Yandex SpeechKit v3 async file recognition via gRPC."""

    GRPC_HOST = "stt.api.cloud.yandex.net:443"
    POLL_BACKOFF = [1, 2, 4, 8, 8, 8, 8, 8, 8]  # секунды, sum = 55s
    MAX_CONTENT_BYTES = 50 * 1024 * 1024          # 50 MB

    def __init__(self, api_key: str) -> None: ...

    async def recognize(self, wav_bytes: bytes) -> AsyncRecognitionResult:
        """
        1. RecognizeFileRequest(content=wav_bytes, FULL_DATA)
        2. Получить operation_id
        3. Poll GetRecognition с exponential backoff
        4. Parse alternatives с таймкодами → list[TimedUtterance]
        """

    async def _poll_operation(self, operation_id: str) -> Any:
        """Poll until done=true или timeout (сумма POLL_BACKOFF)."""
```

gRPC channel config:
- `max_send_message_length = 55 * 1024 * 1024` (55 MB, запас над 50 MB)
- Standard SSL credentials (без Russian Root CA)
- Auth: `("authorization", f"Api-Key {api_key}")` в metadata

RecognizeFileRequest:
- `content = wav_bytes`
- `recognition_model.model = "general"`
- `recognition_model.audio_format = ContainerAudio(WAV)`
- `recognition_model.audio_processing_type = FULL_DATA`
- **НЕ** используем: `speaker_labeling`, `speech_analysis` (оба бессмысленны на одноканальном аудио с одним спикером)
- Все метрики (talk time, word count, speech rate) вычисляем сами из таймкодов utterances

### 5.3 PostCallProcessor (backend/pipeline/post_call.py)

```python
@dataclass
class DiarizedUtterance:
    speaker: str              # "rep" / "client"
    text: str
    start_ms: int
    end_ms: int

@dataclass
class CallAnalytics:
    total_duration_s: float
    rep_talk_time_s: float
    client_talk_time_s: float
    rep_talk_ratio: float           # 0.0–1.0
    rep_speech_rate_wpm: float
    client_speech_rate_wpm: float
    rep_word_count: int
    client_word_count: int
    interruptions_by_rep: int
    interruptions_by_client: int
    avg_rep_pause_before_response_s: float
    utterances: list[DiarizedUtterance]

    def to_redis_json(self) -> str:
        """Serialize без utterances (они хранятся отдельно)."""

    @classmethod
    def from_redis_json(cls, data: str) -> "CallAnalytics":
        """Deserialize (utterances будет пустой list)."""


class PostCallProcessor:
    MIN_DURATION_S = 5.0
    INTERRUPTION_THRESHOLD_MS = 300
    MAX_PAUSE_FOR_RESPONSE_MS = 10_000

    def __init__(
        self,
        recognizer: YandexAsyncRecognizer,
        redis: Any,
        session_id: str,
    ) -> None: ...

    async def process(self, audio_buffer: AudioBuffer) -> CallAnalytics | None:
        """
        1. Guard: duration < 5s → return None
        2. Guard: buffer.exceeds_limit() → return None (log warning)
        3. Build WAV per channel
        4. asyncio.gather(recognize(rep_wav), recognize(client_wav))
        5. Compensate timestamp offset (audio_buffer.start_offset_ms())
        6. Merge utterances by start_ms → sorted timeline
        7. Compute CallAnalytics from timings + SpeechStats
        8. Redis: атомарная замена eval_transcript:{session_id}:
           pipe = redis.pipeline()
           pipe.delete(eval_key)
           pipe.rpush(eval_key, *diarized_utterances)
           pipe.expire(eval_key, 86400)
           pipe.set(analytics_key, analytics_json, ex=86400)
           await pipe.execute()
        # Если pipeline fails — eval_transcript остаётся real-time (safe fallback)
        10. Return CallAnalytics
        """

    def _merge(
        self,
        rep: AsyncRecognitionResult,
        client: AsyncRecognitionResult,
        offset_ms: int,
    ) -> list[DiarizedUtterance]:
        """Merge two channel results into time-sorted timeline.
        offset_ms compensates for channel start time difference."""

    def _compute_analytics(
        self,
        utterances: list[DiarizedUtterance],
    ) -> CallAnalytics:
        """Compute all metrics from utterance timings.
        talk_time = sum(end_ms - start_ms) per speaker
        word_count = sum(len(text.split())) per speaker
        speech_rate = word_count / talk_time_min
        """

    def _count_interruptions(
        self,
        utterances: list[DiarizedUtterance],
    ) -> tuple[int, int]:
        """Count overlapping utterances between speakers.
        Overlap > 300ms = interruption. Speaker who started later = interrupter."""

    def _avg_pause_before_response(
        self,
        utterances: list[DiarizedUtterance],
    ) -> float:
        """Average gap between client utterance end and next rep utterance start.
        Gaps > 10s excluded (topic change, not response pause)."""
```

## 6. Интеграция с evaluator (FEAT-004)

### 6.1 Изменённый контракт evaluator

```python
# backend/pipeline/evaluator.py

async def evaluate_call(
    self,
    transcript: list[dict],
    config: EvaluationConfig,
    briefing: str,
    analytics: CallAnalytics | None = None,  # NEW
) -> CallEvaluation:
```

`analytics=None` → промпт без секции АНАЛИТИКА ЗВОНКА (поведение как раньше).

### 6.2 Формат diarized транскрипта в промпте

Если utterances содержат `start_ms` (diarized):

```
[00:12] Менеджер: Добрый день, Иван Петрович! Меня зовут Алексей, компания...
[00:28] Клиент: Здравствуйте, да, слушаю вас.
[01:05] Менеджер: Расскажите, какие задачи сейчас стоят перед вашей командой?
[01:15] Клиент: Ну, у нас основная проблема — это...
```

Если нет `start_ms` (fallback, real-time):

```
Менеджер: Добрый день, Иван Петрович!
Клиент: Здравствуйте, да, слушаю вас.
```

### 6.3 Секция АНАЛИТИКА ЗВОНКА в промпте

Добавляется между `{briefing}` и `{criteria_list}` если `analytics is not None`:

```
АНАЛИТИКА ЗВОНКА (объективные данные, используй для оценки):
- Длительность: {total_duration_s:.0f} сек ({total_duration_s/60:.1f} мин)
- Менеджер говорил: {rep_talk_time_s:.0f} сек ({rep_talk_ratio*100:.0f}%)
- Клиент говорил: {client_talk_time_s:.0f} сек ({(1-rep_talk_ratio)*100:.0f}%)
- Темп речи менеджера: {rep_speech_rate_wpm:.0f} слов/мин
- Темп речи клиента: {client_speech_rate_wpm:.0f} слов/мин
- Перебивания менеджером: {interruptions_by_rep}
- Перебивания клиентом: {interruptions_by_client}
- Средняя пауза менеджера перед ответом: {avg_rep_pause_before_response_s:.1f} сек
- Слов менеджера: {rep_word_count}, клиента: {client_word_count}
```

### 6.4 Дополнение system prompt evaluator

Добавить в конец существующего system prompt из FEAT-004:

```
Если предоставлена секция АНАЛИТИКА ЗВОНКА:
- Используй объективные данные (talk ratio, speech rate, паузы) вместо угадывания.
- Talk ratio 43/57 (менеджер/клиент) — эталон. Отклонение >15% — снижай оценку needs_discovery.
- Темп речи 120-160 слов/мин — норма. <100 = слишком медленно, >180 = слишком быстро.
- Пауза менеджера перед ответом на возражение >1 сек — хорошо. <0.5 сек — плохо (не выслушал).
- Перебивания менеджером >3 — снижай оценку communication.
- Если аналитика отсутствует — оценивай как раньше, только по тексту.
```

### 6.5 Полный user prompt template (обновлённый)

```
ТРАНСКРИПТ ЗВОНКА:
{transcript}

БРИФИНГ (подготовка к звонку):
{briefing}

{analytics_section}

КРИТЕРИИ ОЦЕНКИ:
{criteria_list}

Оцени звонок по каждому критерию. Ответ — ТОЛЬКО валидный JSON по схеме CallEvaluation.
```

### 6.6 Функции форматирования (prompt_formatter.py)

```python
def format_diarized_transcript(utterances: list[dict]) -> str:
    """Транскрипт с таймкодами: [MM:SS] Спикер: текст"""

def format_plain_transcript(utterances: list[dict]) -> str:
    """Плоский транскрипт без таймкодов: Спикер: текст"""

def format_analytics(analytics: CallAnalytics) -> str:
    """Секция АНАЛИТИКА ЗВОНКА для промпта evaluator."""

def _ms_to_timestamp(ms: int) -> str:
    """12400 → '00:12' (truncation, не rounding)"""
```

### 6.7 Изменения в evaluator.py

```python
# Обновлённая сигнатура
async def evaluate_call(
    self,
    transcript: list[dict],
    config: EvaluationConfig,
    briefing: str,
    analytics: CallAnalytics | None = None,  # NEW
) -> CallEvaluation:
    # ...
    # Форматирование транскрипта
    if transcript and transcript[0].get("start_ms") is not None:
        formatted_transcript = format_diarized_transcript(transcript)
    else:
        formatted_transcript = format_plain_transcript(transcript)

    # Форматирование аналитики
    analytics_section = format_analytics(analytics) if analytics else ""

    # Подстановка в промпт — analytics_section между briefing и criteria
    user_prompt = _USER_TEMPLATE.format(
        transcript=formatted_transcript,
        briefing=briefing,
        analytics_section=analytics_section,
        criteria_list=criteria_text,
    )
    # ... остальная логика без изменений
```

`_USER_TEMPLATE` обновляется: добавляется `{analytics_section}` placeholder. Если analytics=None → пустая строка, промпт как раньше.

## 7. Proto-файлы

### 7.1 Что нужно добавить

Текущие proto в `backend/pipeline/yandexstt/` содержат только streaming API. Нужно добавить:

**AsyncRecognizer service:**
```protobuf
service AsyncRecognizer {
  rpc RecognizeFile(RecognizeFileRequest) returns (google.longrunning.Operation);
  rpc GetRecognition(GetRecognitionRequest) returns (google.longrunning.Operation);
}
```

**RecognizeFileRequest:**
```protobuf
message RecognizeFileRequest {
  oneof audio_source {
    bytes content = 1;
    string uri = 2;
  }
  RecognitionModelOptions recognition_model = 3;
  // SpeechAnalysisOptions speech_analysis = 5;  // НЕ используем — метрики из таймкодов
}
```

### 7.2 Подход к обновлению

Регенерировать из `yandex-cloud/cloudapi` repo:

```bash
git clone https://github.com/yandex-cloud/cloudapi
cd cloudapi
pip install grpcio-tools
python3 -m grpc_tools.protoc -I . -I third_party/googleapis \
  --python_out=backend/pipeline/yandexstt/ \
  --grpc_python_out=backend/pipeline/yandexstt/ \
  yandex/cloud/ai/stt/v3/stt_service.proto \
  yandex/cloud/ai/stt/v3/stt.proto
```

Streaming client (`YandexSpeechKitSTT`) использует те же proto — обратная совместимость сохраняется.

### 7.3a Что НЕ используем из proto

- `SpeakerLabelingOptions` — не нужен (каналы разделены аппаратно)
- `SpeechAnalysisOptions.enable_conversation_analysis` — не работает на раздельных каналах
- `SummarizationOptions` — вне scope демо
- `RecognizeFileRequest.uri` — для демо используем content upload

### 7.3 Полный список proto-файлов для генерации

Yandex AsyncRecognizer возвращает `google.longrunning.Operation`, что требует дополнительных proto-зависимостей. Все они есть в `yandex-cloud/cloudapi` repo (включая `third_party/googleapis`):

```
# Основные (Yandex STT v3)
yandex/cloud/ai/stt/v3/stt.proto
yandex/cloud/ai/stt/v3/stt_service.proto

# Yandex Operation (обёртка над google.longrunning)
yandex/cloud/operation/operation.proto

# Google зависимости (из third_party/googleapis)
google/longrunning/operations.proto
google/protobuf/any.proto
google/protobuf/duration.proto
google/protobuf/timestamp.proto
google/rpc/status.proto
google/api/annotations.proto
google/api/http.proto
```

### 7.4 Миграция proto без поломки streaming STT

Проблема: текущие proto в `backend/pipeline/yandexstt/` используют `package speechkit.stt.v3;`, а upstream cloudapi использует `package yandex.cloud.ai.stt.v3;`. Регенерация сломает import paths в `YandexSpeechKitSTT`.

Решение: **раздельные директории**:
- `backend/pipeline/yandexstt/` — **не трогаем**, streaming STT работает как раньше
- `backend/pipeline/yandexstt_async/` — **новая**, сгенерированная из cloudapi для AsyncRecognizer

```bash
# Генерация async proto (в отдельную директорию)
git clone https://github.com/yandex-cloud/cloudapi /tmp/cloudapi
cd /tmp/cloudapi
python3 -m grpc_tools.protoc -I . -I third_party/googleapis \
  --python_out=backend/pipeline/yandexstt_async/ \
  --grpc_python_out=backend/pipeline/yandexstt_async/ \
  yandex/cloud/ai/stt/v3/stt_service.proto \
  yandex/cloud/ai/stt/v3/stt.proto \
  yandex/cloud/operation/operation.proto \
  google/longrunning/operations.proto \
  google/api/http.proto \
  google/api/annotations.proto
```

Imports в `yandex_async.py`:
```python
from backend.pipeline.yandexstt_async.yandex.cloud.ai.stt.v3 import (
    stt_pb2 as async_stt_pb2,
    stt_service_pb2_grpc as async_stt_service_pb2_grpc,
)
```

Streaming STT (`stt.py`) — **без изменений**, продолжает использовать `backend.pipeline.yandexstt`.

## 8. Redis-хранение

| Ключ | Тип | TTL | Изменение |
|------|-----|-----|-----------|
| `eval_transcript:{session_id}` | List | 24h | **Перезаписывается** diarized utterances (с start_ms/end_ms) |
| `eval_analytics:{session_id}` | String (JSON) | 24h | **НОВЫЙ** — метрики CallAnalytics (без utterances) |
| `eval_config:default` | JSON | — | Без изменений (FEAT-004) |
| `eval:{session_id}` | JSON | 24h | Без изменений (FEAT-004) |
| `eval_token:{session_id}` | String | 24h | Без изменений (FEAT-004) |

### Формат diarized utterance в Redis

```json
{"speaker": "rep", "text": "Добрый день...", "start_ms": 12400, "end_ms": 26800}
```

vs текущий real-time формат:

```json
{"speaker": "rep", "text": "Добрый день..."}
```

Evaluator определяет формат по наличию `start_ms` в первом элементе.

### Формат eval_analytics в Redis

```json
{
  "total_duration_s": 754.0,
  "rep_talk_time_s": 324.0,
  "client_talk_time_s": 430.0,
  "rep_talk_ratio": 0.43,
  "rep_speech_rate_wpm": 142.0,
  "client_speech_rate_wpm": 118.0,
  "rep_word_count": 768,
  "client_word_count": 847,
  "interruptions_by_rep": 2,
  "interruptions_by_client": 1,
  "avg_rep_pause_before_response_s": 1.8
}
```

## 9. Конфигурация

### backend/config.py — новые поля

```python
class Settings(BaseSettings):
    # ... existing fields ...

    # Post-call diarization
    enable_post_call_diarization: bool = False   # opt-in для демо
    yandex_speechkit_api_key: str = ""           # уже существует
```

Обновить `.env.example`:
```
# Post-call diarization (opt-in)
ENABLE_POST_CALL_DIARIZATION=false
```

Diarization запускается только если:
1. `enable_post_call_diarization = True`
2. `yandex_speechkit_api_key` не пустой
3. Длительность звонка >= 5 секунд
4. Буфер не превышает 50 MB per channel

## 10. Edge cases и обработка ошибок

### 10.1 Diarization edge cases

| Ситуация | Поведение |
|----------|-----------|
| Звонок < 5 секунд | Skip diarization |
| Один канал пустой (клиент молчал) | Recognize только непустой канал, analytics с нулевыми метриками для пустого |
| Yandex API key не настроен | Skip diarization (log info) |
| enable_post_call_diarization = False | Skip diarization |
| Буфер > 50 MB per channel (> ~26 мин) | Skip diarization (log warning) |
| gRPC RecognizeFile error | Skip diarization, evaluator на real-time данных |
| Polling timeout (> ~55s по backoff) | Skip diarization |
| Yandex вернул 0 utterances для одного/обоих каналов | Diarization считается неуспешной, evaluator на real-time данных |
| Один канал recognize OK, другой failed | Diarization считается неуспешной целиком (для демо — не смешиваем форматы) |
| Процесс убит во время буферизации | Аудио потеряно, evaluator на real-time данных |
| Два session_end подряд | `_evaluation_started` guard (idempotency, FEAT-004) |
| Redis недоступен при записи analytics | Log error, evaluator без analytics |

### 10.2 Алгоритм вычисления interruptions

```
Для каждого utterance U_i, U_j где U_i.speaker != U_j.speaker:
  overlap_ms = min(U_i.end_ms, U_j.end_ms) - max(U_i.start_ms, U_j.start_ms)
  if overlap_ms > 300ms:  # порог — исключить артефакты STT
    Кто начал позже = тот перебил
```

Порог 300ms: ниже — скорее всего задержка STT, а не реальное перебивание.

### 10.3 Алгоритм avg_pause_before_response

```
Для каждой пары (client utterance C, следующий rep utterance R по start_ms):
  if R.start_ms > C.end_ms:           # нет overlap
    pause_ms = R.start_ms - C.end_ms
    if pause_ms < 10_000:              # > 10s — смена темы, не пауза перед ответом
      pauses.append(pause_ms)

avg_pause = mean(pauses) if pauses else 0.0
```

### 10.4 Timestamp offset compensation

```
offset_ms = audio_buffer.start_offset_ms()
# Положительный = rep начал раньше client
# При merge: client utterances сдвигаются на offset_ms
for u in client_utterances:
    u.start_ms += offset_ms
    u.end_ms += offset_ms
```

### 10.5 Memory guard

```
Max per channel: 50 MB (gRPC content limit)
Max total: 100 MB
16kHz PCM16 = 1.92 MB/мин → max ~26 мин per channel

Guard работает в ДВА этапа:

1. Mid-call (в AudioBuffer.append()):
   if len(self._buffers[channel]) >= 50 * 1024 * 1024:
     return  # молча игнорирует новые чанки, log warning один раз
   # Защита от OOM на длинных звонках

2. Post-call (в PostCallProcessor.process()):
   if audio_buffer.exceeds_limit():
     # Буфер обрезан mid-call → данные неполные
     # Skip diarization, evaluator на real-time данных
     audio_buffer.clear()
     return None
```

### 10.6 Совместимость с FEAT-004

| Сценарий | transcript | analytics | Промпт evaluator |
|----------|-----------|-----------|-------------------|
| Diarization успешна | diarized (start_ms/end_ms) | CallAnalytics | Таймкоды + АНАЛИТИКА ЗВОНКА |
| Diarization упала | real-time (без start_ms) | None | Плоский текст, без аналитики |
| Yandex не настроен | real-time | None | Плоский текст, без аналитики |
| Звонок < 5 сек | real-time | None | Плоский текст, без аналитики |
| Звонок > 26 мин | real-time | None | Плоский текст, без аналитики |
| Один канал failed | real-time (fallback) | None | Плоский текст, без аналитики |

**Partial diarization (один канал OK, другой failed):** для демо упрощаем — считаем diarization неуспешной целиком. Evaluator получает real-time транскрипт без аналитики. Причина: смешивание diarized и real-time utterances создаёт несовместимые форматы (с таймкодами и без), усложняет merge и analytics вычисления без пропорционального выигрыша для демо.

Evaluator **всегда работает**. Diarization — best-effort enrichment.

## 11. Ограничения (для демо)

- Max ~26 мин на канал (gRPC content limit 50 MB)
- In-memory buffer — при crash аудио потеряно
- Нет сохранения аудио после обработки
- Yandex async polling может занять до 55s на длинных файлах
- Все метрики (talk time, speech rate, interruptions, pauses) вычисляются из таймкодов utterances — точность зависит от качества STT timestamps
- Фича opt-in (`enable_post_call_diarization = False` по умолчанию)
- Нет UI для аналитики — данные видны только в evaluator отчёте
