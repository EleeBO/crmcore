from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    stt_provider: str = "deepgram"
    deepgram_api_key: str = ""
    sber_speech_api_key: str = ""
    sber_speech_scope: str = "SALUTE_SPEECH_PERS"
    openrouter_api_key: str = ""
    redis_url: str = "redis://localhost:6379"
    llm_primary_model: str = "google/gemini-2.5-flash"
    llm_fallback_model: str = "openai/gpt-4.1-mini"
    llm_primary_timeout_ms: int = 1000
    llm_fallback_timeout_ms: int = 2000
    yandex_speechkit_api_key: str = ""
    session_idle_timeout_s: int = 300  # 5 minutes of no transcripts → auto-close
    vad_threshold: float = 0.3
    log_level: str = "INFO"
    # Post-call diarization (opt-in)
    enable_post_call_diarization: bool = False
    # Hint context: how many past utterances to include (0 = all)
    hint_context_utterances: int = 50

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton. Use in application code."""
    return Settings()
