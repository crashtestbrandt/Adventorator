# schemas.py

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Ability = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA"]


class CharacterSheet(BaseModel):
    name: str
    class_name: str = Field(alias="class")
    level: int = Field(ge=1, le=20)
    abilities: dict[Ability, int]
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
    def validate_abilities(cls, v: dict[str, int]):
        missing = [k for k in ["STR", "DEX", "CON", "INT", "WIS", "CHA"] if k not in v]
        if missing:
            raise ValueError(f"missing abilities: {missing}")
        return v

    model_config = dict(populate_by_name=True, extra="forbid")


# -----------------------------
# LLM shadow-mode data models
# -----------------------------

LLMAction = Literal[
    # Phase 3: ability checks
    "ability_check",
    # Phase 11: minimal combat attack
    "attack",
    # Phase 11.3: simple conditions
    "apply_condition",
    "remove_condition",
    "clear_condition",
]


class LLMProposal(BaseModel):
    """Model for the LLM's mechanics proposal in shadow mode.

    Fields mirror the JSON contract emitted by the narrator prompt.
    """

    action: LLMAction
    # ability_check fields
    ability: str | None = None
    suggested_dc: int | None = Field(default=None, ge=1, le=40)
    # attack fields
    attacker: str | None = None
    target: str | None = None
    attack_bonus: int | None = Field(default=None, ge=-5, le=15)
    target_ac: int | None = Field(default=None, ge=5, le=30)
    damage: dict | None = None  # { dice: str, mod?: int, type?: str }
    advantage: bool | None = None
    disadvantage: bool | None = None
    # condition fields
    condition: str | None = None
    duration: int | None = None

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
