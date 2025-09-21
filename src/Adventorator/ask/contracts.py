from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AffordanceTag(BaseModel):
    key: str = Field(..., description="Ontology key, e.g., action.attack or target.npc")
    value: str | None = Field(
        default=None, description="Optional value or normalized ID, e.g., npc:guard_12"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence for tag extraction (rule-based defaults to 1.0)",
    )


class IntentFrame(BaseModel):
    # Minimal baseline fields; extend via versioned contract if needed
    action: str = Field(..., description="Normalized action verb, e.g., 'attack' or 'move'")
    actor_ref: str | None = Field(
        default=None, description="Actor reference (character ID, user, or alias) if known"
    )
    target_ref: str | None = Field(
        default=None, description="Target reference (character/NPC/object ID or alias)"
    )
    modifiers: list[str] = Field(default_factory=list, description="Free-form modifiers or adverbs")


class AskReport(BaseModel):
    version: Literal["1.0"] = Field(default="1.0", description="Contract version")
    raw_text: str = Field(..., description="Original user text input")
    intent: IntentFrame = Field(..., description="Primary interpreted intent")
    tags: list[AffordanceTag] = Field(default_factory=list, description="Extracted affordance tags")

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=False, exclude_none=True)

    @classmethod
    def from_json(cls, data: str) -> AskReport:
        return cls.model_validate_json(data)
