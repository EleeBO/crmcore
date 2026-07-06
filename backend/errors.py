"""Unified error system for AI Sales Copilot backend."""

from enum import StrEnum


class ErrorCode(StrEnum):
    # Infrastructure
    REDIS_UNAVAILABLE = "REDIS_UNAVAILABLE"
    CHROMADB_UNAVAILABLE = "CHROMADB_UNAVAILABLE"
    STT_UNAVAILABLE = "STT_UNAVAILABLE"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"

    # Upload / Ingestion
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_UNSUPPORTED = "FILE_UNSUPPORTED"
    FILE_CORRUPT = "FILE_CORRUPT"
    UPLOAD_PARTIAL = "UPLOAD_PARTIAL"

    # Session
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    KB_NOT_FOUND = "KB_NOT_FOUND"

    # Pipeline
    STT_TIMEOUT = "STT_TIMEOUT"
    STT_BALANCE_EXHAUSTED = "STT_BALANCE_EXHAUSTED"
    STT_AUTH_FAILED = "STT_AUTH_FAILED"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    RAG_NO_RESULTS = "RAG_NO_RESULTS"

    # WebSocket
    WS_INVALID_FRAME = "WS_INVALID_FRAME"
    WS_SESSION_MISSING = "WS_SESSION_MISSING"


class CopilotError(Exception):
    """Base exception for all backend errors."""

    def __init__(
        self, code: ErrorCode, message: str, detail: str | None = None
    ) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)

    def to_dict(self) -> dict[str, str | None]:
        return {
            "error": self.code.value,
            "message": self.message,
            "detail": self.detail,
        }


class InfrastructureError(CopilotError):
    pass


class IngestionError(CopilotError):
    pass


class SessionError(CopilotError):
    pass


class PipelineError(CopilotError):
    pass


class WebSocketError(CopilotError):
    pass
