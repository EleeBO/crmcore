# Architecture Review Report

**Date:** 2026-03-14
**Scope:** Full codebase (backend + Chrome extension)
**Stack:** Python 3.11 (FastAPI, Pydantic, Redis, gRPC) + TypeScript (Chrome Extension, Vite)
**Architectural Pattern:** Modular Monolith (Layered) — no explicit Clean/Hexagonal separation
**Total LOC:** ~8,500 (backend ~5,400 + extension ~3,100)

---

## Executive Summary

| Dimension | Status | Findings |
|-----------|--------|----------|
| Dependency Direction | YELLOW | 9 violations (4 high, 3 medium, 2 low) |
| Layer Isolation | RED | No storage abstraction; raw Redis everywhere; 1 of 5 needed interfaces exists |
| Coupling | YELLOW | 2 hub modules (main.py fan-out=15, orchestrator fan-out=11) |
| Cohesion | RED | 2 God modules (sidepanel.ts 1896 LOC/56 functions, main.py 695 LOC/15 fan-out) |
| Boundary Integrity | YELLOW | 7 cross-context direct imports; 3x type duplication; no shared schema |

**Overall Health: YELLOW** (trending RED due to cohesion problems)

---

## Critical Findings (must fix)

### C1. God Module: `sidepanel.ts` (1,896 LOC, 56 functions, 22 event handlers)
**File:** `extension/src/sidepanel/sidepanel.ts`
**Impact:** Untestable, unmaintainable, impossible to reason about in isolation.

Combines 8+ distinct concerns in one file:
- Phase engine (state machine)
- Port communication with service worker
- VU meters and call timer
- Upload flow (file validation, chunking, scenario generation)
- Briefing rendering
- Hint display
- Transcript display
- Evaluation display and analytics
- Settings overlay
- Mic device selection
- Preflight status checks

**Recommendation:** Split into focused modules:
```
sidepanel/
  phase-engine.ts       (state machine, phase transitions)
  state.ts              (loadState, saveState, resetSessionState)
  port-handler.ts       (connectPort, handlePortMessage)
  upload.ts             (validateFiles, doUpload, setStep)
  briefing-renderer.ts  (renderBriefing, renderPortrait, renderStrategy)
  hint-display.ts       (showHint, renderHintCard)
  transcript-display.ts (appendTranscript, downloadTranscript)
  evaluation-display.ts (renderEvaluation, renderAnalytics)
  settings-overlay.ts   (settings UI)
  sidepanel.ts          (init orchestration, imports above modules)
```

### C2. God Function: `websocket_endpoint` (280 lines, fan-out=15)
**File:** `backend/main.py:404-685`
**Impact:** The WebSocket handler directly imports and orchestrates modules from 4 bounded contexts (STT, Session, Pipeline, Ingestion). It constructs `LLMClient`, `SessionManager`, creates STT clients, wires callbacks, and manages idle timeouts — all implementation details.

**Recommendation:** Extract a `WebSocketHandler` class or move orchestration into `PipelineOrchestrator`:
```python
# main.py should only contain:
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, ...):
    handler = WebSocketHandler(ws, config)
    await handler.run()
```

---

## High Priority Findings (should fix)

### H1. No Storage Abstraction — Raw Redis Everywhere
**Severity:** HIGH
**Files:** `main.py:25`, `session/manager.py:31`, `api/evaluation.py:18`, `briefing/portrait.py:80`, `summarize/call_summary.py:83`

Raw `redis.asyncio` client is passed as `Any` to every bounded context. No repository or storage interface exists. Changing Redis would require modifying every module.

**Recommendation:** Define a `SessionStore` Protocol in the application layer:
```python
class SessionStore(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ex: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
```

### H2. Only 1 of 5 Needed Abstract Interfaces Exists
**Severity:** HIGH
**Existing:** `STTClient(ABC)` at `pipeline/stt.py:59`
**Missing:**
- `LLMClient` Protocol (two concrete clients exist: `LLMClient`, `EvaluatorLLMClient` — no shared interface)
- `SessionStore` Protocol
- `DocumentParser` Protocol
- `AsyncRecognizer` Protocol

**Impact:** Components cannot be swapped, tested in isolation, or evolved independently.

