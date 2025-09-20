"""Registry for MCP adapters."""

from __future__ import annotations

from dataclasses import dataclass

from .interfaces import RulesAdapter, SimulationAdapter


class MCPRegistryError(RuntimeError):
    """Raised when MCP adapters are missing or misconfigured."""


@dataclass
class MCPRegistry:
    """Holds active MCP adapters for executor use."""

    rules: RulesAdapter | None = None
    simulation: SimulationAdapter | None = None

    def register_rules(self, adapter: RulesAdapter) -> None:
        self.rules = adapter

    def register_simulation(self, adapter: SimulationAdapter) -> None:
        self.simulation = adapter

    def require_rules(self) -> RulesAdapter:
        if self.rules is None:
            raise MCPRegistryError("rules adapter is not registered")
        return self.rules

    def require_simulation(self) -> SimulationAdapter:
        if self.simulation is None:
            raise MCPRegistryError("simulation adapter is not registered")
        return self.simulation
