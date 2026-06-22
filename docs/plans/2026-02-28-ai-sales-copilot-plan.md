# AI Sales Copilot — Implementation Plan

> **IMPORTANT:** Start with fresh context. Run `/clear` before `/implement`.

Created: 2026-02-28
Status: COMPLETE
Design: docs/plans/2026-02-28-ai-sales-copilot-design.md
PRD: AI_Sales_Copilot_PRD.md

> **Status Lifecycle:** PENDING → COMPLETE → VERIFIED
> - PENDING: Initial state, awaiting implementation
> - COMPLETE: All tasks implemented (set by /implement)
> - VERIFIED: Rules supervisor passed (set automatically)

## Summary

**Goal:** Build a demo-ready MVP Chrome Extension + FastAPI backend for real-time AI sales assistance during SIP calls, targeting SberCRM leadership demo.

**Architecture:** Chrome MV3 Extension (Popup + Offscreen Document for audio/WebSocket + Content Script widget in Shadow DOM + Service Worker control plane) communicates via native binary WebSocket with a FastAPI backend running an async pipeline: VAD (Silero ONNX) → STT (Deepgram Nova-3 WebSocket, with SaluteSpeech as pluggable alternative) → RAG (ChromaDB + BM25 hybrid) → LLM (Gemini 2.5 Flash via OpenRouter) → streaming Hint delivery.

**Tech Stack:**
- Extension: TypeScript, Vite + vite-plugin-web-extension, @xstate/store (widget), Web Audio API + AudioWorklet
- Backend: Python 3.11+, FastAPI, Redis, ChromaDB, ONNX Runtime, deepgram-sdk (STT), OpenRouter (openai SDK)
- Models: Deepgram Nova-3 (STT primary), SaluteSpeech (STT optional), Silero VAD v5 ONNX, multilingual-e5-base (embeddings), Gemini 2.5 Flash / GPT-4.1-mini (LLM)

## Scope

### In Scope
- File upload (PDF, XLSX, DOCX, MD, TXT) with indexing
- Pre-call briefing (buyer portrait + negotiation strategy)
- Real-time audio capture (mic + tab stereo)
- Real-time transcription via SaluteSpeech gRPC
- RAG-powered contextual hints with source attribution
- Sentiment analysis + coaching prompts
- Factual error warnings
- Shadow DOM overlay widget with 6 states
- Post-call summary button
- Health check endpoint
- Docker Compose (backend + Redis + ChromaDB)

### Out of Scope
- Script Compliance Check (Phase 2)
- Authentication / multi-tenancy
- Call recording/playback
- CRM integration
- Mobile/cross-browser support
- Demo-mode with pre-recorded transcripts
- GDPR/PD compliance

## Prerequisites
- Docker + Docker Compose installed
- Chrome browser (latest stable)
- Node.js 20+ and pnpm (for extension)
- Python 3.11+ and uv (for backend)
- API keys: `DEEPGRAM_API_KEY` (primary STT), `OPENROUTER_API_KEY` (LLM), optionally `SBER_SPEECH_API_KEY` (if testing SaluteSpeech)
- Demo content files (tariffs PDF, competitors Excel, CRM notes) — needed by day 3

## Context for Implementer

- **Audio capture architecture:** Offscreen Document owns both audio streams and WebSocket. Service Worker is control plane only (tabCapture init, alarms). See design doc section 2.2.
- **Mic permission:** Cannot prompt in Offscreen Document. Must request from visible extension page on first launch. See design doc section 2.2 constraint #1.
- **tabCapture suppresses audio:** Must route tab stream back to AudioContext.destination. See design doc section 2.2 constraint #2.
- **AudioWorklet for PCM encoding:** Float32→Int16 conversion in dedicated audio thread. Worklet module loaded from extension's offscreen directory. See design doc section 2.2 constraint #3.
- **Binary WebSocket protocol:** 5-byte header (uint32 LE seq + uint8 channel) + payload. Channel 0=audio, 1=control JSON. Backend uses `websocket.receive()` low-level for mixed frames. See design doc section 4.2.
- **STT architecture:** Abstract `STTClient` interface with two implementations: `DeepgramClient` (primary, WebSocket streaming, ~200-500ms final) and `SaluteSpeechClient` (optional gRPC, benchmark day 1). Switch via `STT_PROVIDER` env var. Deepgram: `deepgram-sdk` v3+, `model="nova-3"`, `interim_results=true`, `endpointing=300`. SaluteSpeech: gRPC bidirectional, max chunk 4MB, max duration 2s.
- **OpenRouter:** Uses openai SDK with `base_url="https://openrouter.ai/api/v1"`. Model names: `google/gemini-2.5-flash`, `openai/gpt-4.1-mini`.
- **Silero VAD ONNX:** Consider `silero-vad-lite` (zero-dependency, bundles C++ ONNX runtime). Must run in `ThreadPoolExecutor` to avoid blocking asyncio. Single-threaded ONNX config. Expects ~30ms chunks (480 samples at 16kHz). RNN state must be maintained per stream.
- **Hybrid search:** ChromaDB cosine + rank_bm25 keyword, merged via RRF (k=60). BM25 index persisted as JSON alongside ChromaDB.
- **Embedding optimization:** Use ONNX QInt8 backend for multilingual-e5-base: `SentenceTransformer('intfloat/multilingual-e5-base', backend='onnx')` — ~15ms vs ~50ms FP32.
- **Chrome extension ports:** `chrome.runtime.connect()` for persistent communication. JSON serialization only (no Transferable ArrayBuffer in Chrome extension ports). Audio goes directly from Offscreen Doc to WebSocket, NOT through Service Worker.
- **Widget state machine:** 6 states (IDLE, LISTENING, HINT_ACTIVE, WARNING, DISCONNECTED, BRIEFING) with explicit transition table. Use hand-rolled state machine or @xstate/store (<1KB gzipped).

### Latency Optimizations (Critical for <2s budget)

1. **Speculative RAG on interim STT:** Start RAG search on interim transcripts (before `speech_final`). When final transcript arrives, use pre-fetched RAG context if query is similar (cosine >0.85), otherwise re-query. Saves 200-500ms.
2. **Streaming LLM output:** Stream LLM tokens to widget via WebSocket as they arrive. User sees first word at TTFT (~500ms after STT), not after full generation. Visual latency drops to ~700-1000ms.
3. **Pre-warm OpenRouter connection:** Keep a persistent HTTP/2 connection to OpenRouter. Send a lightweight request during session_start to warm the route. Saves 50-100ms on first real request.
4. **ONNX QInt8 embeddings:** Quantized embedding model cuts query embedding from ~50ms to ~15ms.
5. **Gemini 2.5 Flash-Lite fallback consideration:** If Gemini 2.5 Flash TTFT is too high, Flash-Lite has ~250ms TTFT (half). Evaluate quality before switching.

