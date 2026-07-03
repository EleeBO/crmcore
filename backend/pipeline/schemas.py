"""SGR schemas for structured LLM output.

Field order is intentional: reasoning before hint_type
warms up model context for better classification (SGR pattern).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class HintResponseV2(BaseModel):
    """SGR schema for real-time coaching hints.

    Replaces the old HintResponse dataclass. Uses Pydantic for
    constrained decoding — the model physically cannot return
    invalid hint_type. Length limits are soft (in descriptions)
    to avoid parse failures from verbose LLM responses.

    LLMs may return null for optional string fields — the validator
    coerces None → "" to avoid validation failures.
    """

    reasoning: str = Field(description="1-line: utterance summary + client emotion")
    hint_type: Literal["coaching", "success", "warning"] = Field(
        description=(
            "coaching = what the rep should do next; "
            "success = objection handled or good technique; "
            "warning = client losing interest or off-topic"
        )
    )
    headline: str = Field(
        description="Main coaching text, ideally ≤80 chars, readable in 1 second",
    )
    detail: str = Field(
        default="",
        description="Supporting context or explanation, ideally ≤150 chars",
    )
    coaching: str = Field(
        default="",
        description="Tone/tempo advice: 'slow down', 'show empathy', etc.",
    )
    source: str = Field(
        default="",
        description="Knowledge base reference, e.g. 'Brief, p.3'",
    )

    @field_validator(
        "detail", "coaching", "source", "headline", "reasoning", mode="before"
    )
    @classmethod
    def _coerce_none_to_empty(cls, v: object) -> str:
        """LLMs sometimes return null for string fields."""
        if v is None:
            return ""
        return str(v)
