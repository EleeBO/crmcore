# Repository structure

Annotated tree of the AI Sales Copilot repo. Counts and notes are accurate as of the most recent commit on `main`.

```
crmcore/
├── backend/                 ← Python 3.11 FastAPI service (uv-managed)
│   ├── main.py              FastAPI composition root: lifespan (Redis), router wiring, /ws endpoint
│   ├── config.py            pydantic-settings — reads backend/.env, single Settings class
│   ├── logger.py            loguru setup; project standard is f-strings (no %s)
│   ├── errors.py            shared exception types
│   ├── api/                 REST endpoints
│   │   ├── health.py        liveness + dependency checks
│   │   ├── upload.py        knowledge-base file upload (PDF / XLSX / MD)
│   │   ├── session.py       session lifecycle helpers
│   │   ├── briefing.py      pre-call briefing (RAG over uploaded docs)
│   │   ├── summarize.py     post-call summary
│   │   └── evaluation.py    /api/v1/evaluation — call scoring + follow-up
│   ├── ws/
│   │   └── handler.py       WebSocket handler — receives audio frames, owns orchestrator,
│   │                        handles session_start / session_end / test_mode control frames
│   ├── pipeline/            real-time + post-call processing
│   │   ├── orchestrator.py  per-session pipeline: STT → talk-ratio → hint LLM, evaluation kick-off
│   │   ├── stt.py           STT provider façade (Deepgram / SaluteSpeech / Yandex), select_stt()
│   │   ├── salutespeech/    gRPC client + generated _pb2 stubs (gitignored ruff/mypy)
│   │   ├── yandexstt/       Yandex streaming gRPC stubs
│   │   ├── yandexstt_async/ Yandex async (post-call diarization) gRPC stubs
│   │   ├── yandex_async.py  high-level Yandex async recognition wrapper
│   │   ├── audio.py         frame routing
│   │   ├── audio_buffer.py  per-channel ring buffer
│   │   ├── vad.py           voice-activity gate
│   │   ├── llm.py           OpenRouter client, primary + fallback, fence stripping
│   │   ├── shared_llm.py    shared LLM helpers (timeouts, retries)
│   │   ├── prompt_formatter.py  hint-prompt assembly
│   │   ├── schemas.py       SGR Pydantic schemas — HintResponseV2, etc.
│   │   ├── talk_ratio.py    TalkRatioTracker — manager/client % + waveform ring buffer
│   │   ├── scenario.py      scenario fast-path (rule-based hint when LLM is slow)
│   │   ├── evaluator.py     post-call rubric scoring
│   │   ├── evaluator_llm.py LLM evaluator (Pydantic-typed verdict)
│   │   ├── evaluation_runner.py  orchestrates evaluation + follow-up generation
│   │   ├── evaluation_schemas.py SGR schemas for evaluation outputs
│   │   ├── post_call.py     async diarization + transcript reprocessing
│   │   ├── protocols.py     duck-typed STT / LLM protocols
│   │   └── types.py         shared dataclasses (Transcript, Utterance, ...)
│   ├── briefing/
│   │   ├── portrait.py      builds buyer portrait + strategy from uploaded KB
│   │   └── models.py        SGR models for BriefData (camelCase aliases for FE contract)
│   ├── ingestion/
│   │   ├── parser.py        PDF/XLSX/MD parsers
│   │   └── chunker.py       semantic chunking for vector DB
│   ├── summarize/
│   │   └── call_summary.py  short summary post-call
│   ├── session/
│   │   └── manager.py       Redis-backed session state
│   ├── storage/             ChromaDB persistence wrappers
│   ├── tests/               pytest suite — ≈370 tests
│   │   ├── test_pipeline.py        orchestrator
│   │   ├── test_llm.py             LLM client + fence stripping
│   │   ├── test_schemas.py         HintResponseV2 + BriefData
│   │   ├── test_talk_ratio.py      ring buffer + percentages
│   │   ├── test_briefing.py        RAG end-to-end
│   │   ├── test_stt.py             provider façade
│   │   ├── test_ws_handler.py      WebSocket lifecycle
│   │   ├── test_salutespeech_*.py  SaluteSpeech (some integration, gated by env)
│   │   ├── test_yandex_*.py        Yandex (some integration)
│   │   ├── test_audio.py / test_ingestion.py / test_edge_cases.py
│   │   └── ...
│   ├── certs/
│   │   └── russian_trusted_root_ca.pem  public Russian root CA, required for SaluteSpeech mTLS
│   ├── chroma_data/         (gitignored) local vector index
│   ├── logs/                (gitignored) loguru output
│   ├── Dockerfile
│   └── pyproject.toml       backend-specific extras (e.g. salutespeech)
│
├── extension/               ← Chrome MV3 extension (TypeScript, Preact)
│   ├── manifest.json        v0.7.x — sidePanel / offscreen / tabCapture / activeTab
│   ├── src/
│   │   ├── background/
│   │   │   └── service-worker.ts  capture orchestration, port routing, badge state
│   │   ├── offscreen/
│   │   │   ├── offscreen.html
│   │   │   └── offscreen.ts       getUserMedia + tabCapture + WS streaming
│   │   ├── audio-worklet.ts       PCM resample + VU level emit
│   │   ├── permissions/
│   │   │   ├── permissions.html / permissions.ts   pre-flight permission grant flow
│   │   ├── lib/
│   │   │   └── ws-client.ts       WebSocket client (reconnect, lifecycle)
│   │   ├── shared/
│   │   │   ├── constants.ts       BACKEND_HTTP_URL / BACKEND_WS_URL / API_BASE
│   │   │   ├── messages.ts        WS payload types (WsHintEnd, WsTranscript, …)
│   │   │   ├── evaluation-types.ts  evaluation/follow-up wire types
│   │   │   └── types.ts
│   │   ├── sidepanel/
│   │   │   ├── sidepanel.html / sidepanel.css
│   │   │   ├── sidepanel.ts       host (~2000 LOC) — phase engine, port, capture, splitters,
│   │   │   │                      preflight, REC button, settings, mic selection
│   │   │   ├── brief/             Preact pre-call briefing (mounted via mount.ts)
│   │   │   │   ├── BriefPanel.tsx + ContactCard / FocusPoints / PainPoints /
│   │   │   │   │   RoiHighlight / ComparisonCards / ObjectionCards / ExpandButton
│   │   │   │   ├── brief.css      CSS variables design system
│   │   │   │   ├── mount.ts       isBriefDataV2 type guard + mountBriefPanel
│   │   │   │   └── types.ts
│   │   │   └── live-call/         Preact live-call panel (FEAT-013)
│   │   │       ├── LiveCallPanel.tsx   root composition
│   │   │       ├── AIHintCard.tsx      hint card with cooldown
│   │   │       ├── TalkRatioBar.tsx    bar + waveform
│   │   │       ├── TranscriptFeed.tsx + TranscriptMessage.tsx
│   │   │       ├── RecordingBar.tsx    REC button + timer + mic VU
│   │   │       ├── ConnectionStatus.tsx + ContextTabs.tsx
│   │   │       ├── live-call.css
│   │   │       ├── store.ts            @preact/signals signals
│   │   │       ├── types.ts
│   │   │       ├── hooks/useHintCooldown.ts + useAutoScroll.ts
│   │   │       ├── mount.ts            mountLiveCall / unmountLiveCall / mountRecBarDone
│   │   │       └── *.test.tsx          Vitest + Testing Library
│   │   ├── settings/
│   │   │   ├── evaluation-settings.html / .ts / .css   evaluation tuning UI
│   │   └── report/
│   │       └── report.html / .ts / .css                full-page evaluation report
│   ├── package.json         pnpm scripts: dev / build / test / typecheck
│   ├── vite.config.ts + vite.worklet.config.ts
│   ├── vitest.config.ts
│   └── tsconfig.json        strict mode
│
├── specs/                   ← Living feature specifications (FEAT-NNN format)
│   ├── registry.md          status table — DRAFT / ACTIVE / MODIFIED / DEPRECATED / ARCHIVED
│   ├── FEAT-001-context-stuffing-pipeline.md
│   ├── FEAT-002-extension-redesign.md     (audio pipeline fix)
│   ├── FEAT-003-extension-ui-redesign.md  (deprecated)
│   ├── FEAT-007-side-panel-migration.md
│   ├── FEAT-008-backend-arch-fixes.md
│   ├── FEAT-009-frontend-arch-fixes.md    sidepanel.ts split (in progress)
│   ├── FEAT-012-brief-panel-redesign.md   Preact + SGR brief panel
│   ├── FEAT-012-sgr-contract.md           Pydantic schema contract for BriefData
│   └── archive/                            retired specs
│
├── docs/                    ← Design docs, plans, architecture notes
│   ├── ARCHITECTURE.md      high-level system diagram + decisions
│   ├── AI_Sales_Copilot_Brief_Panel_Spec.md   FEAT-012 design spec
│   ├── AI_Sales_Copilot_Live_Call_Spec.md     FEAT-013 design spec
│   ├── AUDIO_FLOW_ANALYSIS.md      tab-capture + offscreen + worklet flow
│   ├── DEMO_PREFLIGHT.md / DEMO_SCRIPT.md
│   ├── PHASE2_ROADMAP.md
│   ├── SALUTESPEECH_*.md           SaluteSpeech integration / multi-utterance fix / testing
│   ├── architecture-review-2026-03-14.md
│   ├── extension-issues.md
│   ├── plans/                       implementation plans (with checkbox tracking)
│   ├── superpowers/
│   │   ├── plans/                   superpowers-style stepwise plans
│   │   └── specs/                   superpowers-style specs
│   ├── repo-stats.md
│   └── STRUCTURE.md         this file
│
├── tests/
│   └── e2e/                 end-to-end browser scenarios (agent-browser)
│
├── scripts/
│   ├── health_check.py      Redis / ChromaDB / SaluteSpeech / backend HTTP probe
│   ├── install-tools.sh     installs uv, pnpm, just, agent-browser, etc.
│   ├── copy-to-project.sh   bootstrap .claude/ into another repo
│   └── generate_yandex_async_proto.sh
│
├── .claude/                 ← Claude Code agentic workflow definitions
│   ├── agents/              role definitions (orchestrator, architect, backend, frontend, …)
│   ├── commands/            slash commands (/plan, /implement, /verify, /specify, …)
│   ├── hooks/               PreToolUse / PostToolUse hooks (TDD enforcer, etc.)
│   ├── memory/              cross-session learnings
│   ├── reviews/             archived plan reviews
│   ├── rules/standard/      coding standards, trunk/leaves, TDD, debugging, etc.
│   └── skills/              reusable knowledge modules (backend-python, frontend-react, …)
│
├── chroma_data/             (gitignored) — local ChromaDB persistence
├── test_data/               sample uploadable docs for the briefing flow
├── worktrees/               git worktrees workspace (gitignored)
│
├── docker-compose.yml       Redis only by default; backend service is opt-in
├── justfile                 unified command runner (`just --list`)
├── pyproject.toml           uv project root (deps + ruff + mypy + pytest config)
├── pytest.ini
├── uv.lock
├── CLAUDE.md                project rules for Claude Code
├── AI_Sales_Copilot_PRD.md  product requirements
├── README.md
└── .env.example, .gitignore, .mcp.json, .ai-rules.md
```

