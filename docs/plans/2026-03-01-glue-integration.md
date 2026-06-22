# Glue Integration — Upload & WebSocket Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire existing pipeline modules into working HTTP and WebSocket endpoints so the full demo scenario runs end-to-end.

**Architecture:** Four glue layers: (1) lifespan — real Redis/ChromaDB init; (2) POST /api/v1/upload calling parser→chunker→embedder→ChromaDB; (3) WebSocket /ws routing binary frames through VAD→STT→Orchestrator; (4) Deepgram SDK real connection.

**Tech Stack:** FastAPI, redis.asyncio, chromadb, sentence-transformers, deepgram-sdk v3, python-multipart (already installed)

---

## What already works (DO NOT rewrite)

| Module | File | Status |
|--------|------|--------|
| File parsing | backend/ingestion/parser.py | complete |
| Chunking | backend/ingestion/chunker.py | complete |
| Embedding + indexing | backend/ingestion/embedder.py | complete |
| Hybrid RAG | backend/pipeline/rag.py | complete |
| VAD | backend/pipeline/vad.py | energy heuristic (works for demo) |
| STT abstraction | backend/pipeline/stt.py | stub _connect_channel -> Task G4 |
| LLM client | backend/pipeline/llm.py | complete |
| Pipeline orchestrator | backend/pipeline/orchestrator.py | complete |
| Session manager | backend/session/manager.py | complete |
| Health endpoint | backend/main.py:39 | complete |
| Briefing + Summarize | backend/main.py:108,148 | complete |

## What needs to be built

| # | Task | File | Currently |
|---|------|------|-----------|
| G1 | Lifespan: real service init | backend/main.py | app.state.redis = None |
| G2 | Upload endpoint | backend/main.py | HTTP 501 |
| G3 | WebSocket handler | backend/main.py | NotImplementedError |
| G4 | Deepgram real connection | backend/pipeline/stt.py | self._connections[ch] = None |
| G5 | Install missing deps | backend/ | chromadb, sentence-transformers, deepgram-sdk not in venv |

---

## Progress Tracking

- [x] G1: Lifespan — real service initialization
- [x] G2: Upload endpoint — multipart -> parse -> embed -> index
- [x] G3: WebSocket handler — frame routing -> VAD -> STT -> Orchestrator
- [x] G4: Deepgram real connection — fill _connect_channel()
- [x] G5: Install deps + verify startup

**Total Tasks:** 5 | **Completed:** 5 | **Remaining:** 0

Status: COMPLETE

