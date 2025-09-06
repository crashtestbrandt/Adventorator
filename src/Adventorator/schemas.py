# schemas.py

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Dict

Ability = Literal["STR","DEX","CON","INT","WIS","CHA"]

class CharacterSheet(BaseModel):
    name: str
    class_name: str = Field(alias="class")
    level: int = Field(ge=1, le=20)
    abilities: Dict[Ability, int]
    proficiency_bonus: int = Field(ge=2, le=6)
    skills: dict[str, bool] = Field(default_factory=dict)
    ac: int = Field(ge=1, le=30)
    hp: dict = Field(default_factory=lambda: {"current": 1, "max": 1, "temp": 0})
    speed: int = Field(ge=0, le=120)
    senses: dict = Field(default_factory=dict)
    inventory: list[dict] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    spells: list[dict] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("abilities")
    @classmethod
    def validate_abilities(cls, v: Dict[str, int]):
        missing = [k for k in ["STR","DEX","CON","INT","WIS","CHA"] if k not in v]
        if missing:
            raise ValueError(f"missing abilities: {missing}")
        return v

    model_config = dict(populate_by_name=True, extra="forbid")


# -----------------------------
# LLM shadow-mode data models
# -----------------------------

LLMAction = Literal[
    # Keep tight for milestone 0; expand as new actions are supported
    "ability_check",
]


class LLMProposal(BaseModel):
    """Model for the LLM's mechanics proposal in shadow mode.

    Fields mirror the JSON contract emitted by the narrator prompt.
    """

    action: LLMAction
    ability: Ability
    suggested_dc: int = Field(ge=1, le=40)
    reason: str

    model_config = dict(extra="forbid")


class LLMNarration(BaseModel):
    """Free-form narration text."""

    narration: str

    model_config = dict(extra="forbid")


class LLMOutput(BaseModel):
    """Top-level structure produced by the narrator in JSON-only mode."""

    proposal: LLMProposal
    narration: str

    model_config = dict(extra="forbid")
