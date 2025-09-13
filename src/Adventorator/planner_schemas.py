"""Pydantic models for the Phase 4 planner output."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlannerOutput(BaseModel):
    """Validated output from the planner LLM.

    - command: top-level slash command name (e.g., "do")
    - subcommand: optional subcommand name if applicable
    - args: dictionary of arguments for the command's option model
    """

    command: str = Field(min_length=1)
    subcommand: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    # Optional observability fields; ignored by dispatcher behavior
    confidence: float | None = Field(default=None, ge=0, le=1)
    rationale: str | None = None

    model_config = dict(extra="forbid")
