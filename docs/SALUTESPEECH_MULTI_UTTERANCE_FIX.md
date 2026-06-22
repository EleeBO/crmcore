# Fix: enable_multi_utterance для SaluteSpeech

> Дата: 2026-03-10
> Severity: HIGH
> Status: FIXED

---

## Проблема

Production код `backend/pipeline/stt.py` НЕ устанавливает флаг `enable_multi_utterance=True` в RecognitionOptions, тогда как тестовый скрипт устанавливает.

---

## Почему это критично

### SaluteSpeech gRPC API поведение:

| `enable_multi_utterance` | Поведение сервера |
|--------------------------|-------------------|
| `false` (default) | Сервер закрывает поток после **первой** фразы (EOU = End of Utterance). Для продолжения требуется реконнект. |
| `true` | Сервер продолжает слушать после EOU, отправляя multiple final results в одном потоке. |

### Реальный сценарий звонка:

```
Без enable_multi_utterance=True:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Client: "Здравствуйте, меня зовут Иван"
        ↓
Server: [transcript final] → EOU → ЗАКРЫВАЕТ ПОТОК
        ↓
[Аудио теряется до реконнекта]
        ↓
Client: "хочу узнать о вашем продукте"  ← ПОТЕРЯНО!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

С enable_multi_utterance=True:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Client: "Здравствуйте, меня зовут Иван"
        ↓
Server: [transcript final] → EOU → ПРОДОЛЖАЕТ СЛУШАТЬ
        ↓
Client: "хочу узнать о вашем продукте"
        ↓
Server: [transcript final] → EOU → ПРОДОЛЖАЕТ СЛУШАТЬ
        ↓
... и так далее до конца звонка
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Документация SaluteSpeech

> **enable_multi_utterance** (boolean)
> Распознавание либо одного, либо нескольких предложений.
> Возможные значения: `true` и `false`.
> Значение по умолчанию — `false`
>
> В режиме `enable_multi_utterance=true` распознавание речи не останавливается с окончанием очередного предложения...

Источник: https://developers.sber.ru/docs/ru/salutespeech/api/grpc/recognition-stream-2

---

## Сравнение кода

### До (stt.py:274-281):

```python
yield recognition_pb2.RecognitionRequest(
    options=recognition_pb2.RecognitionOptions(
        audio_encoding=recognition_pb2.RecognitionOptions.PCM_S16LE,
        sample_rate=16000,
        language="ru-RU",
        enable_partial_results=True,
        no_speech_timeout=_nst,
    )
)
```

### После:

```python
yield recognition_pb2.RecognitionRequest(
    options=recognition_pb2.RecognitionOptions(
        audio_encoding=recognition_pb2.RecognitionOptions.PCM_S16LE,
        sample_rate=16000,
        language="ru-RU",
        enable_partial_results=True,
        enable_multi_utterance=True,  # ← ДОБАВЛЕНО
        no_speech_timeout=_nst,
    )
)
```

---

## Тестирование

После исправления запустить:

```bash
PYTHONPATH=. .venv/bin/python backend/tests/test_salutespeech_synthetic.py --tts --timing
```

Ожидаемый результат: несколько final transcripts в одном потоке без реконнектов.

---

## Файл исправлен

- `backend/pipeline/stt.py:274-281`
