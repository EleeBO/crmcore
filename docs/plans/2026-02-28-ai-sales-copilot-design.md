# AI Sales Copilot — Design Document

**Date:** 2026-02-28
**Status:** DRAFT
**Based on:** `AI_Sales_Copilot_PRD.md` v1.0

---

## 1. Scope & Decisions

### 1.1 What We're Building

MVP Chrome Extension + FastAPI backend for real-time sales assistance during SIP calls. Demo-ready for SberCRM leadership.

### 1.2 Key Decisions (from PRD review)

| # | Decision | Chosen Option | Rationale |
|---|----------|---------------|-----------|
| D1 | WebSocket owner | Offscreen Document | SW killed after 5min idle; Offscreen Doc stays alive during audio capture |
| D2 | Transport | Native WebSocket (binary frames) | Socket.IO incompatible with MV3 SW, +45KB overhead, long-polling breaks audio |
| D3 | Upload→Session binding | `knowledge_base_id` UUID | Upload returns KB ID, session_start includes it |
| D4 | VAD runtime | Silero VAD v5 ONNX | 40MB vs 800MB PyTorch, no event loop blocking |
| D5 | Audio frame format | Binary WebSocket | 33% less overhead than base64 JSON |
| D6 | RAG trigger | Deepgram `final` + `endpointing=300ms` | Balance of accuracy and latency |
| D7 | UI language | Russian | Target audience is Sber leadership |
| D8 | LLM prompt language | Russian | Better hint quality in target language |
| D9 | Embedding model | `multilingual-e5-base` | Good Russian support, 384d vectors |
| D10 | LLM provider | OpenRouter (single API) | One SDK, one key, easy model switching |
| D11 | Primary LLM | Gemini 2.5 Flash | ~150-300ms TTFT, cheap, good Russian |
| D12 | Fallback LLM | GPT-4.1-mini | ~300ms, reliable JSON mode |
| D13 | Follow-up email | Button "Summarize Call" (+1 day) | Compromise: not full feature, but demo moment |
| D14 | Script Compliance | CUT from MVP | Phase 2 |
| D15 | Demo fallback STT | None | Trust Deepgram; no pre-recorded transcripts |
| D16 | SIP page detection | Configurable URL pattern | User sets Mizugate URL in popup settings |
| D17 | Demo environment | Localhost | Single laptop, no network risks |
| D18 | Build pipeline | Vite + vite-plugin-web-extension + TypeScript | HMR, MV3 support, modern tooling |

### 1.3 Cut from Scope

- Script Compliance Check (Phase 2)
- Demo-mode with pre-recorded transcripts
- Authentication
- Multi-tenancy
- Call recording/playback

### 1.4 Added to Scope (vs original PRD)

- "Summarize Call" button for follow-up email generation
- Phase 2 Roadmap slide for Q&A
- Demo Pre-Flight Checklist
- Configurable SIP page URL pattern

---

## 2. Architecture

### 2.1 System Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  Chrome Extension (MV3)                   │
│                                                           │
│  ┌──────────┐    ┌────────────────────┐   ┌───────────┐  │
│  │ Popup    │    │  Offscreen Document │   │ Content   │  │
│  │          │    │                     │   │ Script    │  │
│  │ - Upload │    │ - getUserMedia(mic) │   │           │  │
│  │ - Brief  │    │ - getUserMedia(tab) │   │ - Shadow  │  │
│  │ - Config │    │ - Web Audio API     │   │   DOM     │  │
│  │ - Perms  │    │ - Stereo mix        │   │   Widget  │  │
│  │   grant  │    │ - AudioWorklet PCM  │   │ - State   │  │
│  │          │    │ - Native WebSocket  │   │   Machine │  │
│  └────┬─────┘    └─────────┬──────────┘   └─────┬─────┘  │
│       │                    │                     │        │
│       └────────┐    ┌──────┘    ┌────────────────┘        │
│                ▼    ▼           ▼                          │
│          ┌───────────────────────────┐                    │
│          │     Service Worker        │                    │
│          │  - tabCapture.getMediaStreamId()               │
│          │  - chrome.alarms keepalive │                    │
│          │  - Message routing (ports) │                    │
│          │  - chrome.storage state    │                    │
│          └───────────────────────────┘                    │
└───────────────────────────┬───────────────────────────────┘
                            │
                 Native WebSocket (binary frames)
                 5-byte header + PCM16 payload
                            │
                            ▼