### H3. Feature Envy: `_run_evaluation` in Orchestrator (170 LOC)
**Severity:** HIGH
**File:** `backend/pipeline/orchestrator.py:124-293`

The hint orchestrator contains 170 lines of post-call evaluation logic (diarization + eval pipeline), lazily importing 5 modules. This is a separate concern from real-time hint generation.

**Recommendation:** Extract to `backend/pipeline/evaluation_runner.py`.

### H4. Presentation → Infrastructure Violations (4 instances)
**Severity:** HIGH
**File:** `backend/main.py:412-416`

`main.py` directly imports infrastructure modules:
- `pipeline/audio_buffer` (AudioBuffer)
- `pipeline/stt` (create_stt_client)
- `pipeline/audio` (parse_frame, deinterleave_stereo)
- `pipeline/llm` (LLMClient)

**Recommendation:** These instantiations should be behind a factory or the orchestrator.

---

## Medium Priority Findings (plan to address)

### M1. Application → Infrastructure Violations (5 instances)
**Files:**
- `orchestrator.py` → `pipeline/llm` (HintContext, HintResponse) — `orchestrator.py:10`
- `orchestrator.py` → `pipeline/yandex_async` (YandexAsyncRecognizer) — deferred
- `orchestrator.py` → `pipeline/stt` (Transcript) — TYPE_CHECKING
- `post_call.py` → `pipeline/audio_buffer` (AudioBuffer) — `post_call.py:6`
- `post_call.py` → `pipeline/yandex_async` (YandexAsyncRecognizer) — `post_call.py:13`

**Root cause:** Data classes like `Transcript`, `HintContext`, `HintResponse`, `CallAnalytics` are defined in infrastructure modules but used as application-layer DTOs. Move them to domain or application layer.

### M2. Data Clump: `(api_key, model)` in 5+ Signatures
**Files:** `main.py:269,361,391`, `portrait.py:81`, `call_summary.py:82`, `scenario.py:110`

The same `(api_key: str, model: str)` pair is passed through everywhere. Additionally, `_call_llm()` is duplicated in 3 files (`portrait.py:42`, `call_summary.py:43`, `scenario.py:73`), each creating its own `AsyncOpenAI` client.

**Recommendation:**
1. Create `LLMConfig` dataclass
2. Extract shared `OpenRouterClient`
3. Inject via DI instead of parameter threading

### M3. Type Duplication Across Backend/Extension
**No shared schema** between Python and TypeScript. Manually-kept duplicates:
- `CallAnalyticsWire` defined 3x (`evaluation-types.ts`, `report.ts:22-34`, `orchestrator.py:244-258`)
- `CallEvaluationResult` defined 2x (`evaluation-types.ts:12-20`, `report.ts:12-20`)
- `HintPayload` mirrors `HintResponse` with no codegen

**Recommendation:** Generate TypeScript types from Pydantic models (e.g., `pydantic-to-typescript` or JSON Schema).

### M4. Shotgun Surgery: Evaluation Schema Changes Touch 8 Files
Changing evaluation schema requires edits in:
`evaluation_schemas.py`, `evaluator.py`, `evaluator_llm.py`, `orchestrator.py`, `api/evaluation.py`, `sidepanel.ts`, `report.ts`, `evaluation-types.ts`

### M5. No Anti-Corruption Layers Between Bounded Contexts
All contexts share types directly — no translation/adapter layers. Briefing imports Scenario internals (`portrait.py:110`). PromptFormatter imports CallAnalytics from PostCall (`prompt_formatter.py:5`).

### M6. `BriefingResponse` Uses Untyped Dicts
**File:** `briefing/portrait.py:16-21`
`portrait` and `strategy` fields are `dict[str, Any]` instead of reusing Scenario's typed Pydantic models (`BuyerPortrait`, `Strategy`, `Objection`).

### M7. Orchestrator Accepts All Dependencies as `Any`
**File:** `pipeline/orchestrator.py:24-31`
`ws: Any`, `llm_client: Any`, `session_manager: Any` — defeats type safety.

---

## Low Priority Findings (consider fixing)

### L1. `PipelineOrchestrator.__init__` Has 7 Parameters
**File:** `pipeline/orchestrator.py:24`
Consider a config/builder pattern.

