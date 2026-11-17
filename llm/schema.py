"""The contract: what /triage accepts and what it is allowed to return. Defined BEFORE any model call."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

MAX_TEXT = 2000

# Closed lists. Anything the model says outside these is a validation failure, not a new category.
Category = Literal["work", "study", "personal", "health", "finance", "other"]
Priority = Literal["low", "normal", "high"]


class TriageIn(BaseModel):
    """What the caller sends. Validated before anything else, so bad requests never cost a model call."""

    text: StrictStr = Field(
        min_length=1,
        max_length=MAX_TEXT,
        description=f"The messy to-do note to classify (1-{MAX_TEXT} characters).",
        examples=["pay the electricity bill before friday or there's a late fee"],
    )

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class TriageResult(BaseModel):
    """What we promise to return. Nothing else, ever: unknown fields are rejected, not passed along."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    priority: Priority
    confidence: float = Field(strict=True, ge=0.0, le=1.0)
    reason: str = Field(strict=True, min_length=1, max_length=200, description="One short sentence.")


# Hard-coded answer for LLM_STUB=1. It satisfies the schema, and the reason says it is not real.
STUB_RESULT = TriageResult(
    category="other",
    priority="normal",
    confidence=0.5,
    reason="Stub mode: no model was called.",
)


# Deterministic answer when the kill switch (LLM_ENABLED=false) is on. confidence 0.0 says "this is not a real judgement".
FALLBACK_RESULT = TriageResult(
    category="other",
    priority="normal",
    confidence=0.0,
    reason="Classification is switched off; no model was called.",
)