┌───────────────────────────────────────────────────────────┐
│              FastAPI Backend (Python 3.11+)                │
│                                                            │
│  ┌─────────────────── Pipeline ──────────────────────┐    │
│  │                                                    │    │
│  │  Binary   De-inter-   VAD      STT      Session   │    │
│  │  WS ────► leave ────► Silero ► Deepgram ► Manager  │    │
│  │  frames   L+R stereo  ONNX    Nova-3     (Redis)  │    │
│  │                                  │                 │    │
│  │                           ┌──────┘                 │    │
│  │                           ▼ (on is_final)          │    │
│  │                          RAG ──► LLM ──► Hint      │    │
│  │                          Hybrid  Gemini   JSON     │    │
│  │                          Search  Flash    push     │    │
│  │                          (ChromaDB                  │    │
│  │                           + BM25)                   │    │
│  └────────────────────────────────────────────────────┘    │
│                                                            │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐           │
│  │ Redis    │  │ ChromaDB │  │ File Storage  │           │
│  │ Sessions │  │ Vectors  │  │ (local fs)    │           │
│  │ TTL=30m  │  │ + BM25   │  │ uploads/      │           │
│  └──────────┘  └──────────┘  └───────────────┘           │
└───────────────────────────────────────────────────────────┘
```

### 2.2 Audio Capture Flow (Critical Path)

Based on Chrome MV3 best practices (Chrome 116+):

```
1. User clicks "Start Call" in Popup
   │
2. Popup → Service Worker: "start_capture"
   │
3. Service Worker calls chrome.tabCapture.getMediaStreamId({targetTabId})
   │  (requires user gesture from popup click)
   │
4. Service Worker → creates Offscreen Document (if not exists)
   │  reason: "USER_MEDIA", justification: "Audio capture for call"
   │
5. Service Worker → Offscreen Document: {streamId, action: "start"}
   │
6. Offscreen Document:
   │  a) navigator.mediaDevices.getUserMedia({audio: {mandatory: {chromeMediaSource: 'tab', chromeMediaSourceId: streamId}}})
   │     → tabStream (client voice)
   │  b) navigator.mediaDevices.getUserMedia({audio: true})
   │     → micStream (sales rep voice)
   │     NOTE: mic permission must be pre-granted from popup extension page
   │  c) Route tabStream back to AudioContext.destination (so user hears client)
   │  d) Mix into stereo: L=mic, R=tab via ChannelMergerNode
   │  e) AudioWorkletNode encodes Float32 → Int16 PCM
   │  f) Send binary frames via native WebSocket to backend
```

**Key constraints (verified via web research):**

1. **Mic permission:** `getUserMedia({audio: true})` CANNOT prompt for permission in Offscreen Document — prompt silently fails with "Permission dismissed". Workarounds:
   - **Option A (recommended):** Open a visible extension page (tab) on first launch to request mic permission. Once granted, the Offscreen Document can use `getUserMedia` without prompt.
   - **Option B:** Inject invisible iframe via Content Script to request permission on behalf of extension origin.
   - **Option C:** User manually sets "Allow" in Extension > Details > Site Settings > Microphone.
   - We use **Option A**: popup on first launch opens `chrome.tabs.create({url: chrome.runtime.getURL('permissions.html')})` which requests mic, then closes.

2. **tabCapture suppresses audio:** When `tabCapture` captures a tab, the tab's audio stops playing to the user. **Must** route back via `AudioContext.destination`:
   ```js
   const ctx = new AudioContext();
   const source = ctx.createMediaStreamSource(tabStream);
   source.connect(ctx.destination); // user hears client again
   ```
   Store `ctx` reference to prevent garbage collection.

3. **AudioWorklet vs ScriptProcessorNode:**
   - `ScriptProcessorNode` is deprecated, runs on main thread, causes glitches at 48kHz
   - `AudioWorkletNode` runs on dedicated audio thread, fixed 128-sample buffer (~2.7ms at 48kHz)
   - **We use AudioWorklet** with a `PCM16Processor` class:
     - Receives Float32 samples in `process()` method
     - Clamps to [-1, 1], scales to Int16 range (× 32767)
     - Posts Int16Array chunks via `port.postMessage()` with transferable
   - Worklet module loaded via `audioContext.audioWorklet.addModule(chrome.runtime.getURL('audio-worklet.js'))`

4. **Memory management in AudioWorklet:**
   - Allocate output buffer once, reuse per `process()` call
   - Never allocate inside `process()` — GC pauses cause audio glitches
   - 3ms timing budget per audio block at 48kHz

5. **Tab focus loss during call:**
   - If user switches away from Mizugate tab, tab audio may freeze/go silent
   - `tabCapture` stream continues but Chrome throttles background tab rendering
   - Mic capture (getUserMedia) is unaffected by tab focus
   - **Mitigation:** Widget shows warning "Tab не в фокусе — голос клиента может прерваться"

### 2.3 Message Flow Between Extension Components

```
chrome.runtime.connect() ports (persistent, not sendMessage):

