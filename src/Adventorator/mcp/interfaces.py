"""Shared MCP adapter interfaces used by the executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from Adventorator.rules.checks import CheckInput, CheckResult


@dataclass(frozen=True)
class ComputeCheckRequest:
    """Request payload for rules.compute_check."""

    check: CheckInput
    seed: int | None = None
    d20_rolls: list[int] | None = None


@dataclass(frozen=True)
class ComputeCheckResponse:
    """Deterministic output for rules.compute_check."""

    result: CheckResult


@dataclass(frozen=True)
class RollAttackRequest:
    """Request payload for rules.roll_attack."""

    attack_bonus: int
    target_ac: int
    damage_dice: str
    damage_modifier: int
    advantage: bool = False
    disadvantage: bool = False
    seed: int | None = None


@dataclass(frozen=True)
class RollAttackResponse:
    """Deterministic output for rules.roll_attack."""

    total: int
    d20: int
    is_critical: bool
    is_fumble: bool
    hit: bool
    damage_total: int | None


@dataclass(frozen=True)
class ApplyDamageRequest:
    """Request payload for rules.apply_damage."""

    amount: int
    current_hp: int | None = None
    temp_hp: int | None = None


@dataclass(frozen=True)
class ApplyDamageResponse:
    """Deterministic output for rules.apply_damage."""

    remaining_hp: int | None
    remaining_temp_hp: int | None


@dataclass(frozen=True)
class RaycastRequest:
    """Placeholder simulation request used for parity testing."""

    origin: tuple[float, float, float]
    direction: tuple[float, float, float]
    distance: float


@dataclass(frozen=True)
class RaycastResponse:
    """Placeholder response for sim.raycast."""

    hit: bool
    point: tuple[float, float, float] | None = None


class RulesAdapter(Protocol):
    """Rules-oriented MCP adapter interface."""

    def compute_check(self, request: ComputeCheckRequest) -> ComputeCheckResponse:
        """Compute a skill check using deterministic dice rolls."""

    def roll_attack(self, request: RollAttackRequest) -> RollAttackResponse:
        """Resolve an attack roll and produce damage totals."""

    def apply_damage(self, request: ApplyDamageRequest) -> ApplyDamageResponse:
        """Apply damage to a hit point pool."""


class SimulationAdapter(Protocol):
    """Simulation-oriented MCP adapter interface."""

    def raycast(self, request: RaycastRequest) -> RaycastResponse:
        """Run a simple raycast against the active scene."""