### Latency Budget (Verified with Benchmarks)

```
Stage                          Best Case    Typical    Source
─────────────────────────────────────────────────────────────────
VAD silence threshold          250 ms       400 ms     Design choice
VAD inference (Silero ONNX)    < 1 ms       < 1 ms     Silero GitHub
STT final (Deepgram Nova-3)   200 ms       500 ms     Deepgram docs
  OR SaluteSpeech              ???          ???        No public data
Embedding query (e5-base)      15 ms        50 ms      Benchmarks
ChromaDB search (500 docs)     3 ms         5 ms       ChromaDB benchmarks
LLM TTFT (Gemini 2.5 Flash)   500 ms       650 ms     Artificial Analysis
LLM generation (50 tokens)    200 ms       250 ms     248 tok/s
Network + rendering            20 ms        50 ms      Local WS
─────────────────────────────────────────────────────────────────
TOTAL (Deepgram + Gemini)      ~1190 ms     ~1905 ms   ✅ Within budget
TOTAL (w/ speculative RAG)     ~890 ms      ~1405 ms   ✅ Comfortable
Visual latency (w/ streaming)  ~700 ms      ~1000 ms   ✅ Excellent
```

## Progress Tracking

**MANDATORY: Update this checklist as tasks complete. Change `[ ]` to `[x]`.**

### 1. Infrastructure & Scaffolding
- [x] 1.1 Backend scaffold (FastAPI + Docker Compose)
- [x] 1.2 Extension scaffold (Vite + MV3 + TypeScript)

### 2. File Ingestion & RAG
- [x] 2.1 File parsing pipeline (PDF, Excel, DOCX)
- [x] 2.2 Chunking + embedding + ChromaDB indexing
- [x] 2.3 Hybrid search (ChromaDB + BM25 + RRF)

### 3. Audio Pipeline
- [x] 3.1 Extension audio capture (mic + tab stereo + AudioWorklet PCM)
- [x] 3.2 Backend audio processing (binary WS + de-interleave + VAD)
- [x] 3.3 STT integration (SaluteSpeech gRPC streaming)

### 4. LLM & Hints
- [x] 4.1 LLM client (OpenRouter + fallback + single-flight queue)
- [x] 4.2 Pipeline orchestrator (VAD → STT → RAG → LLM → Hint)

### 5. Extension UI
- [x] 5.1 Popup UI (upload, briefing, settings, permissions)
- [x] 5.2 Widget (Shadow DOM, state machine, hint display)

### 6. Briefing & Summary
- [x] 6.1 Pre-call briefing (portrait + strategy generation)
- [x] 6.2 Post-call summary + email draft

### 7. Integration & Polish
- [x] 7.1 End-to-end integration + edge cases
- [x] 7.2 Demo rehearsal preparation

**Total Tasks:** 14 | **Completed:** 14 | **Remaining:** 0

---

## Implementation Tasks

### 1. Infrastructure & Scaffolding

#### 1.1 Backend Scaffold (FastAPI + Docker Compose)

