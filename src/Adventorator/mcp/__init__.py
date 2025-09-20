"""Multi-Component Protocol (MCP) integration scaffolding."""  # noqa: N999

from .client import MCPClient
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

__all__ = [
    "MCPClient",
    "MCPRegistry",
    "MCPRegistryError",
    "ApplyDamageRequest",
    "ApplyDamageResponse",
    "ComputeCheckRequest",
    "ComputeCheckResponse",
    "RollAttackRequest",
    "RollAttackResponse",
    "RaycastRequest",
    "RaycastResponse",
]