Popup ←──port──→ Service Worker ←──port──→ Offscreen Document
                       │
                  ←──port──→ Content Script (Widget)

High-frequency audio: Offscreen Doc → WebSocket (direct, no SW hop)
Hints from backend:   WebSocket → Offscreen Doc → port → SW → port → Content Script
Control messages:     Popup → port → SW → port → Offscreen Doc
```

### 2.4 Pipeline Error Handling

| Stage | On Failure | Behavior |
|-------|-----------|----------|
| VAD | Drop frame | Silent skip, no error to UI |
| STT (Deepgram) | Skip utterance | Widget stays in "Listening", log error |
| RAG | Empty context | LLM receives prompt without RAG results, generates generic hint |
| LLM Primary (Gemini) | Timeout 2s → fallback | Switch to GPT-4.1-mini, add `[fallback]` badge to hint |
| LLM Fallback | Timeout 3s → cached | Return pre-loaded objection response from Redis, `[cached]` badge |
| WebSocket | Disconnect | Widget → "Disconnected" state, auto-reconnect exponential backoff |
| Redis | Unavailable | Pipeline continues without session context, hints will lack history |

### 2.5 Single-Flight LLM Queue

When a new `final` transcript arrives while LLM is in-flight:
1. Cancel the in-flight request
2. Start fresh LLM call with latest context
3. Maximum queue depth: 1

This prevents stale hints and Groq/OpenRouter rate limit issues.

---

## 3. Data Model

### 3.1 ChromaDB Collections

```
Collection: session_{knowledge_base_id}
  Document fields:
    - id: str (chunk UUID)
    - content: str (chunk text)
    - embedding: float[384] (multilingual-e5-base)
    - metadata:
        source_file: str
        page_number: int | null
        section_title: str | null
        chunk_type: "text" | "table" | "list"
        row_range: str | null (for Excel: "15-20")
```

### 3.2 Redis Keys

```
session:{session_id}:kb_id         → str (knowledge_base_id UUID)     TTL: 30min
session:{session_id}:utterances    → list[JSON] (last 10 utterances)  TTL: 30min
session:{session_id}:summary       → str (rolling conversation summary) TTL: 30min
session:{session_id}:portrait      → JSON (buyer portrait)            TTL: 30min
session:{session_id}:strategy      → JSON (negotiation strategy)      TTL: 30min
cache:objections:{kb_id}           → list[JSON] (top 10 objections)   TTL: 1hour
```

### 3.3 BM25 Index

```
File: {CHROMA_PERSIST_DIR}/bm25_{knowledge_base_id}.json
  {
    "corpus": [[tokenized, words, ...], ...],
    "doc_ids": ["chunk_uuid_1", "chunk_uuid_2", ...],
    "metadata": {"created_at": "...", "chunks_count": 42}
  }
```

Rebuilt on each ingestion. Loaded into memory on session start.

---

## 4. API Contracts (Updated)

### 4.1 REST Endpoints

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/v1/upload` | multipart files + `session_id` | `{knowledge_base_id, files_indexed, chunks_count, time_ms}` |
| POST | `/api/v1/briefing` | `{session_id, knowledge_base_id}` | `{portrait, strategy, objections: [{q, a}]}` |
| POST | `/api/v1/summarize` | `{session_id}` | `{summary, key_points, action_items, email_draft}` |
| GET | `/api/v1/health` | — | `{status, redis, chromadb, deepgram, openrouter}` |
| DELETE | `/api/v1/session/{id}` | — | `{status}` (also deletes ChromaDB collection) |