**Objective:** Set up the FastAPI backend with Docker Compose running Redis and ChromaDB. Health endpoint verifying all dependencies.

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/main.py`
- Create: `backend/config.py`
- Create: `backend/Dockerfile`
- Create: `docker-compose.yml`
- Create: `backend/.env.example`
- Test: `backend/tests/test_health.py`

**Implementation Steps:**

1. **Create `backend/pyproject.toml`** with dependencies:
   - Core: `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `redis[hiredis]`, `chromadb`, `onnxruntime`, `sentence-transformers`, `openai`, `deepgram-sdk`, `PyMuPDF`, `openpyxl`, `python-docx`, `rank-bm25`, `loguru`
   - Optional (SaluteSpeech): `grpcio`, `grpcio-tools`
   - Dev: `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, `httpx`

2. **Create `backend/config.py`** using Pydantic Settings:
   ```python
   class Settings(BaseSettings):
       stt_provider: str = "deepgram"  # "deepgram" or "salutespeech"
       deepgram_api_key: str = ""
       sber_speech_api_key: str = ""  # optional, only if stt_provider=salutespeech
       openrouter_api_key: str
       redis_url: str = "redis://localhost:6379"
       chroma_persist_dir: str = "./chroma_data"
       llm_primary_model: str = "google/gemini-2.5-flash"
       llm_fallback_model: str = "openai/gpt-4.1-mini"
       llm_primary_timeout_ms: int = 1000  # TTFT timeout only, not full response
       llm_fallback_timeout_ms: int = 2000
       vad_threshold: float = 0.5
       embedding_model: str = "intfloat/multilingual-e5-base"
       log_level: str = "INFO"
       model_config = SettingsConfigDict(env_file=".env")
   ```

3. **Create `backend/main.py`** with FastAPI app:
   - `lifespan` context manager: load embedding model, init ChromaDB, init Redis, warm up VAD model
   - `GET /api/v1/health` — check Redis ping, ChromaDB heartbeat, STT provider auth (Deepgram or SaluteSpeech), OpenRouter reachability
   - `POST /api/v1/upload` — placeholder (implemented in 2.1)
   - `DELETE /api/v1/session/{id}` — delete ChromaDB collection, BM25 JSON, Redis keys for session
   - `WebSocket /ws` — placeholder (implemented in 3.2)

4. **Create `docker-compose.yml`**:
   - `backend`: build from `backend/Dockerfile`, ports 8000, env_file `.env`
   - `redis`: `redis:7-alpine`, port 6379
   - `chromadb`: `chromadb/chroma:latest`, port 8001, volume for persistence

5. **Create `backend/Dockerfile`**:
   - Multi-stage: builder (uv install) + runtime (slim)
   - Pre-download Silero VAD ONNX model and embedding model at build time
   - Non-root user

6. **Write test:** `test_health.py` — verify health endpoint returns 200 with all components status.

**Definition of Done:**
- [ ] `docker compose up` starts all 3 services
- [ ] `GET /api/v1/health` returns `{"status": "ok", "redis": "ok", "chromadb": "ok"}`
- [ ] Backend connects to Redis and ChromaDB
- [ ] Tests pass with `pytest`

---

#### 1.2 Extension Scaffold (Vite + MV3 + TypeScript)

**Objective:** Set up Chrome MV3 extension project with Vite bundler, TypeScript, and all entry points.

**Files:**
- Create: `extension/package.json`
- Create: `extension/vite.config.ts`
- Create: `extension/tsconfig.json`
- Create: `extension/manifest.json`
- Create: `extension/src/background/service-worker.ts` (minimal keepalive)
- Create: `extension/src/popup/popup.html` + `popup.ts` + `popup.css`
- Create: `extension/src/offscreen/offscreen.html` + `offscreen.ts`
- Create: `extension/src/content/widget.ts` + `widget.css`
- Create: `extension/src/shared/types.ts` + `messages.ts` + `constants.ts`

**Implementation Steps:**

1. **Create `extension/package.json`** with:
   - `vite`, `vite-plugin-web-extension`, `typescript`
   - No XState yet (added in 5.2)

2. **Create `extension/manifest.json`**:
   ```json
   {
     "manifest_version": 3,
     "name": "AI Sales Copilot",
     "version": "0.1.0",
     "permissions": ["activeTab", "tabCapture", "offscreen", "storage", "tabs", "alarms"],
     "host_permissions": ["ws://localhost:8000/*", "http://localhost:8000/*"],
     "background": { "service_worker": "src/background/service-worker.ts" },
     "content_scripts": [{ "matches": ["<all_urls>"], "js": ["src/content/widget.ts"], "css": ["src/content/widget.css"] }],
     "action": { "default_popup": "src/popup/popup.html" },
     "web_accessible_resources": [{ "resources": ["audio-worklet.js"], "matches": ["chrome-extension://*/*"] }]
   }
   ```
   **Note:** No `"microphone"` permission needed in manifest — mic access is requested at runtime via `getUserMedia` from the permissions page. `host_permissions` required for WebSocket and REST calls to backend.

3. **Create `extension/vite.config.ts`**:
   - Configure `vite-plugin-web-extension` for MV3 with multiple entry points
   - **AudioWorklet special handling:** Configure separate rollup input for `audio-worklet.ts` as IIFE format (AudioWorklet scope does NOT support ES `import`). Output as `audio-worklet.js` at extension root. Do NOT let Vite bundle it with offscreen.js.
   - **permissions.html:** Add to `additionalInputs`: `['src/permissions/permissions.html', 'src/offscreen/offscreen.html']`
   - Verify built output structure matches manifest paths

4. **Create minimal `service-worker.ts`**:
   - `chrome.alarms.create("keepalive", { periodInMinutes: 0.4 })` — 24-second keepalive
   - `chrome.alarms.onAlarm.addListener` — no-op handler
   - Message router between popup ↔ offscreen ↔ content script

5. **Create shared types** (`types.ts`, `messages.ts`, `constants.ts`):
   - WS message types including streaming: `hint_start`, `hint_chunk`, `hint_end` (new for LLM streaming)
   - Widget states enum, port message interfaces
   - Backend URL constant (synced with `host_permissions`)

6. **Create skeleton files** for popup (basic HTML form), offscreen (empty), content script (empty shadow DOM host injection), permissions page (placeholder).

**Definition of Done:**
- [ ] `cd extension && pnpm install && pnpm build` succeeds
- [ ] Extension loads in Chrome developer mode
- [ ] Popup opens and shows placeholder UI
- [ ] Service Worker registers, alarm fires
- [ ] Content script injects empty Shadow DOM container on any page
- [ ] `audio-worklet.js` exists as separate file in build output (not bundled)
- [ ] `permissions.html` accessible via `chrome.runtime.getURL('permissions.html')`
- [ ] No console errors

---

### 2. File Ingestion & RAG

#### 2.1 File Parsing Pipeline

**Objective:** Parse uploaded PDF, Excel, and DOCX files into text chunks with metadata.

**Files:**
- Create: `backend/ingestion/parser.py`
- Create: `backend/ingestion/chunker.py`
- Modify: `backend/main.py` (add `/api/v1/upload` endpoint)
- Test: `backend/tests/test_ingestion.py`
- Test fixtures: `backend/tests/fixtures/sample.pdf`, `sample.xlsx`, `sample.docx`

**Implementation Steps:**

1. **Write failing tests** for:
   - `test_parse_pdf` — extract text from PDF with page numbers
   - `test_parse_excel` — extract rows with sheet/row metadata
   - `test_parse_docx` — extract text with section headers
   - `test_parse_unsupported` — reject `.exe`, return clear error
   - `test_parse_corrupt_file` — handle gracefully, return error message
   - `test_chunker_text` — 512 tokens, 64 overlap
   - `test_chunker_table` — row-based chunking for tabular data

2. **Implement `parser.py`:**
   - `parse_pdf(file_bytes) -> list[ParsedChunk]` using PyMuPDF
   - `parse_excel(file_bytes) -> list[ParsedChunk]` using openpyxl (handle merged cells!)
   - `parse_docx(file_bytes) -> list[ParsedChunk]` using python-docx
   - Each returns `ParsedChunk(text, source_file, page_number, section_title, chunk_type)`

3. **Implement `chunker.py`:**
   - Text chunks: 512 tokens with 64-token overlap using tiktoken or simple word-count approximation
   - Table chunks: by row/section, preserving column headers in each chunk
   - Returns `list[Chunk]` with metadata

4. **Implement upload endpoint** in `main.py`:
   - `POST /api/v1/upload` — accepts multipart files + `session_id`
   - Validates: file size (<50MB), MIME type, format support
   - **Bind KB to session:** Write `session:{session_id}:kb_id = knowledge_base_id` to Redis with TTL=30min
   - Returns `{knowledge_base_id, files_indexed, chunks_count, time_ms}`
   - On partial success (some files fail): return `{..., failed_files: [{name, error}]}` with HTTP 207

**Definition of Done:**
- [ ] Upload 3 test files (PDF + Excel + DOCX), endpoint returns chunks_count
- [ ] Parser handles corrupt/protected files with clear errors
- [ ] Table data preserves column headers per chunk
- [ ] `session:{session_id}:kb_id` written to Redis after successful indexing
- [ ] Partial upload failure returns per-file error details
- [ ] All tests pass

---

#### 2.2 Chunking + Embedding + ChromaDB Indexing

**Objective:** Embed text chunks using multilingual-e5-base and store in ChromaDB with metadata.

**Files:**
- Create: `backend/ingestion/embedder.py`
- Modify: `backend/main.py` (wire up upload → parse → embed → index)
- Test: `backend/tests/test_embedder.py`

**Implementation Steps:**

1. **Write failing tests:**
   - `test_embed_single_chunk` — returns 384-dim vector
   - `test_embed_batch` — embeds multiple chunks efficiently
   - `test_index_and_retrieve` — store chunks, query ChromaDB, get results with metadata
   - `test_collection_isolation` — different KB IDs use different collections

2. **Implement `embedder.py`:**
   - Load `multilingual-e5-base` at startup with ONNX QInt8 backend: `SentenceTransformer('intfloat/multilingual-e5-base', backend='onnx')` — ~15ms/query vs ~50ms FP32
   - `embed_chunks(chunks: list[Chunk]) -> list[float[384]]` — batch embedding
   - `embed_query(query: str) -> list[float]` — single query embedding (optimized for latency)
   - `index_chunks(kb_id: str, chunks: list[Chunk], embeddings: list)` — create ChromaDB collection `session_{kb_id}`, upsert documents with metadata
   - Build and persist BM25 index: tokenize chunks, save corpus + doc_ids to JSON file. **Use atomic write:** write to `.tmp` then `os.replace()`.
   - `load_bm25_index(kb_id: str) -> BM25Okapi | None` — load from `{CHROMA_PERSIST_DIR}/bm25_{kb_id}.json`, with `json.JSONDecodeError` guard (rebuild from ChromaDB if corrupt)

3. **Wire up upload endpoint:** parse → chunk → embed → index → return KB ID

**Definition of Done:**
- [ ] Upload 50 pages of test data, indexing completes in <30s
- [ ] ChromaDB collection created with correct metadata
- [ ] BM25 index JSON file persisted
- [ ] Tests pass

---

#### 2.3 Hybrid Search (ChromaDB + BM25 + RRF)

**Objective:** Implement hybrid search combining semantic (ChromaDB) and keyword (BM25) results via Reciprocal Rank Fusion.

**Files:**
- Create: `backend/pipeline/rag.py`
- Test: `backend/tests/test_rag.py`

**Implementation Steps:**

1. **Write failing tests** (from PRD):
   - `test_rag_exact_match` — query "Какой RTO у SLA Gold?", assert contains "15 минут"
   - `test_rag_semantic_match` — query "Как быстро восстановите после сбоя?", same result
   - `test_rag_no_match` — query "Какой цвет машины CEO?", assert "Нет релевантных данных"
   - `test_rag_table_data` — query from Excel data, get correct cell value
   - `test_rag_hybrid_superiority` — query "Gold план $500", keyword finds exact match

2. **Implement `rag.py`:**
   - `HybridSearchEngine` class, initialized with ChromaDB client + BM25 index + ThreadPoolExecutor
   - One instance per WebSocket session, created on `session_start` with loaded BM25 index
   - `search(query: str, kb_id: str, top_k: int = 3) -> list[SearchResult]`
   - Internally runs both searches in parallel (`asyncio.gather`):
     - ChromaDB cosine similarity search (embed query → query collection) — async I/O
     - BM25 keyword search — **wrapped in `run_in_executor`** (CPU-bound, blocks event loop otherwise; 5-50ms for 500 docs)
   - RRF fusion: `score(d) = Σ 1/(k + rank_i(d))` with `k=60`
   - Return top_k results with `SearchResult(text, source_file, page, score, search_type)`
   - **session_start handler:** validate `kb_id` exists in ChromaDB (`get_collection()`), load BM25 from disk, return error if KB not found

**Definition of Done:**
- [ ] All 5 RAG tests pass
- [ ] Hybrid search returns results with source attribution
- [ ] BM25 catches exact keyword matches that semantic search misses
- [ ] Query latency <200ms

---

### 3. Audio Pipeline

#### 3.1 Extension Audio Capture

**Objective:** Capture mic + tab audio in Offscreen Document, mix to stereo PCM16 via AudioWorklet, send binary frames over WebSocket.

**Files:**
- Create: `extension/src/offscreen/audio-worklet.ts` (PCM16Processor)
- Modify: `extension/src/offscreen/offscreen.ts` (audio capture + WS)
- Modify: `extension/src/background/service-worker.ts` (tabCapture + offscreen lifecycle)
- Create: `extension/src/permissions/permissions.html` + `permissions.ts` (mic permission page)
- Modify: `extension/src/shared/types.ts` (binary frame types)
- Create: `extension/src/lib/ws-client.ts` (binary WebSocket framing)

**Implementation Steps:**

1. **Create `audio-worklet.ts`** (PCM16Processor):
   - `class PCM16Processor extends AudioWorkletProcessor`
   - In `process()`: receive Float32 stereo input, convert to Int16 PCM
   - Pre-allocate output buffer once (no GC in process loop)
   - `this.port.postMessage(int16Array, [int16Array.buffer])` with transferable

2. **Create `permissions.html` + `permissions.ts`**:
   - Opens as visible tab on first launch
   - Requests mic permission via `navigator.mediaDevices.getUserMedia({audio: true})`
   - On grant: stores flag in `chrome.storage.local`, closes tab
   - On deny: shows step-by-step guide to enable in Chrome settings

3. **Implement Service Worker audio initiation:**
   - On "start_capture" message from popup:
     a. Check mic permission flag in `chrome.storage.local`
     b. **Debounce:** Ignore if capture already in progress (guard against double-click)
     c. Call `chrome.tabCapture.getMediaStreamId({targetTabId})` — **validate tab is normal window, not DevTools/popup**
     d. Create Offscreen Document (check existing first with `chrome.runtime.getContexts()`):
        ```ts
        await chrome.offscreen.createDocument({
          url: chrome.runtime.getURL('offscreen/offscreen.html'),
          reasons: ['USER_MEDIA', 'AUDIO_PLAYBACK'],  // Both required
          justification: 'Captures mic/tab audio, routes tab audio to speakers',
        });
        ```
     e. Send `{streamId, action: "start_capture"}` to Offscreen Doc via port

4. **Implement Offscreen Document audio pipeline:**
   - Receive streamId from Service Worker
   - **Check AudioContext state:** Create `audioCtx = new AudioContext({sampleRate: 16000})`, call `audioCtx.resume()` if state is 'suspended' (no user gesture in offscreen context)
   - Get tab audio: `navigator.mediaDevices.getUserMedia({audio: {mandatory: {chromeMediaSource: 'tab', chromeMediaSourceId: streamId}}})`
   - Get mic audio: `navigator.mediaDevices.getUserMedia({audio: true})`
   - Route tab audio back to speakers: `audioCtx.createMediaStreamSource(tabStream).connect(audioCtx.destination)`
   - Create ChannelMergerNode: L=mic, R=tab
   - Load AudioWorklet: `audioCtx.audioWorklet.addModule(chrome.runtime.getURL('audio-worklet.js'))` (**use chrome.runtime.getURL, NOT relative path**)
   - Connect merger → AudioWorkletNode → receive PCM chunks via port
   - **Worklet `process()` MUST return `true`** to keep processor alive

5. **Implement `ws-client.ts`:**
   - Open native WebSocket to backend
   - Send audio frames: 5-byte header (seq uint32 LE + channel uint8) + PCM16 payload
   - Send control frames: 5-byte header + UTF-8 JSON
   - Receive: parse incoming messages, dispatch to appropriate handler
   - Auto-reconnect with exponential backoff (1s, 2s, 4s, max 30s)

**Definition of Done:**
- [ ] Extension captures mic audio (mono)
- [ ] Extension captures tab audio (mono)
- [ ] Stereo mix produces separate L/R channels
- [ ] Binary frames sent to backend WebSocket
- [ ] User still hears tab audio during capture
- [ ] Permission flow works on first launch
- [ ] WebSocket reconnects after disconnect

---

#### 3.2 Backend Audio Processing

**Objective:** Receive binary WebSocket frames, de-interleave stereo to separate channels, run VAD on each channel.

**Files:**
- Create: `backend/pipeline/audio.py`
- Create: `backend/pipeline/vad.py`
- Modify: `backend/main.py` (implement WS endpoint)
- Test: `backend/tests/test_audio.py`

**Implementation Steps:**

1. **Write failing tests:**
   - `test_parse_binary_frame` — parse 5-byte header + payload
   - `test_deinterleave_stereo` — split interleaved PCM16 into L+R
   - `test_vad_speech_detected` — speech audio → VAD returns True
   - `test_vad_silence_detected` — silence → VAD returns False
   - `test_vad_nonblocking` — VAD runs in executor, doesn't block event loop

2. **Implement `audio.py`:**
   - `parse_frame(data: bytes) -> AudioFrame | ControlFrame`
   - `deinterleave_stereo(pcm16: bytes) -> tuple[bytes, bytes]` — even samples = L (mic), odd = R (tab)

3. **Implement `vad.py`:**
   - Load Silero VAD ONNX at startup: `load_silero_vad(onnx=True)`
   - Create `ThreadPoolExecutor(max_workers=2)` (one per channel)
   - `async def detect_speech(audio: bytes, channel: str) -> bool` — wraps `run_in_executor`
   - Maintain VAD state per channel (Silero is stateful RNN)

4. **Implement WebSocket endpoint** in `main.py`:
   - `@app.websocket("/ws")` using low-level `websocket.receive()` for mixed binary/text
   - On binary frame: parse → deinterleave → VAD per channel → if speech on client channel → buffer for STT
   - On control frame: parse JSON → handle session_start, session_end
   - Session state in Redis

**Definition of Done:**
- [ ] WebSocket accepts binary frames from extension
- [ ] Stereo correctly split into mic/tab channels
- [ ] VAD filters silence (no STT calls on silence)
- [ ] VAD runs without blocking event loop
- [ ] Tests pass

---

#### 3.3 STT Integration (Deepgram Nova-3 primary, SaluteSpeech pluggable)

**Objective:** Abstract STT interface with Deepgram Nova-3 WebSocket as primary implementation. Stream audio from VAD, receive interim and final transcripts tagged by speaker.

**Files:**
- Create: `backend/pipeline/stt.py` (abstract `STTClient` + `DeepgramSTT` implementation)
- Create: `backend/pipeline/stt_salute.py` (optional `SaluteSpeechSTT` implementation)
- Test: `backend/tests/test_stt.py`

**Implementation Steps:**

1. **Write failing tests:**
   - `test_stt_transcript_final` — send audio, receive final transcript with `is_final=true`
   - `test_stt_transcript_interim` — interim results arrive before final
   - `test_stt_speaker_tagging` — client channel tagged "client", rep channel tagged "rep"
   - `test_stt_reconnect_on_error` — WebSocket/gRPC error → reconnect
   - `test_stt_session_lifecycle` — open on session_start, close on session_end
   - `test_stt_provider_switch` — factory creates correct client based on `STT_PROVIDER` config

2. **Define abstract interface:**
   ```python
   class STTClient(ABC):
       async def start_session(self, session_id: str) -> None: ...
       async def send_audio(self, chunk: bytes, channel: str) -> None: ...
       async def close(self) -> None: ...
       # Yields Transcript(speaker, text, is_final) via callback or async iterator
   ```

3. **Implement `DeepgramSTT` (primary):**
   - Uses `deepgram-sdk` v3+, `listen.v2.connect()` async interface
   - Config: `model="nova-3"`, `language="ru"`, `interim_results=True`, `endpointing=300`, `smart_format=True`
   - Two parallel WebSocket connections: one for client channel, one for rep channel
   - Event handlers: `on_message` → yield `Transcript(speaker, text, is_final)` when `message.is_final`
   - Interim results also emitted for speculative RAG (tagged `is_final=False`)
   - Handle reconnect on `on_error` / `on_close` with exponential backoff

4. **Implement `SaluteSpeechSTT` (optional, gated by `STT_PROVIDER=salutespeech`):**
   - gRPC bidirectional streaming with `Recognize` method
   - Requires proto files in `backend/pipeline/proto/` — **obtain from Sber developer portal as day-1 task**
   - Same abstract interface as DeepgramSTT

5. **STT factory:**
   ```python
   def create_stt_client(settings: Settings) -> STTClient:
       if settings.stt_provider == "salutespeech":
           return SaluteSpeechSTT(settings.sber_speech_api_key)
       return DeepgramSTT(settings.deepgram_api_key)
   ```

6. **Implement transcript buffer:**
   - Accumulate interim results per speaker
   - On `is_final`: flush to session manager and trigger RAG+LLM pipeline
   - On interim: emit for speculative RAG (task 4.2)

**Definition of Done:**
- [ ] Send Russian audio via Deepgram → receive correct transcript
- [ ] Client and rep speech tagged separately
- [ ] Interim results emitted for speculative RAG
- [ ] Final transcripts trigger downstream pipeline
- [ ] WebSocket reconnects on error
- [ ] STT_PROVIDER switch works (Deepgram ↔ SaluteSpeech)
- [ ] Tests pass (with mocked WebSocket/gRPC for unit tests)

---

### 4. LLM & Hints

#### 4.1 LLM Client (OpenRouter + Fallback)

**Objective:** Call Gemini 2.5 Flash via OpenRouter with structured JSON output. Fall back to GPT-4.1-mini on timeout. Single-flight queue per session.

**Files:**
- Create: `backend/pipeline/llm.py`
- Test: `backend/tests/test_llm.py`

**Implementation Steps:**

1. **Write failing tests:**
   - `test_llm_generates_hint` — returns valid HintResponse JSON
   - `test_llm_fallback_on_timeout` — primary times out → fallback returns result
   - `test_llm_cached_on_double_timeout` — both timeout → cached response from Redis
   - `test_llm_single_flight` — cancel in-flight when new request arrives
   - `test_llm_json_parsing` — handle malformed JSON gracefully

2. **Implement `llm.py`:**
   - `OpenRouterClient` using `openai.AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key)`
   - `async def generate_hint_stream(context: HintContext) -> AsyncIterator[str]` — streaming version (primary path)
   - `async def generate_hint(context: HintContext) -> HintResponse` — non-streaming fallback
   - Assemble prompt (Russian, as per design doc section 5.1)
   - Primary path: call with `stream=True`, yield tokens as they arrive, validate full response after stream ends
   - **TTFT timeout:** `asyncio.wait_for` around ONLY the first `await stream.__anext__()` call (timeout=`llm_primary_timeout_ms`). This guards against TTFT failure without cutting off mid-stream.
   - **Per-token idle timeout:** After first token, apply 5s idle timeout on each subsequent `__anext__()`. If mid-stream stall occurs, send `hint_end` with error and stop.
   - On TTFT timeout/error → call fallback with `asyncio.wait_for(timeout=llm_fallback_timeout_ms)`
   - On double timeout → return cached objection from Redis
   - Parse with Pydantic `HintResponse.model_validate_json()`, handle `ValidationError`
   - Strip markdown code fences before JSON parsing if needed
   - **Single-flight queue:** Track current LLM task as `self._llm_task: asyncio.Task | None`. On new request: if `_llm_task` exists and not done, call `_llm_task.cancel()`. LLM coroutine must NOT catch `CancelledError` (let it propagate). **Do NOT use `asyncio.Event`** — it cannot cancel in-flight HTTP calls.
   - **Connection pre-warming:** `async def warm_connection()` — lightweight request on session_start to establish HTTP/2 connection

**Definition of Done:**
- [ ] Generates valid HintResponse with hint, source, sentiment, color
- [ ] Fallback triggers on primary timeout
- [ ] Cached response returned on double failure
- [ ] Single-flight cancellation works
- [ ] Tests pass

---

#### 4.2 Pipeline Orchestrator

**Objective:** Coordinate the full pipeline: VAD → STT → Session → RAG → LLM → Hint delivery via WebSocket.

**Files:**
- Create: `backend/pipeline/orchestrator.py`
- Create: `backend/session/manager.py`
- Test: `backend/tests/test_pipeline.py`

**Implementation Steps:**

1. **Write failing tests:**
   - `test_pipeline_full_flow` — audio in → hint out (with mocked STT/LLM)
   - `test_pipeline_stage_failure` — STT fails → no hint, no crash
   - `test_session_utterance_buffer` — last 10 utterances maintained
   - `test_session_rolling_summary` — summary updated every 2 minutes
   - `test_pipeline_latency` — full pipeline <2000ms (mocked external APIs)
   - `test_speculative_rag_reuse` — interim RAG result reused when final is similar (cosine >0.85)
   - `test_speculative_rag_discard` — interim RAG result discarded when final diverges
   - `test_llm_streaming` — LLM tokens streamed to WebSocket as they arrive

2. **Implement `session/manager.py`:**
   - `SessionManager(redis)` class
   - `add_utterance(session_id, speaker, text)` — append to Redis list, trim to 10
   - `get_context(session_id) -> SessionContext` — utterances + summary + portrait + strategy
   - `update_summary(session_id)` — LLM call to summarize, background task every 2min
   - TTL: 30 minutes on all keys

3. **Implement `orchestrator.py`:**
   - `PipelineOrchestrator` class, one per WebSocket session
   - **Task lifecycle management:** Maintain `self._background_tasks: set[asyncio.Task]` for ALL spawned tasks. In `async def teardown()` (called from WebSocket `finally` block): cancel all tasks, `await asyncio.gather(*tasks, return_exceptions=True)`. Rolling summary stored as `self._summary_task` for explicit cancellation.
   - **On `session_start`:** Validate `kb_id` exists in ChromaDB. Load BM25 index from disk. Create `HybridSearchEngine` instance. Send error and close WS with code 4404 if KB not found.
   - **Speculative RAG on interim transcripts:**
     a. On `interim` transcript from client channel: cancel previous speculative task if still running, then start new RAG search (`asyncio.create_task`, add to `_background_tasks`)
     b. Cache interim RAG result with query embedding
     c. On `final` transcript: compute cosine similarity between interim and final query embeddings
     d. If similarity > 0.85: reuse cached RAG result (saves 200-500ms)
     e. If similarity ≤ 0.85: run new RAG search with final transcript
   - **Main pipeline on `final` transcript:**
     a. Add to session utterances
     b. If speaker == "client": get RAG context (speculative or fresh)
     c. Build HintContext: session context + RAG results + latest utterance
     d. Call LLM via single-flight queue with **streaming enabled**
     e. Stream LLM tokens to widget via WebSocket as they arrive (not waiting for full response)
     f. On stream complete: validate full response with Pydantic, send final control frame
   - **LLM streaming delivery:**
     a. First token → send `{type: "hint_start", sentiment, color}` control frame
     b. Each token batch (~50ms) → send `{type: "hint_chunk", text}`
     c. Stream end → send `{type: "hint_end", source, full_text}` with validated response
   - Error propagation: `PipelineResult(status, stage_failed, fallback_used)`
   - Background summary update: `asyncio.create_task` tied to session lifecycle
   - **Pre-warm OpenRouter:** On `session_start`, send lightweight health-check request to warm HTTP/2 connection

**Definition of Done:**
- [ ] Full pipeline runs end-to-end with mocked STT
- [ ] Hints delivered via WebSocket within latency budget
- [ ] Session state maintained in Redis
- [ ] Rolling summary updates in background
- [ ] Stage failures handled gracefully
- [ ] Tests pass

---

### 5. Extension UI

#### 5.1 Popup UI

**Objective:** Build extension popup with file upload (drag-drop), briefing display, settings, and permission flow.

**Files:**
- Modify: `extension/src/popup/popup.html`
- Modify: `extension/src/popup/popup.ts`
- Modify: `extension/src/popup/popup.css`
- Modify: `extension/src/background/service-worker.ts` (handle upload via REST)

**Implementation Steps:**

1. **File upload screen:**
   - Drag-and-drop zone accepting PDF, XLSX, XLS, DOCX, MD, TXT
   - Client-side validation: file size <50MB, MIME type check, max 10 files
   - Progress bar during upload
   - Display indexed file count + chunks count on completion
   - Error display for failed files (partial success handling)
   - Upload via `fetch()` to `POST /api/v1/upload`

2. **Briefing screen:**
   - "Подготовить звонок" button
   - Calls `POST /api/v1/briefing` with session_id + knowledge_base_id
   - Displays buyer portrait card + strategy card + top 3 objections
   - Loading state during generation

3. **Settings screen:**
   - Mizugate URL pattern input (stored in `chrome.storage.local`)
   - Backend URL input (default: `ws://localhost:8000/ws`)
   - Language toggle (future, placeholder)

