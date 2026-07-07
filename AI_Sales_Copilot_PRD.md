# AI Sales Copilot — Product Requirements Document

**MVP "Demo-Ready" for SberCRM**

| Parameter | Value |
|-----------|-------|
| Product | AI Sales Copilot (Chrome Extension + Backend) |
| Target | Hack/Demo for SberCRM Leadership |
| Goal | Demo-ready MVP in 2 weeks |
| Author | Prospero / Technology Director |
| Version | 1.0 — February 2026 |
| Status | DRAFT |

---

## 1. Vision & Strategic Context

AI Sales Copilot is a real-time intelligent layer that sits on top of the browser, turning any sales representative into an expert negotiator. The system does not simply transcribe calls — it anticipates the salesperson's needs based on deal context, corporate knowledge base, and live conversation dynamics.

### 1.1 Problem Statement

Sales reps at Sber's Corporate Investment Block handle complex B2B products with multi-page tariff grids, SLA matrices, and competitor comparisons. During live calls, they frequently cannot recall exact figures, fumble on objection handling, and miss cross-sell opportunities. This results in longer sales cycles, lower win rates, and inconsistent customer experience.

### 1.2 Solution

A Chrome Extension that provides three capabilities in a single overlay widget:

- **Pre-call Briefing:** AI-generated buyer portrait and negotiation strategy from uploaded documents
- **Real-time Prompter:** Sub-2-second contextual hints during live SIP calls with source attribution
- **Emotional & Pacing Support:** Sentiment analysis and tempo coaching for the salesperson

### 1.3 Success Criteria for Demo

| Metric | Target | How We Measure |
|--------|--------|----------------|
| Hint latency | < 2 sec from end of client phrase | Stopwatch during demo call |
| RAG accuracy | 9/10 hints cite correct source | Manual check against uploaded docs |
| Diarization accuracy | 100% speaker separation | Stereo channel split (no ML needed) |
| Widget stability | Zero crashes during 15-min call | Full demo walkthrough |
| Wow-factor | Boss says "When can we ship this?" | Qualitative |

---

## 2. Golden Path: Demo Scenario

This is the single scenario that must work flawlessly. Every engineering decision serves this path.

### 2.1 Phase 1: Ingestion

**Actor:** Sales rep (demo presenter)

**Action:** Opens the extension popup and uploads 3 files via drag-and-drop:

1. PDF with tariff plans (e.g., `Tariffs_2026_Q1.pdf`)
2. Excel with competitor comparison matrix (e.g., `Competitors.xlsx`)
3. Text/Markdown file with CRM notes about the client (e.g., `Client_Ivanov.md`)

**System:** Files are sent to the backend, chunked, embedded, and indexed in the vector DB. A progress bar shows completion. Total time target: < 30 seconds for 50 pages.

> ✅ **Acceptance test:** Upload 3 files totaling 50 pages. Index completes in < 30s. No errors in console.

### 2.2 Phase 2: Pre-call Briefing

**Actor:** Sales rep clicks "Prepare for Call" button

**System generates:**

- **Buyer Portrait:** "Ivan Ivanovich, CTO. Conservative buyer. Prioritizes reliability and 24/7 support. Will push for discounts. Sensitive to downtime metrics."
- **Negotiation Strategy:** "Don't offer discounts first. Lead with IT department time savings. If he mentions competitors, pivot to SLA comparison."
- **Top 3 likely objections** with prepared responses

> ✅ **Acceptance test:** Portrait and strategy appear within 5 seconds. Content references actual uploaded data.

### 2.3 Phase 3: The Call

**Actor:** Sales rep opens Mizugate (Web-SIP) in a browser tab and initiates a call

**System:** Extension detects the active SIP tab, captures two audio channels (mic = sales rep, tab audio = client), and starts streaming to the backend. The overlay widget appears as a semi-transparent panel on the right side of the screen.