### 4.2 WebSocket Binary Protocol

```
Frame header (5 bytes):
  [0-3] uint32 LE: sequence number
  [4]   uint8:     channel (0=stereo, 1=control)

Audio frame (channel=0):
  header + interleaved PCM16 LE payload
  Left channel (even samples) = mic (sales rep)
  Right channel (odd samples) = tab audio (client)

Control frame (channel=1):
  header + UTF-8 JSON payload
```

### 4.3 WebSocket JSON Events (over control frames)

| Direction | Event | Payload |
|-----------|-------|---------|
| C→S | `session_start` | `{session_id, knowledge_base_id, config: {sip_url}}` |
| C→S | `session_end` | `{session_id}` |
| S→C | `transcript` | `{speaker: "client"\|"rep", text, is_final}` |
| S→C | `hint` | `{text, source, sentiment, coaching, color, warning, fallback_used}` |
| S→C | `error` | `{code: "STT_ERROR"\|"LLM_TIMEOUT"\|"RAG_ERROR"\|..., message}` |
| S→C | `status` | `{state: "listening"\|"processing"\|"reconnecting"}` |

### 4.4 Error Codes

| Code | HTTP/WS | Description |
|------|---------|-------------|
| `UPLOAD_FAILED` | 400 | File parsing error (corrupt, protected, unsupported) |
| `UPLOAD_TOO_LARGE` | 413 | File exceeds 50MB limit |
| `KB_NOT_FOUND` | 404 | Knowledge base ID not found |
| `STT_ERROR` | WS | Deepgram connection/transcription error |
| `LLM_TIMEOUT` | WS | Both primary and fallback LLM timed out |
| `LLM_RATE_LIMIT` | WS | OpenRouter rate limit hit |
| `RAG_ERROR` | WS | ChromaDB or BM25 query failed |
| `SESSION_EXPIRED` | WS | Redis session TTL expired |

---

## 5. Model Stack

| Layer | Model | Provider | Config |
|-------|-------|----------|--------|
| STT | Deepgram Nova-3 | Deepgram API | `language:ru, interim_results:true, endpointing:300, punctuate:true` |
| VAD | Silero VAD v5 | ONNX Runtime (local) | `threshold:0.5, min_speech:250ms` |
| Embedding | `multilingual-e5-base` | Local (sentence-transformers) | 384d, loaded at startup |
| BM25 | `rank_bm25` | Local (Python) | RRF fusion: k=60 |
| LLM Primary | Gemini 2.5 Flash | OpenRouter | `max_tokens:300, temperature:0.3, response_format:json` |
| LLM Fallback | GPT-4.1-mini | OpenRouter | `max_tokens:300, temperature:0.3, response_format:json_object` |

### 5.1 LLM Prompt (Russian)

```
[SYSTEM]
Ты — помощник продавца Sber CIB в реальном времени.
Задача: генерировать КОРОТКУЮ (1–2 предложения) подсказку для продавца.
Правила:
  1) Используй ТОЛЬКО факты из [БАЗА_ЗНАНИЙ].
  2) Указывай источник.
  3) Если нет данных — скажи "Нет данных в базе знаний".
  4) Оцени тон клиента: ПОЗИТИВНЫЙ / НЕЙТРАЛЬНЫЙ / НЕГАТИВНЫЙ.
  5) Если продавец ошибся — отметь как ПРЕДУПРЕЖДЕНИЕ.

[ПОРТРЕТ_КЛИЕНТА] {portrait}
[СТРАТЕГИЯ] {strategy}
[БАЗА_ЗНАНИЙ] {rag_results_with_sources}
[РЕЗЮМЕ_РАЗГОВОРА] {rolling_summary}
[ПОСЛЕДНИЕ_5_РЕПЛИК] {tagged_by_speaker}
[КЛИЕНТ_СКАЗАЛ] {latest_utterance}
```

### 5.2 LLM Output Schema (Pydantic)

```python
class HintResponse(BaseModel):
    hint: str
    source: str  # "file.pdf, стр.12" or "Нет данных"
    sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
    coaching: str | None = None
    warning: str | None = None
    color: Literal["GREEN", "YELLOW", "RED", "BLUE"]
```