## File-count summary

| Area | Count | Notes |
|------|-------|-------|
| `extension/src/**/*.{ts,tsx}` | ~44 | Excludes `node_modules`, `dist` |
| `backend/**/*.py` (excl. proto + cache) | ~50 src | Plus generated `_pb2`/`_pb2_grpc` |
| `backend/tests/test_*.py` | ~25 | ≈370 collected pytest items |
| `specs/FEAT-*.md` | 9 | Plus `registry.md`, `archive/` |
| `docs/**/*.md` | ~25 | Architecture, plans, specs |

## Layered concerns inside `backend/pipeline/`

```
inbound audio frames (WS handler)
        │
        ▼
┌──────────────┐    ┌──────────────────┐
│ audio_buffer │───►│ vad              │  decides "speech started/stopped"
└──────────────┘    └──────────────────┘
        │
        ▼
┌──────────────────┐
│ stt (provider)   │  Deepgram / SaluteSpeech / Yandex
└──────────────────┘
        │ Transcript(text, speaker, is_final, ts)
        ▼
┌──────────────────┐
│ orchestrator     │  merges utterances, gates LLM, owns talk_ratio + scenario
└──────────────────┘
        │
        ├──► talk_ratio ──► WS:talk_ratio
        ├──► scenario   ──► WS:hint (fast-path)
        └──► llm + schemas (SGR) ──► WS:hint_end (HintResponseV2)

session_end                                    parallel
   ├──► evaluation_runner ──► evaluator_llm ──► WS:evaluation_result
   └──► evaluation_runner ──► follow-up LLM ──► WS:follow_up_ready
```

