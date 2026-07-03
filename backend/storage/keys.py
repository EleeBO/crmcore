"""Redis key registry — single source of truth for all key patterns."""

from __future__ import annotations

# ── TTL constants (seconds) ──────────────────────────────────────────────

SESSION_TTL = 1800  # 30 minutes
KB_TTL = 7200  # 2 hours
EVAL_TTL = 86400  # 24 hours
# eval_config:default — intentionally no TTL (admin-controlled persistent config)
CONFIG_TTL: int | None = None


# ── Session keys ─────────────────────────────────────────────────────────


def session_utterances(session_id: str) -> str:
    return f"session:{session_id}:utterances"


def session_summary(session_id: str) -> str:
    return f"session:{session_id}:summary"


def session_kb_id(session_id: str) -> str:
    return f"session:{session_id}:kb_id"


# ── Evaluation keys ──────────────────────────────────────────────────────


def eval_transcript(session_id: str) -> str:
    return f"eval_transcript:{session_id}"


def eval_token(session_id: str) -> str:
    return f"eval_token:{session_id}"


def eval_analytics(session_id: str) -> str:
    return f"eval_analytics:{session_id}"


def eval_result(session_id: str) -> str:
    return f"eval:{session_id}"


def eval_config() -> str:
    return "eval_config:default"


# ── Knowledge base keys ──────────────────────────────────────────────────


def kb_docs(kb_id: str) -> str:
    return f"kb:{kb_id}:docs"


def kb_scenario(kb_id: str) -> str:
    return f"kb:{kb_id}:scenario"


# ── Briefing cache ───────────────────────────────────────────────────────


def briefing_cache(session_id: str, kb_id: str) -> str:
    return f"briefing:{session_id}:{kb_id}"