---

## 6. Extension Build & Structure

### 6.1 Tooling

- **Bundler:** Vite + `vite-plugin-web-extension`
- **Language:** TypeScript (strict mode)
- **State management:** XState (widget state machine)
- **Package manager:** pnpm

### 6.2 Directory Structure

```
extension/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── manifest.json
├── src/
│   ├── popup/
│   │   ├── popup.html
│   │   ├── popup.ts
│   │   └── popup.css
│   ├── content/
│   │   ├── widget.ts          # Shadow DOM widget
│   │   ├── widget.css         # Scoped styles
│   │   └── state-machine.ts   # XState widget states
│   ├── offscreen/
│   │   ├── offscreen.html
│   │   ├── offscreen.ts       # Audio capture + WebSocket
│   │   └── audio-worklet.ts   # Float32→Int16 PCM encoder
│   ├── background/
│   │   └── service-worker.ts  # Control plane
│   ├── shared/
│   │   ├── types.ts           # Shared interfaces
│   │   ├── messages.ts        # Port message types
│   │   └── constants.ts       # Config, URLs
│   └── lib/
│       └── ws-client.ts       # WebSocket binary framing
└── public/
    └── icons/
```

### 6.3 Widget State Machine

```
States: IDLE → LISTENING → HINT_ACTIVE → WARNING → DISCONNECTED → BRIEFING

Valid transitions:
  IDLE → LISTENING (audio capture started)
  IDLE → BRIEFING ("Prepare" clicked)
  LISTENING → HINT_ACTIVE (hint received)
  LISTENING → WARNING (red hint received)
  LISTENING → DISCONNECTED (WS lost)
  HINT_ACTIVE → LISTENING (3s timeout, new audio detected)
  HINT_ACTIVE → WARNING (red hint received)
  HINT_ACTIVE → DISCONNECTED (WS lost)
  WARNING → LISTENING (5s timeout)
  WARNING → DISCONNECTED (WS lost)
  DISCONNECTED → LISTENING (WS reconnected)
  BRIEFING → IDLE (briefing dismissed)
  BRIEFING → LISTENING (call started from briefing)
  ANY → IDLE (session ended)
```

---

## 7. Backend Structure

```
backend/
├── pyproject.toml
├── Dockerfile
├── main.py                    # FastAPI app, lifespan, WS endpoints
├── config.py                  # Pydantic Settings (env vars)
├── pipeline/
│   ├── orchestrator.py        # Pipeline coordinator, single-flight queue
│   ├── vad.py                 # Silero VAD ONNX wrapper + ThreadPoolExecutor
│   ├── stt.py                 # Deepgram Nova-3 streaming client
│   ├── rag.py                 # Hybrid search: ChromaDB + BM25 + RRF
│   ├── llm.py                 # OpenRouter client (Gemini Flash + GPT-4.1-mini fallback)
│   └── audio.py               # Binary frame parser, stereo de-interleaver
├── ingestion/
│   ├── parser.py              # PDF (PyMuPDF), Excel (openpyxl), DOCX (python-docx)
│   ├── chunker.py             # 512 tokens, 64 overlap, table-aware
│   └── embedder.py            # multilingual-e5-base + ChromaDB + BM25 index
├── briefing/
│   └── portrait.py            # Buyer portrait + strategy generator
├── session/
│   └── manager.py             # Redis session state, rolling summary
├── summarize/
│   └── call_summary.py        # Post-call summary + email draft
└── tests/
    ├── test_rag.py
    ├── test_pipeline.py
    ├── test_latency.py
    ├── test_ingestion.py
    └── fixtures/
```

### 7.1 Environment Variables