4. **Permission flow:**
   - On first launch: check `chrome.storage.local` for mic permission flag
   - If not granted: show "Настройка микрофона" screen with button
   - Button opens `permissions.html` in new tab

5. **State sync:**
   - All popup state stored in `chrome.storage.session`
   - On popup open: read state from storage
   - Listen to `chrome.storage.onChanged` for live updates

**Definition of Done:**
- [ ] Drag-drop upload works, shows progress
- [ ] Briefing displays portrait + strategy
- [ ] Settings persist across popup reopens
- [ ] Permission flow works on first launch
- [ ] UI in Russian

---

#### 5.2 Widget (Shadow DOM + State Machine)

**Objective:** Build the overlay widget with Shadow DOM, state machine for 6 states, hint display with color coding, and animations.

**Files:**
- Modify: `extension/src/content/widget.ts`
- Modify: `extension/src/content/widget.css`
- Create: `extension/src/content/state-machine.ts`

**Implementation Steps:**

1. **Create state machine** (hand-rolled or @xstate/store):
   - 6 states: IDLE, LISTENING, HINT_ACTIVE, WARNING, DISCONNECTED, BRIEFING
   - Transition table from design doc section 6.3 + **add `BRIEFING → DISCONNECTED` (WS lost)**
   - Each state entry clears previous visual artifacts
   - Auto-dismiss timers start at `hint_end` (NOT `hint_start`) — effective reading window is full 3s/5s after stream completes
   - Guard against invalid transitions (log warning, stay in current state)