> ✅ **Acceptance test:** Widget appears. Audio capture starts. No browser permission dialogs during the call (pre-flight check completed).

### 2.4 Phase 4: Real-time Support

During the live call, the widget provides three types of assistance:

#### 2.4.1 Contextual Hints (triggered by client speech)

| Client Says | Widget Shows | Source |
|-------------|-------------|--------|
| "What if our database crashes? How fast can you recover?" | "RTO is 15 minutes under SLA Gold. Mention our backup data centers in Kazakhstan." | `[Tariffs_2026_Q1.pdf, p.12]` |
| "Your competitor offers this for 30% less" | "Competitor X doesn't include 24/7 support in base price. Their SLA recovery is 4 hours vs our 15 min. Show the comparison table." | `[Competitors.xlsx, row 15]` |
| "We need a custom integration with SAP" | "We have a certified SAP connector. Implementation takes 2 weeks. Mention the Gazprom case study." | `[Client_Ivanov.md]` |

#### 2.4.2 Emotional Boost (triggered by sentiment analysis)

| Situation | Widget Shows | Color |
|-----------|-------------|-------|
| Sales rep gave a strong answer | "Excellent answer! He'll push on price next — be ready." | 🟢 GREEN |
| Client's tone is getting aggressive | "Soften your tone. Don't argue. Acknowledge his concern first." | 🟡 YELLOW |
| Sales rep talks too fast / too long | "Slow down. Let the client respond." | 🟡 YELLOW |
| Sales rep contradicts uploaded data | "WARNING: You quoted 99.9% but SLA says 99.5%. Correct yourself." | 🔴 RED |

#### 2.4.3 Script Compliance Check

If a sales script was uploaded, the system tracks which key phrases/topics have been covered and shows a checklist. At the end of the call, uncovered topics are highlighted.

> ✅ **Acceptance test:** During a 10-min demo call, widget provides 5+ relevant hints with < 2s latency. Zero hallucinated facts.

---

## 3. Technical Architecture

The MVP uses a pragmatic monolithic backend with an async pipeline. Layers are architecturally separated for future microservice extraction.

### 3.1 System Diagram

```
┌─────────────────────────────────────────────────┐
│            Chrome Extension (Manifest V3)        │
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ Content   │  │ Offscreen    │  │ Service   │  │
│  │ Script:   │  │ Document:    │  │ Worker:   │  │
│  │ Shadow DOM│  │ Audio Capture│  │ Router &  │  │
│  │ Widget    │  │ & Stereo Mix │  │ Auth      │  │
│  └─────┬─────┘  └──────┬───────┘  └─────┬─────┘  │
└────────┼───────────────┼────────────────┼────────┘
         │               │                │
         └───────────────┼────────────────┘
                         │ WebSocket (Full-Duplex)
                         ▼
┌─────────────────────────────────────────────────┐
│          Backend Orchestrator (FastAPI)           │
│                                                   │
│  Audio ──► VAD ──► STT ──► RAG ──► LLM ──► Hint │
│  Stream   Silero  Deepgram  Hybrid  Groq/   JSON  │
│                   Nova-2    Search  GPT-4o        │
│                                                   │
│  ┌─────────────┐  ┌─────────────┐                │
│  │ Redis       │  │ ChromaDB    │                │
│  │ Session     │  │ Vector DB   │                │
│  │ State       │  │ + BM25      │                │
│  └─────────────┘  └─────────────┘                │
└─────────────────────────────────────────────────┘
```

