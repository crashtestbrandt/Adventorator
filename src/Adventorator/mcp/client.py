"""Thin MCP client that instruments adapter calls for the executor."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import structlog

from Adventorator.metrics import inc_counter, observe_histogram

from .interfaces import (
    ApplyDamageRequest,
    ApplyDamageResponse,
    ComputeCheckRequest,
    ComputeCheckResponse,
    RaycastRequest,
    RaycastResponse,
    RollAttackRequest,
    RollAttackResponse,
)
from .registry import MCPRegistry, MCPRegistryError

ReqT = TypeVar("ReqT")
T = TypeVar("T")


class MCPClient:
    """Routes executor requests through MCP adapters when enabled."""

    def __init__(self, registry: MCPRegistry) -> None:
        self._registry = registry
        self._log = structlog.get_logger()

    def compute_check(self, request: ComputeCheckRequest) -> ComputeCheckResponse:
        adapter = self._registry.require_rules()
        return self._call("rules.compute_check", adapter.compute_check, request)

    def roll_attack(self, request: RollAttackRequest) -> RollAttackResponse:
        adapter = self._registry.require_rules()
        return self._call("rules.roll_attack", adapter.roll_attack, request)

    def apply_damage(self, request: ApplyDamageRequest) -> ApplyDamageResponse:
        adapter = self._registry.require_rules()
        return self._call("rules.apply_damage", adapter.apply_damage, request)

    def raycast(self, request: RaycastRequest) -> RaycastResponse:
        adapter = self._registry.require_simulation()
        return self._call("simulation.raycast", adapter.raycast, request)

    def _call(self, tool: str, func: Callable[[ReqT], T], request: ReqT) -> T:
        start = time.monotonic()
        inc_counter("executor.mcp.call")
        try:
            result = func(request)
            dur_ms = int((time.monotonic() - start) * 1000)
            self._log.info("executor.mcp.tool", tool=tool, duration_ms=dur_ms)
            inc_counter("executor.mcp.duration_ms", dur_ms)
            observe_histogram("executor.mcp.ms", dur_ms)
            return result
        except MCPRegistryError:
            # Bubble registry errors directly for feature-flag gating clarity.
            raise
        except Exception as exc:
            dur_ms = int((time.monotonic() - start) * 1000)
            self._log.error(
                "executor.mcp.error",
                tool=tool,
                duration_ms=dur_ms,
                error=str(exc),
            )
            inc_counter("executor.mcp.failure")
            raise