2. **Create Shadow DOM widget:**
   - Inject `<div id="ai-copilot-host">` as direct child of `document.body`
   - Attach Shadow DOM (closed mode)
   - Import widget.css into Shadow DOM — load `@font-face` in **main document** (Shadow DOM cannot load fonts)
   - Position: `fixed`, right side, `z-index: 2147483647`
   - **ARIA:** `role="complementary"`, `aria-label="AI Sales Copilot"`, hint region `aria-live="polite"`, warning region `aria-live="assertive"`
   - **Keyboard:** `Alt+Shift+C` to toggle collapse/expand

3. **Widget visual states:**
   - IDLE: collapsed pill, gray, "AI Готов"
   - LISTENING: expanded panel, pulsing blue border
   - HINT_ACTIVE: hint text + source badge + colored border (green/yellow/red/blue)
   - WARNING: red border, bold text, shake animation (with `prefers-reduced-motion` check)
   - DISCONNECTED: gray overlay, "Переподключение..."
   - BRIEFING: full panel with portrait + strategy cards

4. **Color system:**
   - GREEN `#27AE60`: positive sentiment
   - YELLOW `#F39C12`: attention/objection
   - RED `#E74C3C`: error/warning
   - BLUE `#2E75B6`: informational
   - GRAY `#95A5A6`: system/idle