| Variable | Example | Required |
|----------|---------|----------|
| `DEEPGRAM_API_KEY` | `dg-xxxx` | Yes |
| `OPENROUTER_API_KEY` | `sk-or-xxxx` | Yes |
| `REDIS_URL` | `redis://localhost:6379` | Yes |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | Yes |
| `LLM_PRIMARY_MODEL` | `google/gemini-2.5-flash` | No (default) |
| `LLM_FALLBACK_MODEL` | `openai/gpt-4.1-mini` | No (default) |
| `LLM_PRIMARY_TIMEOUT_MS` | `2000` | No (default: 2000) |
| `LLM_FALLBACK_TIMEOUT_MS` | `3000` | No (default: 3000) |
| `VAD_THRESHOLD` | `0.5` | No (default: 0.5) |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-base` | No (default) |
| `LOG_LEVEL` | `INFO` | No (default: INFO) |

---

## 8. Latency Budget (Verified with Benchmarks, 2026-02-28)

### Standard Pipeline (wait for final STT → RAG → LLM → full response)
```
Stage                              Best Case    Typical    Source
────────────────────────────────────────────────────────────────────
VAD silence threshold              250 ms       400 ms     Design choice
VAD inference (Silero v5 ONNX)     < 1 ms       < 1 ms     Silero GitHub
STT final (Deepgram Nova-3)       200 ms       500 ms     Deepgram docs
  OR SaluteSpeech gRPC            ???          ???        No public data!
Embedding query (e5-base ONNX Q8) 15 ms        50 ms      Benchmarks
ChromaDB search (500 docs)        3 ms         5 ms       ChromaDB benchmarks
LLM TTFT (Gemini 2.5 Flash/OR)   500 ms       650 ms     Artificial Analysis
LLM generation (50 tok, 248 t/s)  200 ms       250 ms     Artificial Analysis
Network + rendering                20 ms        50 ms      Local WS
────────────────────────────────────────────────────────────────────
TOTAL (Deepgram + Gemini)          ~1190 ms     ~1905 ms   ✅ Within budget
```

### Optimized Pipeline (speculative RAG + streaming LLM)
```
Optimization                       Savings      How
────────────────────────────────────────────────────────────────────
Speculative RAG on interim STT     -200..500ms  Start RAG before speech_final
LLM streaming (show at TTFT)       -200..250ms  Display tokens as they arrive
Pre-warm OpenRouter HTTP/2         -50..100ms   Health check on session_start
ONNX QInt8 embeddings              -30..40ms    Quantized model
────────────────────────────────────────────────────────────────────
TOTAL (optimized)                  ~890 ms      ~1405 ms   ✅ Comfortable
Visual latency (user perception)   ~700 ms      ~1000 ms   ✅ Excellent
```

### Fallback Comparison
```
LLM Model                   TTFT       Output Speed   50-tok Total
────────────────────────────────────────────────────────────────────
Gemini 2.5 Flash / OR       500 ms     248 tok/s      ~700 ms
GPT-4.1-mini / OR           520 ms     64-79 tok/s    ~1150 ms ⚠️
Gemini 2.5 Flash-Lite / OR  250 ms     360 tok/s      ~390 ms  ✅ Best
```

---

## 9. Demo Pre-Flight Checklist

Before the audience enters the room:

- [ ] Extension installed in Chrome (developer mode)
- [ ] Microphone permission granted (via popup first-launch flow)
- [ ] Backend running (`docker compose up` → health check green)
- [ ] Redis and ChromaDB accessible
- [ ] Deepgram API key valid (health endpoint)
- [ ] OpenRouter API key valid (health endpoint)
- [ ] Demo files ready (tariffs PDF, competitors Excel, CRM notes)
- [ ] Mizugate URL configured in extension settings
- [ ] Test upload + test query verified
- [ ] Test call audio capture verified (both channels)
- [ ] Widget renders on Mizugate page without CSS conflicts
- [ ] Backup laptop prepared with identical setup

---

## 10. Sources

- [Chrome Offscreen Documents Guide](https://developer.chrome.com/blog/Offscreen-Documents-in-Manifest-v3)
- [How to Build a Chrome Recording Extension (Recall.ai)](https://www.recall.ai/blog/how-to-build-a-chrome-recording-extension)
- [chrome.tabCapture API Reference](https://developer.chrome.com/docs/extensions/reference/api/tabCapture)
- [Audio Recording and Screen Capture (Chrome Developers)](https://developer.chrome.com/docs/extensions/how-to/web-platform/screen-capture)
- [Recall.ai Chrome Recording Extension (reference implementation)](https://github.com/recallai/chrome-recording-transcription-extension)
- [MV3 WebSocket in Service Worker (Chrome 116+)](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/23pCzk69Ueo/m/z9GH0J7WBQAJ)
