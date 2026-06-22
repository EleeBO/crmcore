# Архитектура crmcore

> Краткое оглавление слоёв, функций и файлов.

---

## Backend (Python/FastAPI)

```
backend/
├── main.py              # FastAPI app, REST endpoints, WS handler
├── config.py            # Settings (pydantic-settings)
├── logger.py            # Loguru setup
├── errors.py            # Error classes
│
├── pipeline/            # Real-time processing
│   ├── orchestrator.py  # PipelineOrchestrator — STT→LLM→hints
│   ├── stt.py           # STTClient, SaluteSpeechSTT, DeepgramSTT
│   ├── vad.py           # SileroVAD
│   ├── llm.py           # LLMClient (OpenRouter)
│   ├── audio.py         # parse_frame, deinterleave_stereo
│   ├── scenario.py      # Scenario, generate_scenario
│   └── salutespeech/    # gRPC protobuf (generated)
│
├── session/
│   └── manager.py       # SessionManager — Redis utterances
│
├── ingestion/
│   ├── parser.py        # parse_pdf, parse_excel, parse_docx
│   └── chunker.py       # chunk_text, chunk_table
│
├── briefing/
│   └── portrait.py      # generate_briefing
│
├── summarize/
│   └── call_summary.py  # generate_summary
│
├── certs/
│   └── russian_trusted_root_ca.pem  # SaluteSpeech SSL
│
└── tests/               # pytest tests
```

### API Endpoints

| Method | Path | Описание |
|--------|------|----------|
| `GET` | `/api/v1/health` | Health check (Redis) |
| `GET` | `/api/v1/preflight` | External services check |
| `POST` | `/api/v1/upload` | Knowledge base upload |
| `POST` | `/api/v1/briefing` | Pre-call briefing |
| `POST` | `/api/v1/summarize` | Post-call summary |
| `DELETE` | `/api/v1/session/{id}` | Session cleanup |
| `WS` | `/ws` | Real-time audio streaming |

---

## Extension (TypeScript/Chrome MV3)

```
extension/src/
├── background/
│   └── service-worker.ts  # Tab capture, offscreen lifecycle, badge
│
├── offscreen/
│   ├── offscreen.html
│   └── offscreen.ts       # Audio capture, WsClient, mixing
│
├── sidepanel/
│   ├── sidepanel.html
│   └── sidepanel.ts       # UI phases (0-4), upload, hints, transcripts
│
├── permissions/
│   ├── permissions.html
│   └── permissions.ts     # Mic permission request
│
├── lib/
│   └── ws-client.ts       # WsClient — binary frames, reconnect
│
├── shared/
│   ├── constants.ts       # URLs, config
│   ├── types.ts           # HintPayload, SearchResult, AudioFrame
│   └── messages.ts        # WsMessage, ExtMessage types
│
└── audio-worklet.ts       # Float32→Int16, interleaving, RMS
```

### UI Phases (Sidepanel)

| Phase | Состояние |
|-------|-----------|
| 0 | IDLE — начальный |
| 1 | UPLOAD — загрузка KB |
| 2 | BRIEFING — подготовка |
| 3 | LISTENING — запись звонка |
| 4 | SUMMARY — итоги |

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ EXTENSION                                                           │
│                                                                     │
│  Sidepanel ──► ServiceWorker ──► Offscreen ──► AudioWorklet        │
│      │              │                │              │              │
│      │         tabCapture        mic+tab        PCM16             │
│      │              │                │              │              │
│      │              └────────────────┴──────────────┘              │
│      │                        │                                    │
│      │                   WsClient                                  │
│      │                        │                                    │
└──────┼────────────────────────┼────────────────────────────────────┘
       │                        │ WebSocket (binary frames)
       │                        ▼
┌──────┼─────────────────────────────────────────────────────────────┐
│      │   BACKEND                                                    │
│      │                                                              │
│      │   main.py (WS handler)                                       │
│      │        │                                                     │
│      │        ▼                                                     │
│      │   parse_frame() → deinterleave_stereo()                     │
│      │        │                                                     │
│      │        ├────► VAD (speech detection)                        │
│      │        │                                                     │
│      │        └────► STT (per channel)                             │
│      │                  │                                          │
│      ◄──────────────────┴── Transcript messages                   │
│      │                                                              │
│      │   PipelineOrchestrator                                       │
│      │        │                                                     │
│      │        ▼                                                     │
│      │   LLM → hint_start/chunk/end                                │
│      │        │                                                     │
│      ◄────────┴── Hint messages                                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### WebSocket Protocol

**Binary Frame:**
```
[0-3] uint32 LE: sequence
[4]   uint8:  channel (0=audio, 1=control)
[5+]  payload
```

**Control → Backend:**
- `session_start`, `session_end`

**Backend → Control:**
- `transcript`, `hint_start`, `hint_chunk`, `hint_end`, `error`

---

## Тестирование

| Скрипт | Назначение |
|--------|------------|
| `backend/tests/test_salutespeech_synthetic.py` | SaluteSpeech без микрофона |
| `backend/tests/test_salutespeech_mic.py` | SaluteSpeech с микрофоном |

```bash
# Запуск тестов
PYTHONPATH=. .venv/bin/python backend/tests/test_salutespeech_synthetic.py --tts --timing
```

---

## Документация

| Файл | Описание |
|------|----------|
| `docs/ARCHITECTURE.md` | Эта страница |
| `docs/SALUTESPEECH_TESTING.md` | SaluteSpeech тестирование |
| `specs/` | Спецификации фич |