5. **Message handling (with streaming support):**
   - Listen on port from Service Worker
   - On `hint_start` → transition to HINT_ACTIVE or WARNING, show color border, clear previous hint
   - On `hint_chunk` → **batch DOM updates via `requestAnimationFrame`**: accumulate chunks in `pendingText` string, flush to DOM once per frame. Prevents jank at high token rates (248 tok/s).
   - On `hint_end` → finalize hint with source badge, **start auto-dismiss timer now** (3s for HINT_ACTIVE, 5s for WARNING)
   - On `hint` (non-streaming fallback) → display full hint immediately
   - On `transcript` → show live transcript in subtitle area
   - On `status` → update state accordingly
   - On `error` → show error badge
   - **UTF-8 streaming:** Use `TextDecoder({stream: true})` for Cyrillic multi-byte chars that may split across chunk boundaries

6. **Tab focus warning:**
   - Listen to `document.visibilitychange`
   - If hidden during active call → show yellow warning "Tab не в фокусе"

**Definition of Done:**
- [ ] Widget renders on any page inside Shadow DOM
- [ ] All 6 states display correctly (including BRIEFING → DISCONNECTED)
- [ ] Color coding matches spec
- [ ] No CSS leaks to/from host page
- [ ] Streaming hint typewriter works without jank (requestAnimationFrame batching)
- [ ] Hint text with source badge displays correctly
- [ ] ARIA live regions announce hints and warnings
- [ ] `Alt+Shift+C` toggles widget collapse
- [ ] Animations respect `prefers-reduced-motion` (pulsing border AND shake)
- [ ] Widget positioned correctly even with transformed ancestors (body direct child)