### L2. `stt.py` Contains 6 Classes in One File (694 LOC)
**File:** `pipeline/stt.py`
Well-structured via inheritance but could be split into one file per provider.

### L3. `report.ts` Duplicates Types Instead of Importing
**File:** `extension/src/report/report.ts:12-34`
Locally redefines `CallEvaluationResult` and `CallAnalyticsWire` instead of importing from `shared/evaluation-types.ts`.

### L4. Extension Type Definitions Can Drift From Backend
No CI check ensures TypeScript wire types match Python schemas.

---

## Dependency Graph (Simplified)

```
                    ┌─────────────┐
                    │  main.py    │ (Presentation, 695 LOC, fan-out=15)
                    │ God Module  │
                    └──────┬──────┘
                           │ imports everything directly
          ┌────────────────┼────────────────┬──────────────┐
          ▼                ▼                ▼              ▼
   ┌──────────┐    ┌──────────────┐  ┌──────────┐  ┌──────────┐
   │ stt.py   │    │orchestrator  │  │ session/  │  │ingestion/│
   │(Infra)   │    │(App, fo=11)  │  │ manager   │  │parser    │
   │ 694 LOC  │    │ 393 LOC      │  │ 101 LOC   │  │ 201 LOC  │
   └──────────┘    └──────┬───────┘  └──────────┘  └──────────┘
                          │
        ┌─────────┬───────┼──────────┬──────────┐
        ▼         ▼       ▼          ▼          ▼
   ┌────────┐ ┌──────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐
   │ llm.py │ │scen. │ │evaluator│ │post_call│ │prompt_fmt│
   │(Infra) │ │(Dom) │ │(App)    │ │(App)    │ │(App)     │
   └────────┘ └──────┘ └─────────┘ └────┬────┘ └──────────┘
                                         │
                                    ┌────▼────┐
                                    │yandex_  │
                                    │async    │
                                    │(Infra)  │
                                    └─────────┘

  Shared (imported by all): config.py, logger.py, errors.py
```

---

## Metrics Summary

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Max fan-in (backend) | 15 (`logger`) | < 20 | OK (logger is expected) |
| Max fan-out (backend) | 15 (`main.py`) | < 15 | WARN |
| Max fan-out (non-entry) | 11 (`orchestrator`) | < 10 | WARN |
| Circular dependencies | 0 | 0 | OK |
| Dependency Rule violations | 9 | 0 | FAIL |
| Layer isolation (interfaces) | 1 of 5 | 5 of 5 | FAIL |
| God modules | 2 (`sidepanel.ts`, `main.py`) | 0 | WARN |
| Max LOC per file | 1,896 (`sidepanel.ts`) | < 500 | FAIL |
| Type duplications | 3 | 0 | WARN |
| Data clumps | 4 patterns | 0 | WARN |
| Anti-corruption layers | 0 | >= 1 per context boundary | FAIL |

---

## Recommendations

### Immediate Actions (next sprint)
1. **Split `sidepanel.ts`** into 8-10 focused modules (eliminates God Module, enables testing)
2. **Extract `WebSocketHandler`** from `main.py` (reduces fan-out from 15 to ~3)
3. **Fix `report.ts` type duplication** — import from `shared/evaluation-types.ts` instead of redefining

### Short-term Improvements (1-2 sprints)
4. **Create `SessionStore` Protocol** — abstract Redis behind an interface
5. **Extract `EvaluationRunner`** from orchestrator (170 LOC of unrelated evaluation logic)
6. **Create `LLMConfig` dataclass** — eliminate `(api_key, model)` data clump and deduplicate `_call_llm()`
7. **Move DTOs to domain/application layer** — `Transcript`, `HintContext`, `HintResponse`, `CallAnalytics` should not live in infrastructure modules

### Long-term Architectural Goals (quarterly)
8. **Add remaining interfaces** — `LLMClient Protocol`, `AsyncRecognizer Protocol`, `DocumentParser Protocol`
9. **Generate TypeScript types from Pydantic schemas** — eliminate manual sync and drift risk
10. **Add architecture fitness tests** — enforce layer rules via `import-linter` or `pytest-archon` in CI
11. **Introduce Anti-Corruption Layers** — translate types at bounded context boundaries instead of sharing directly