## Layered concerns inside `extension/`

```
Service Worker  ──── ports ──── Side panel host (sidepanel.ts)
   │                                 │
   │ tabCapture                      ├── Phase engine (0..4)
   │ + storage state                 ├── Port routing + WS dispatch
   │                                 ├── REC button + capture flow
   ▼                                 ├── Preflight + permissions
Offscreen document                   ├── Settings + mic selection
   ├── getUserMedia                  ├── Splitter layouts (deprecated by Preact)
   ├── audio-worklet (resample+VU)   │
   ├── PCM frames over WS            ├── mountBriefPanel  →  brief/* (Preact)
   └── WS message dispatch           └── mountLiveCall    →  live-call/* (Preact)
                                          └── @preact/signals store
```

## Conventions in this repo

- **TRUNK / LEAVES.** `backend/config.py`, `backend/main.py`, domain models, DB schema, `CLAUDE.md`, `.claude/settings.local.json` are TRUNK — don't change without a deliberate reason. Handlers, services, tests, components are LEAVES — change freely. See `.claude/rules/standard/trunk-leaves-architecture.md`.
- **Plan → Implement → Verify.** Specs live in `specs/`, plans in `docs/plans/` (or `docs/superpowers/plans/`). Plans use `- [ ]` / `- [x]` checkboxes; status fields go `PENDING → COMPLETE → VERIFIED`. See `.claude/rules/standard/workflow-enforcement.md`.
- **TDD.** A pre-tool hook checks for failing tests before allowing implementation edits. See `.claude/rules/standard/tdd-enforcement.md`.
- **Logging.** loguru, f-strings, no `%s` formatting (cleanup commits `aab5b53` / `f2e5dc9`).
- **SGR.** Pydantic schemas with `Field(description=...)` shape LLM outputs; the same schemas are mirrored as TypeScript types in `extension/src/shared/`.
