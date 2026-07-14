# FEAT-001: Context Stuffing Pipeline — Learnings

## Build System
- `uv run` fails with hatchling build error (project name "coderush2" mismatch). Use `.venv/bin/pytest` and `ruff check` directly.
- ruff is available globally, no need for `uv run ruff`.

## Settings / Config
- `backend/config.py` uses pydantic-settings BaseSettings with `.env` file.
- When removing fields from Settings, add `extra="ignore"` to SettingsConfigDict — otherwise .env entries for removed fields cause ValidationError.
- `backend/main.py:429` has `app = create_app()` at module level — Settings() is instantiated on import.

## Testing Patterns
- conftest.py provides: `client`, `app_with_mocks`, `mock_redis`, `test_settings`, audio fixtures (silence_pcm16, speech_pcm16, stereo_pcm16, audio_frame, control_frame).
- Tests that need isolated app create their own via `create_app()` + `TestClient` (e.g., lifespan tests).
- Use `_async_iter()` helper (not `aiter` — shadows Python builtin per ruff A001).
- `zip()` requires `strict=True` per ruff B905.

## Russian Text in Code
- Ruff E501 catches long Russian strings. Split multi-sentence strings into concatenated parts.
- Russian case matters: "СЦЕНАРИЙ" (nominative) vs "СЦЕНАРИЯ" (genitive) — assertions must match actual case form.

## Architecture (Post-Migration)
- No ChromaDB, no embeddings, no BM25, no HybridSearchEngine.
- Upload: parse → join docs_text → LLM generate_scenario() → Redis.
- WebSocket: session_start loads scenario from Redis → PipelineOrchestrator(scenario_text=...).
- Orchestrator: transcript forwarding + scenario-based hint generation with 500ms debounce.
- Briefing: reads scenario from Redis, falls back to docs_text + LLM.

## Pre-existing Issues
- test_stt.py::test_deepgram_connect_channel_uses_async_context_manager is flaky (async mock timing).
- Generated protobuf files (recognition_pb2.py, task_pb2_grpc.py) have ruff violations — ignore.
- test_audio.py, test_ingestion.py, test_llm.py have pre-existing ruff violations (unused imports, long lines).
