# SaluteSpeech STT — Тестирование и документация

> Обновлено: 2026-03-09

## Обзор

SaluteSpeech — российский сервис распознавания речи от Сбер, используемый как основной STT провайдер в проекте.

### Технические детали

| Параметр | Значение |
|----------|----------|
| **gRPC Host** | `smartspeech.sber.ru:443` |
| **Token URL** | `https://ngw.devices.sberbank.ru:9443/api/v2/oauth` |
| **Audio Format** | PCM S16LE (16-bit signed little-endian) |
| **Sample Rate** | 16000 Hz |
| **Channels** | Mono |
| **Chunk Size** | max 4 MB, max 2 сек на чанк |
| **Chunk Interval** | max 5 сек между чанками |

### Аутентификация

1. **OAuth Token** — получается по Basic Auth с API ключом
2. **Token TTL** — 30 минут
3. **Token передаётся** как Bearer в gRPC metadata

## Результаты тестирования

### Замеры скорости (2026-03-09, Москва)

```
Audio duration: 3.23s
Total time: 2.51s
RTF (Real-Time Factor): 0.78x

First partial result: 83ms
Subsequent partials: 50-100ms apart
Final result: 437ms after first chunk
```

### Латентность

| Метрика | Значение |
|---------|----------|
| **Первый partial** | ~80-100ms |
| **Между partials** | ~50-100ms |
| **Final result** | ~400-500ms (для 3с аудио) |
| **RTF** | ~0.78x (быстрее реального времени) |

### Качество распознавания

- **Русский язык**: Отличное
- **Тестовая фраза**: "Привет, это тест распознавания речи от Салют Спич"
- **Результат**: "привет это тест распознавание речи от салют speech"
- **Точность**: ~95% (небольшие отличия в окончаниях)

## Тестовый скрипт

### Расположение

```
backend/tests/test_salutespeech_synthetic.py
```

### Использование

```bash
# Проверка подключения (без аудио)
PYTHONPATH=. .venv/bin/python backend/tests/test_salutespeech_synthetic.py --connect-only

# С синтезированным голосом (macOS TTS)
PYTHONPATH=. .venv/bin/python backend/tests/test_salutespeech_synthetic.py --tts

# С анализом скорости
PYTHONPATH=. .venv/bin/python backend/tests/test_salutespeech_synthetic.py --tts --timing

# Из WAV/AIFF файла
PYTHONPATH=. .venv/bin/python backend/tests/test_salutespeech_synthetic.py --file audio.wav

# Свой текст для TTS
PYTHONPATH=. .venv/bin/python backend/tests/test_salutespeech_synthetic.py --tts --text "Добрый день"
```

### Пример вывода

```
============================================================
SaluteSpeech Streaming Test
============================================================
Provider: salutespeech
Scope: SALUTE_SPEECH_PERS
API Key: ***g4ZQ==

[1/2] Testing connection...
  Getting OAuth token...
  Token acquired, expires at 1773088057.902
  Connecting to smartspeech.sber.ru:443...
  Channel ready!
OK: Connection successful

[2/2] Generating audio...
  Using macOS TTS: 'Привет, это тест распознавания речи от Салют Спич'
  Input: (71194,), 22050Hz, 71194 samples
  Resampled to 16000Hz, 51660 samples
  Audio: 103320 bytes, 3.23s

[3/3] Sending to SaluteSpeech...
  Connecting to smartspeech.sber.ru:443...
  Starting recognition stream...
    [partial]  [    83ms] 'привет'
    [partial]  [   317ms] 'привет это тест'
    [partial]  [   337ms] 'привет это тест распознавания'
  Sent 17/17 audio chunks
    [partial]  [   363ms] 'привет это тест распознавания речи абсолют'
    [partial]  [   412ms] 'привет это тест распознавания речи от салют speech'
    [FINAL]  [   437ms] 'привет это тест распознавание речи от салют speech'

  TIMING ANALYSIS:
    Audio duration: 3.23s
    Total time: 2.51s
    RTF (Real-Time Factor): 0.78x
    First response: 83ms
    Final result: 437ms

============================================================
SUCCESS: SaluteSpeech streaming recognition works!
============================================================
```