### 3.2 System Components

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Chrome Extension | Manifest V3 (Content Script + Offscreen Document + Service Worker) | Offscreen Document enables audio capture without visible UI. Shadow DOM isolates widget styles from host page. |
| Transport | WebSocket (Socket.IO) | Full-duplex, low-latency. Auto-reconnect built-in. Fallback to long-polling. |
| Backend Orchestrator | FastAPI (Python 3.11+) | Native async, WebSocket support, easy prototyping. Single deployment unit for MVP. |
| Voice Activity Detection | Silero VAD (local, on backend) | Filters noise, coughs, silence before sending to STT. Reduces API costs and false triggers. |
| Speech-to-Text | Deepgram Nova-2 (Streaming API) | Sub-second interim results. Built-in language detection. Speaker diarization as fallback. |
| RAG Engine | LangChain + ChromaDB (local) | Hybrid search (keyword + semantic). Zero external dependencies for demo. |
| LLM | Groq (Llama 3 70B) PRIMARY / GPT-4o-mini FALLBACK | Groq: ~200ms TTFT. GPT-4o-mini: ~500ms. Both adequate for < 2s total latency. |
| State Management | Redis | Stores session context: last 10 utterances, conversation summary, active hint. TTL = session duration. |
| File Storage | Local filesystem (MVP) / S3 (production) | Uploaded PDFs, Excel files, processed chunks. |

### 3.3 Data Flow Pipeline

The real-time pipeline processes audio in a streaming chain. Each stage is asynchronous and does not block the next:

1. **CAPTURE:** Offscreen Document captures two separate audio streams (mic channel + tab audio channel) and interleaves them into a stereo WebSocket frame
2. **TRANSPORT:** Service Worker routes the stereo frame to the backend via WebSocket
3. **VAD:** Silero VAD runs on each channel independently, filtering silence and noise
4. **STT:** Deepgram Streaming API receives active audio, returns interim + final transcripts tagged by channel (`sales_rep` / `client`)
5. **CONTEXT:** Session Manager (Redis) appends the transcript to the sliding window (last 10 utterances) and updates the running conversation summary
6. **RAG:** On each client utterance marked as `final`, the RAG engine performs hybrid search against the indexed knowledge base
7. **LLM:** The prompt is assembled from: system instructions + conversation summary + last 5 utterances + RAG results (top 3 chunks with source attribution). The LLM generates a hint.
8. **DELIVER:** The hint is pushed back through WebSocket to the Service Worker, which forwards it to the Content Script widget

> **Critical latency budget:** Capture (10ms) + Transport (50ms) + VAD (20ms) + STT (500ms) + RAG (200ms) + LLM (500ms) + Deliver (50ms) = **~1330ms total**

### 3.4 Speaker Separation Strategy

This is the most critical technical decision in the MVP. We do NOT use ML-based diarization (too slow, too inaccurate for real-time).

**Solution: Hardware-level stereo separation**