---

### 6. Briefing & Summary

#### 6.1 Pre-call Briefing

**Objective:** Generate buyer portrait + negotiation strategy from uploaded documents.

**Files:**
- Create: `backend/briefing/portrait.py`
- Modify: `backend/main.py` (implement `/api/v1/briefing`)
- Test: `backend/tests/test_briefing.py`

**Implementation Steps:**

1. **Write failing tests:**
   - `test_briefing_generates_portrait` — returns portrait with key traits
   - `test_briefing_generates_strategy` — returns negotiation strategy
   - `test_briefing_generates_objections` — returns top 3 objections with responses
   - `test_briefing_latency` — completes in <5s

2. **Implement `portrait.py`:**
   - `async def generate_briefing(kb_id: str, session_id: str) -> BriefingResponse`
   - Query RAG for client-related chunks (filter by chunk_type or source_file matching CRM notes)
   - Build prompt for LLM: "Проанализируй документы и создай портрет покупателя + стратегию переговоров"
   - Parse structured response with `BriefingResponse(portrait, strategy, objections)`
   - Cache in Redis for session duration

3. **Pre-cache objections:**
   - After briefing generation, extract top 10 likely objections
   - Store in Redis as `cache:objections:{kb_id}`
   - Used as fallback when LLM is unavailable during calls

**Definition of Done:**
- [ ] Briefing generates portrait referencing uploaded data
- [ ] Strategy is actionable (not generic)
- [ ] Top 3 objections have prepared responses
- [ ] Completes in <5s
- [ ] Results cached in Redis
- [ ] Tests pass

---

#### 6.2 Post-call Summary + Email Draft