## Архитектура стриминга

```
┌─────────────────┐      1. OAuth Token       ┌────────────────────────┐
│   Backend/      │ ──────────────────────►   │ ngw.devices.sberbank   │
│   Test Script   │      Basic Auth           │ :9443/api/v2/oauth     │
└────────┬────────┘                           └────────────────────────┘
         │
         │ 2. gRPC Bidirectional Stream (Bearer token)
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     smartspeech.sber.ru:443                         │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  Recognize() — bidirectional streaming RPC                    │ │
│  │                                                               │ │
│  │  CLIENT → SERVER:                                             │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │ 1. RecognitionRequest(options)                          │  │ │
│  │  │    - audio_encoding: PCM_S16LE                          │  │ │
│  │  │    - sample_rate: 16000                                 │  │ │
│  │  │    - language: ru-RU                                    │  │ │
│  │  │    - enable_partial_results: true                       │  │ │
│  │  │    - enable_multi_utterance: true                       │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  │                                                               │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │ 2. RecognitionRequest(audio_chunk) × N                  │  │ │
│  │  │    - bytes: PCM audio data                              │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  │                                                               │ │
│  │  SERVER → CLIENT:                                             │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │ RecognitionResponse (streaming)                         │  │ │
│  │  │   - results[].text: распознанный текст                  │  │ │
│  │  │   - eou: bool (End of Utterance = final)                │  │ │
│  │  │   - eou_reason: ORGANIC | NO_SPEECH_TIMEOUT | ...       │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Интеграция в проекте

### Файлы

| Файл | Описание |
|------|----------|
| `backend/pipeline/stt.py` | Абстракция STTClient + реализация SaluteSpeechSTT |
| `backend/pipeline/salutespeech/` | Сгенерированные protobuf файлы |
| `backend/certs/russian_trusted_root_ca.pem` | SSL сертификат для gRPC |
| `backend/tests/test_salutespeech_synthetic.py` | Тестовый скрипт |
| `backend/tests/test_salutespeech_mic.py` | Тест с микрофоном |

### Конфигурация (.env)

```bash
STT_PROVIDER=salutespeech
SBER_SPEECH_API_KEY=<Base64 client_id:client_secret>
SBER_SPEECH_SCOPE=SALUTE_SPEECH_PERS  # или SALUTE_SPEECH_CORP
```

### Использование в коде

```python
from backend.pipeline.stt import SaluteSpeechSTT, Transcript

stt = SaluteSpeechSTT(
    api_key=settings.sber_speech_api_key,
    scope=settings.sber_speech_scope,
)

async def on_transcript(t: Transcript) -> None:
    print(f"[{'FINAL' if t.is_final else 'partial'}] {t.speaker}: {t.text}")

stt.on_transcript = on_transcript
await stt.start_session("session-123")
await stt.send_audio(pcm_chunk, "client")
# ...
await stt.close()
```

## Troubleshooting

### Ошибка: UNAUTHENTICATED

- Проверьте `SBER_SPEECH_API_KEY` в `.env`
- Токен истекает через 30 минут — реализуйте refresh

### Ошибка: SSL certificate verify failed

- Установите Russian Trusted Root CA: `backend/certs/russian_trusted_root_ca.pem`
- Или добавьте в системное хранилище сертификатов

### Нет результатов распознавания

- Проверьте формат аудио: PCM S16LE, 16kHz, mono
- Проверьте уровень звука (RMS)
- Проверьте язык: `language="ru-RU"`

## Ссылки

- [Официальная документация SaluteSpeech](https://developers.sber.ru/docs/ru/salutespeech/api/grpc/recognition-stream-2)
- [SmartMarket документация](https://developers.sber.ru/docs/ru/smartspeech/recognition-stream)