- The Offscreen Document captures two independent audio streams using the Web Audio API
- **Channel 1 (Left):** `navigator.mediaDevices.getUserMedia()` — microphone (sales rep)
- **Channel 2 (Right):** `chrome.tabCapture.capture()` — tab audio (client's voice from SIP)
- Both channels are merged into a single stereo AudioBuffer and streamed as interleaved PCM16
- The backend splits channels and processes them independently
- **Result:** 100% accurate speaker separation with zero ML overhead

> ✅ **Acceptance test:** In a test call, all client utterances are tagged as "client" and all rep utterances as "sales_rep". Zero cross-contamination.

---

## 4. Module Specifications

### 4.1 Module: Knowledge Base (RAG)

#### 4.1.1 Ingestion Pipeline

1. File upload via extension popup (drag-and-drop). Accepted formats: PDF, XLSX, XLS, DOCX, MD, TXT
2. Backend receives files, extracts text (PyMuPDF for PDF, openpyxl for Excel, python-docx for DOCX)
3. Text is split into chunks: 512 tokens with 64-token overlap. Tabular data (tariffs, prices) is chunked by row/section, not by token count
4. Each chunk is embedded using a local embedding model (e.g., `sentence-transformers/all-MiniLM-L6-v2`)
5. Chunks + embeddings are stored in ChromaDB with metadata: `{source_file, page_number, section_title, chunk_type: "text" | "table" | "list"}`
6. Top 10 most common objections are pre-loaded into Redis (in-memory cache) for zero-latency retrieval during calls

#### 4.1.2 Retrieval Strategy

**Hybrid Search:** Every query runs both keyword (BM25) and semantic (cosine similarity) search. Results are merged using Reciprocal Rank Fusion (RRF).

Rationale: For pricing data ("Gold plan", "SLA 99.5%", "$500/month"), keyword search is more reliable than pure semantic search. For open-ended questions ("How do you handle disaster recovery?"), semantic search wins. Hybrid gives us both.

**Source Attribution:** Every hint displayed in the widget MUST include a source reference: `[filename, page/row]`. This is non-negotiable — it protects the sales rep from hallucinated data and builds trust with the demo audience.

### 4.2 Module: Audio Processing

| Component | Technology | Config | Why |
|-----------|-----------|--------|-----|
| Audio Capture | Offscreen Document (`chrome.offscreen`) | 48kHz, stereo, PCM16 | Invisible to user. Captures mic + tab. |
| VAD | Silero VAD | Threshold: 0.5, min_speech: 250ms | Filters noise. Prevents STT from processing silence. |
| STT | Deepgram Nova-2 (Streaming) | `interim_results: true, language: ru, punctuate: true` | Best Russian support. Sub-500ms latency. |
| Sentiment | LLM-based (in prompt) | Analyzed on each "final" transcript | No separate model needed for MVP. LLM judges tone from text. |

### 4.3 Module: LLM Prompt Engineering

The LLM receives a structured prompt on every client utterance:

```
[SYSTEM]
You are a real-time sales assistant for Sber CIB.
Your task: generate a SHORT (1–2 sentences) actionable hint for the sales rep.
Rules:
  1) ONLY use facts from [KNOWLEDGE_BASE]. 
  2) Cite source. 
  3) If unsure, say "No data found".
  4) Assess client sentiment: POSITIVE / NEUTRAL / NEGATIVE.
  5) If sales rep made an error vs knowledge base, flag it as WARNING.

[BUYER_PORTRAIT] {generated_portrait}
[STRATEGY] {generated_strategy}
[KNOWLEDGE_BASE] {rag_results_with_sources}
[CONVERSATION_SUMMARY] {rolling_summary}
[LAST_5_UTTERANCES] {tagged_by_speaker}
[CLIENT_JUST_SAID] {latest_utterance}
```

**Output format (JSON):**

```json
{
  "hint": "...",
  "source": "file.pdf, p.12",
  "sentiment": "NEGATIVE",
  "coaching": "Soften your tone",
  "warning": null,
  "color": "YELLOW"
}
```

### 4.4 Module: Widget UI/UX

#### 4.4.1 Widget States

| State | Visual | Trigger |
|-------|--------|---------|
| Idle | Collapsed pill, shows "AI Ready" in gray | No active call detected |
| Listening | Expanded panel, subtle pulsing blue border | Audio capture active |
| Hint Active | Hint text with source badge, colored border | LLM returned a hint |
| Warning | Red border, bold text, shake animation | Sales rep error or client anger |
| Disconnected | Gray overlay, "Reconnecting..." text | WebSocket lost |
| Briefing | Full panel with portrait + strategy cards | "Prepare" button clicked |

#### 4.4.2 Color System

| Color | Hex | Meaning |
|-------|-----|---------|
| Green | `#27AE60` | Positive: good answer, client engaged, on-script |
| Yellow | `#F39C12` | Attention: objection detected, pacing issue, client hesitant |
| Red | `#E74C3C` | Alert: factual error, client angry, script violation |
| Blue | `#2E75B6` | Informational: neutral hint, data lookup result |
| Gray | `#95A5A6` | System: disconnected, loading, idle |

#### 4.4.3 Shadow DOM Requirement

The widget MUST render inside a Shadow DOM to prevent CSS conflicts with the host page (SberCRM, Mizugate, or any other SIP client). No styles from the host page should leak into the widget, and no widget styles should affect the host page.

---

## 5. Edge Cases & Failure Modes

Every edge case below must have an automated test. The goal is zero manual debugging during demo preparation.

| # | Scenario | Expected Behavior | Test Method |
|---|----------|-------------------|-------------|
| E1 | Cross-talk (both speak simultaneously) | Prioritize client channel for objection detection. Buffer sales rep channel. Resume normal processing when cross-talk ends. | Automated: play overlapping audio files through both channels |
| E2 | LLM hallucination (hint contradicts KB) | Widget shows hint with source. If source is "none" or confidence < 0.7, display: "No verified data. Check manually." | Automated: send query with no matching KB content, verify fallback message |
| E3 | Context drift (20+ min call) | Session Manager maintains rolling summary (updated every 2 min). Last 10 utterances + summary are always in prompt. | Automated: simulate 30-min conversation, verify hint at minute 25 references data from minute 3 |
| E4 | WebSocket disconnect | Widget turns gray, shows "Reconnecting...". Auto-reconnect with exponential backoff (1s, 2s, 4s, max 30s). On reconnect, re-sync session state from Redis. | Automated: kill WS connection mid-call, verify reconnect < 5s |
| E5 | Microphone permission denied | Pre-flight check on extension activation. If denied, show clear error: "Microphone access required. Click here to enable." Block call start. | Automated: mock permission denial, verify error UI |
| E6 | Tab audio capture blocked | Same pre-flight check. Clear error with instructions. Offer fallback: "Use single-channel mode (your mic only, no client separation)." | Automated: mock tabCapture failure, verify fallback mode |
| E7 | Client speaks different language | Deepgram auto-detects language. Hint is always generated in Russian (sales rep's language). Client's speech is translated if needed. | Automated: send English audio on client channel, verify Russian hint |
| E8 | Heavy background noise | VAD filters non-speech. If VAD detects no speech for 10s, widget shows "Waiting for speech..." instead of processing noise. | Automated: send white noise, verify no STT calls triggered |
| E9 | File upload fails (corrupt/protected) | Backend returns specific error: "Cannot read file: password protected" or "Unsupported format". Widget shows retry option. | Automated: upload corrupt and password-protected files, verify error messages |
| E10 | LLM API rate limit / timeout | Fallback to cached objection responses (pre-loaded in Redis). Widget shows hint with "[cached]" badge. | Automated: mock LLM 429/timeout, verify cached response delivery |

---

## 6. Testing Strategy

**Core principle:** If it is not tested automatically, it will break during the demo. No exceptions.

### 6.1 Test Pyramid

| Layer | Scope | Count | Tool | Run Time |
|-------|-------|-------|------|----------|
| Unit | Individual functions: chunking, embedding, prompt assembly, response parsing | ~50 tests | pytest | < 30s |
| Integration | Pipeline stages: STT mock → RAG → LLM mock → response format | ~20 tests | pytest + fixtures | < 2 min |
| E2E (Simulated) | Full pipeline with recorded audio → real STT → real RAG → real LLM | ~10 tests | pytest + Deepgram sandbox | < 5 min |
| E2E (Manual) | Live demo rehearsal with real SIP call | 1 full scenario | Human (demo day -1) | 15 min |

### 6.2 Automated Test Scenarios

#### 6.2.1 RAG Tests

1. `test_rag_exact_match`: Upload tariff PDF. Query "What is the RTO for SLA Gold?". Assert response contains "15 minutes" and source is `Tariffs_2026_Q1.pdf`.
2. `test_rag_semantic_match`: Query "How quickly do you recover from a crash?". Assert same result as above (semantic similarity to "RTO").
3. `test_rag_no_match`: Query "What is the color of the CEO's car?". Assert response is "No relevant data found."
4. `test_rag_table_data`: Upload Excel. Query "What does Competitor X charge for enterprise?". Assert response extracts correct row/cell.
5. `test_rag_hybrid_superiority`: Query "Gold plan $500". Assert keyword search finds exact match that semantic search misses.

#### 6.2.2 Pipeline Latency Tests

- `test_latency_hint_generation`: Send a pre-recorded 5-second audio clip through the full pipeline. Assert total time from audio end to hint delivery is < 2000ms.
- `test_latency_vad_filtering`: Send 10 seconds of silence + 3 seconds of speech. Assert STT is only called on the speech segment.
- `test_latency_llm_fallback`: Mock primary LLM timeout (3s). Assert fallback LLM responds within 1.5s.

#### 6.2.3 Widget State Tests (Playwright)

1. `test_widget_idle_state`: Load extension on a page. Assert widget shows "AI Ready" in gray.
2. `test_widget_hint_display`: Send mock hint via WebSocket. Assert hint text, source badge, and border color appear correctly.
3. `test_widget_disconnect_state`: Kill WebSocket. Assert widget turns gray with "Reconnecting..." text within 1s.
4. `test_widget_shadow_dom_isolation`: Inject CSS on host page (e.g., `* { color: red !important }`). Assert widget text color is unaffected.
5. `test_widget_pre_flight_check`: Mock microphone permission as denied. Assert error message appears and "Start Call" button is disabled.

---

## 7. Repository Structure

```
ai-sales-copilot/
├── extension/                    # Chrome Extension (Manifest V3)
│   ├── manifest.json
│   ├── popup/                    # Extension popup (file upload UI)
│   │   ├── popup.html
│   │   ├── popup.js
│   │   └── popup.css
│   ├── content/                  # Content Script (Widget)
│   │   ├── widget.js             # Shadow DOM widget renderer
│   │   └── widget.css            # Widget styles (inside shadow)
│   ├── offscreen/                # Audio Capture
│   │   ├── offscreen.html
│   │   └── audio-capture.js      # Stereo mix: mic + tab
│   └── background/
│       └── service-worker.js     # WS routing, auth, state
├── backend/                      # FastAPI Backend
│   ├── main.py                   # FastAPI app, WS endpoints
│   ├── config.py                 # Environment config
│   ├── pipeline/
│   │   ├── vad.py                # Silero VAD wrapper
│   │   ├── stt.py                # Deepgram streaming client
│   │   ├── rag.py                # Hybrid search engine
│   │   ├── llm.py                # LLM client (Groq + fallback)
│   │   └── orchestrator.py       # Pipeline coordinator
│   ├── ingestion/
│   │   ├── parser.py             # PDF, Excel, DOCX parsers
│   │   ├── chunker.py            # Smart chunking logic
│   │   └── embedder.py           # Embedding + ChromaDB index
│   ├── briefing/
│   │   └── portrait.py           # Buyer portrait generator
│   ├── session/
│   │   └── manager.py            # Redis session state
│   └── tests/
│       ├── test_rag.py
│       ├── test_pipeline.py
│       ├── test_latency.py
│       ├── test_edge_cases.py
│       └── fixtures/             # Pre-recorded audio, mock docs
├── docs/
│   ├── PRD.md
│   └── DEMO_SCRIPT.md            # Step-by-step demo playbook
├── docker-compose.yml            # Backend + Redis + ChromaDB
├── Makefile                      # dev, test, demo commands
└── README.md
```

---

## 8. Constraints & Non-Goals

### 8.1 MVP Scope Constraints

| Constraint | Detail |
|------------|--------|
| Single concurrent user | No multi-tenancy. One session at a time. |
| Russian language only (primary) | STT and LLM prompts optimized for Russian. English supported as fallback via Deepgram auto-detect. |
| Chrome only | No Firefox, Safari, Edge support in MVP. |
| No persistent storage | Session data lives in Redis with TTL. No database for call history. |
| No authentication | MVP runs on localhost or internal network. Auth added post-demo. |
| Demo duration: 15 minutes max | Pipeline optimized for 15-min calls. Longer calls may degrade context quality. |

### 8.2 Explicit Non-Goals

- Call recording and playback
- CRM integration (data write-back)
- Team analytics dashboard
- Mobile support
- Multi-language UI
- GDPR/PD compliance (handled post-MVP)
- Custom model training / fine-tuning

---

## 9. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Deepgram Russian accuracy < 90% | High — bad transcripts = bad hints | Medium | Test with 10 sample recordings before committing. Fallback: Whisper large-v3 (higher latency but better accuracy). |
| Groq rate limits during demo | High — no hints | Low | GPT-4o-mini as automatic fallback. Pre-cache top 10 objection responses. |
| Chrome blocks tab audio capture | Critical — no client voice | Low | Test on exact Chrome version. Use tabCapture permission in manifest. Have fallback: single-channel mode. |
| Boss asks an out-of-scope question | Medium — LLM hallucinates | High | Hard rule: if RAG returns no match, LLM MUST say "No data in knowledge base". Coach demo audience to use prepared questions. |
| Widget CSS conflicts with SberCRM | Medium — broken UI | Low | Shadow DOM isolates styles. Test on actual SberCRM page before demo. |
| Network latency in office | High — slow hints | Medium | Run backend on localhost for demo. Pre-warm all API connections. |

---

## 10. Implementation Timeline (2 Weeks)

| Day | Sprint | Deliverable | Exit Criteria |
|-----|--------|-------------|---------------|
| 1–2 | Infrastructure | Docker compose (FastAPI + Redis + ChromaDB). Extension scaffold with manifest.json. WebSocket connection working. | Backend starts. Extension loads in Chrome. WS ping-pong works. |
| 3–4 | Ingestion + RAG | File upload UI. Parser pipeline. Chunking + embedding. ChromaDB indexing. Hybrid search. | Upload PDF, query via API, get correct answer with source. |
| 5–6 | Audio Pipeline | Offscreen audio capture (stereo). VAD. Deepgram streaming integration. Transcript tagged by speaker. | Record test call. Verify separate channels. STT returns accurate text. |
| 7–8 | LLM + Hints | Prompt engineering. Groq/GPT-4o-mini integration. Hint generation with source attribution. Fallback logic. | Send transcript + RAG context, get hint < 2s. Fallback works on timeout. |
| 9–10 | Widget UI | Shadow DOM widget. All states (idle, listening, hint, warning, disconnected). Color system. Animations. | Widget renders on any page. Hint display matches spec. No CSS leaks. |
| 11 | Pre-call Briefing | Portrait generation. Strategy generation. Briefing panel UI. | Upload docs + click Prepare = portrait + strategy in < 5s. |
| 12–13 | Integration + Testing | Full pipeline end-to-end. All automated tests green. Edge case handling. | All tests pass. 15-min simulated call completes without errors. |
| 14 | Demo Rehearsal | Full dress rehearsal with real SIP call. Bug fixes. Demo script finalized. | Boss-ready demo. Script printed. Backup plan documented. |

---

## 11. Demo Script (Minute-by-Minute)

This is the exact script for the 12-minute demo presentation. Practice it at least twice.

| Time | Action | What Audience Sees | Talking Points |
|------|--------|--------------------|----------------|
| 0:00–0:30 | Open Chrome. Show empty extension popup. | Clean UI with drag-and-drop zone. | "This is our AI Sales Copilot. Right now it knows nothing. Let's teach it." |
| 0:30–1:30 | Drag 3 files into popup. Click "Index". | Progress bar. "Indexed 47 pages in 12 seconds." | "I just uploaded our tariffs, competitor matrix, and CRM notes. The AI has read everything." |
| 1:30–3:00 | Click "Prepare for Call". | Buyer portrait card + strategy card appear. | "Before I even pick up the phone, the AI tells me: Ivan is a conservative buyer, will push on price, and cares about uptime. My strategy: lead with reliability, not discounts." |
| 3:00–3:30 | Open Mizugate tab. Click "Start Call". | Widget pulses blue. "Listening..." | "Now I'm calling Ivan. Watch the right side of the screen." |
| 3:30–7:00 | Live call with prepared "client" (colleague). | Real-time hints appearing with sources. | Let the demo speak for itself. Client asks 3–4 prepared questions from the uploaded docs. |
| 7:00–8:00 | Client asks the "killer question" not in docs. | Widget shows: "No verified data. Answer carefully." | "See? The AI doesn't hallucinate. It tells me honestly when it doesn't know." |
| 8:00–9:00 | Client gets "angry" (raise voice). | Widget turns YELLOW: "Soften your tone." | "It even reads the room. Emotional intelligence built in." |
| 9:00–10:00 | Intentionally say wrong SLA number. | Widget turns RED with warning. | "And if I make a mistake, it catches me before the client does." |
| 10:00–11:00 | End call. Widget generates follow-up email draft. | Email with key discussion points. | "After the call, it writes the follow-up for me. Every claim is sourced." |
| 11:00–12:00 | Q&A | — | "Questions?" |

---

## Appendix A: API Contracts

### A.1 WebSocket Messages

All WebSocket communication uses JSON. Direction: C = Client (extension), S = Server (backend).

| Direction | Event | Payload | Description |
|-----------|-------|---------|-------------|
| C → S | `audio_chunk` | `{channel: "stereo", data: base64_pcm16, seq: int}` | Raw audio frame, ~100ms per chunk |
| C → S | `session_start` | `{session_id: str, files: [str]}` | Begin new call session |
| C → S | `session_end` | `{session_id: str}` | End call session |
| S → C | `transcript` | `{speaker: "client"\|"rep", text: str, is_final: bool}` | Real-time transcript update |
| S → C | `hint` | `{text: str, source: str, sentiment: str, coaching: str, color: str, warning: str\|null}` | AI-generated hint |
| S → C | `briefing` | `{portrait: str, strategy: str, objections: [{q: str, a: str}]}` | Pre-call briefing result |
| S → C | `error` | `{code: str, message: str}` | Error notification |
| S → C | `status` | `{state: "listening"\|"processing"\|"reconnecting"}` | Pipeline state update |

### A.2 REST Endpoints

| Method | Path | Body | Response | Purpose |
|--------|------|------|----------|---------|
| POST | `/api/v1/upload` | multipart/form-data (files) | `{status, files_indexed, chunks_count, time_ms}` | Upload and index documents |
| POST | `/api/v1/briefing` | `{session_id}` | `{portrait, strategy, objections}` | Generate pre-call briefing |
| GET | `/api/v1/health` | — | `{status, redis, chromadb, deepgram, llm}` | Health check (all dependencies) |
| DELETE | `/api/v1/session/{id}` | — | `{status}` | Clear session data |

---

## Appendix B: Environment Variables

| Variable | Example | Required |
|----------|---------|----------|
| `DEEPGRAM_API_KEY` | `dg-xxxx` | Yes |
| `GROQ_API_KEY` | `gsk_xxxx` | Yes |
| `OPENAI_API_KEY` | `sk-xxxx` | Yes (fallback) |
| `REDIS_URL` | `redis://localhost:6379` | Yes |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | Yes |
| `LLM_PRIMARY` | `groq` | No (default: groq) |
| `LLM_TIMEOUT_MS` | `2000` | No (default: 2000) |
| `VAD_THRESHOLD` | `0.5` | No (default: 0.5) |
| `LOG_LEVEL` | `INFO` | No (default: INFO) |