**Objective:** Generate call summary and follow-up email draft from conversation history.

**Files:**
- Create: `backend/summarize/call_summary.py`
- Modify: `backend/main.py` (implement `/api/v1/summarize`)
- Test: `backend/tests/test_summary.py`

**Implementation Steps:**

1. **Write failing tests:**
   - `test_summary_generates_key_points` — extracts main discussion topics
   - `test_summary_generates_email` — produces formatted email draft
   - `test_summary_references_sources` — email cites specific data from KB

2. **Implement `call_summary.py`:**
   - `async def generate_summary(session_id: str) -> CallSummary`
   - Retrieve full conversation from Redis (all utterances + rolling summary)
   - Build prompt: "Создай резюме звонка и черновик follow-up письма"
   - Return `CallSummary(summary, key_points, action_items, email_draft)`
   - Email draft should reference specific facts from KB with sources

**Definition of Done:**
- [ ] Summary captures key discussion points
- [ ] Email draft is professional and referenced
- [ ] Works with conversation data from Redis
- [ ] Tests pass

---

### 7. Integration & Polish

#### 7.1 End-to-End Integration + Edge Cases

**Objective:** Wire everything together, handle edge cases, test full golden path.

**Files:**
- Modify: multiple files for wiring
- Create: `backend/tests/test_edge_cases.py`
- Create: `backend/tests/test_latency.py`

**Implementation Steps:**

1. **Wire popup → service worker → offscreen → backend → widget** full loop

2. **Edge case handling:**
   - E1: Cross-talk (both speak) → prioritize client channel for RAG trigger
   - E2: No RAG match → "Нет верифицированных данных"
   - E4: WebSocket disconnect → auto-reconnect, widget gray state
   - E5: Mic permission denied → clear error in popup
   - E6: Tab capture blocked → error with fallback instructions
   - E8: Background noise → VAD filters, "Ожидание речи..." after 10s silence
   - E9: Corrupt file → specific error message per file
   - E10: LLM timeout → cached response with `[кэш]` badge

3. **Latency tests:**
   - `test_latency_hint_generation` — full pipeline <2000ms
   - `test_latency_vad_filtering` — silence not sent to STT
   - `test_latency_llm_fallback` — fallback responds within 1.5s

4. **Connection resilience:**
   - WebSocket reconnect with exponential backoff
   - gRPC reconnect for SaluteSpeech
   - Redis connection pool with retry

**Definition of Done:**
- [ ] Full golden path works: upload → briefing → call → hints → summary
- [ ] All edge cases handled with appropriate UI feedback
- [ ] Latency within budget
- [ ] No crashes during 15-minute simulated call
- [ ] All tests pass

---

#### 7.2 Demo Rehearsal Preparation

**Objective:** Prepare demo content, pre-flight checklist, and Phase 2 roadmap slide.

**Files:**
- Create: `docs/DEMO_SCRIPT.md`
- Create: `docs/DEMO_PREFLIGHT.md`
- Create: `docs/PHASE2_ROADMAP.md`

**Implementation Steps:**

1. **Demo pre-flight checklist** (from design doc section 9)

2. **Demo script** (minute-by-minute, adapted from PRD section 11, in Russian):
   - 0:00–0:30 — Показать пустое расширение
   - 0:30–1:30 — Загрузить файлы, показать индексацию
   - 1:30–3:00 — Портрет покупателя + стратегия
   - 3:00–3:30 — Начать звонок, виджет слушает
   - 3:30–7:00 — Живой звонок с подготовленным "клиентом"
   - 7:00–8:00 — Вопрос вне базы → "Нет данных"
   - 8:00–9:00 — Эмоциональная поддержка (жёлтый)
   - 9:00–10:00 — Ошибка продавца → красное предупреждение
   - 10:00–11:00 — Резюме звонка + email
   - 11:00–12:00 — Q&A

3. **Phase 2 roadmap** — 1 page covering:
   - Multi-tenancy & auth
   - Data persistence (call history)
   - GDPR/PД compliance
   - SIP integration beyond Mizugate
   - Infrastructure costs at 50 users
   - Script compliance feature

**Definition of Done:**
- [ ] Demo script reviewed and rehearsed
- [ ] Pre-flight checklist all green
- [ ] Phase 2 roadmap ready for Q&A
- [ ] Demo content files validated against demo script
- [ ] Backup plan documented

---

## Testing Strategy

- **Unit tests:** pytest, ~50 tests covering parsers, chunkers, RAG, LLM, audio processing, session management
- **Integration tests:** pytest + fixtures, ~20 tests covering pipeline stages with mocked external APIs
- **E2E (simulated):** Full pipeline with real SaluteSpeech + real LLM, ~10 tests with pre-recorded audio
- **Extension tests:** Manual verification of all 6 widget states, audio capture, upload flow
- **Demo rehearsal:** Full 15-minute live call simulation day before demo

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SaluteSpeech Russian accuracy insufficient | Medium | High | Test with 5 sample recordings day 1. Fallback: Deepgram Nova-3 |
| SaluteSpeech streaming latency too high | **High** | **Critical** | **No published latency data.** Benchmark day 1. If >500ms, switch to Deepgram Nova-3 (~200ms final) |
| GPT-4.1-mini too slow as fallback | Medium | High | Output speed 64-79 tok/s vs 248 tok/s Gemini. Consider Gemini 2.5 Flash-Lite (~250ms TTFT) as faster fallback |
| Total pipeline exceeds 2s budget | Medium | High | Speculative RAG + LLM streaming reduce visual latency to ~700-1000ms. Pre-warm OpenRouter |
| AudioWorklet CSP issues in offscreen doc | Medium | Medium | Use relative path from offscreen context, test early |
| Chrome tabCapture fails on Mizugate | Low | Critical | Test on actual Mizugate page day 1, not day 5 |
| OpenRouter rate limits during demo | Low | High | Pre-cache top 10 objection responses. Keep demo under 12 min |
| Widget CSS conflicts with SberCRM | Low | Medium | Shadow DOM isolation. Test on actual page before demo |
| gRPC dependency complexity | Medium | Medium | If gRPC too complex for MVP, use SaluteSpeech REST endpoint (higher latency) |

## Open Questions
- SaluteSpeech gRPC proto files — optional (Deepgram is primary), obtain from Sber developer portal if SaluteSpeech testing needed
- Exact Mizugate URL pattern — need from the team
- Demo content files — who creates them, deadline day 3
- Deepgram Russian accuracy — benchmark day 1 with 5 sample recordings

---
**USER: Please review this plan. Edit any section directly, then confirm to proceed.**
