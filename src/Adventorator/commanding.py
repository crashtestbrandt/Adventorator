# src/Adventorator/commanding.py
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel


# --- Transport-agnostic context the handler receives ---
class Responder(Protocol):
    async def send(self, content: str, *, ephemeral: bool = False) -> None: ...

@dataclass
class Invocation:
    name: str
    subcommand: str | None
    options: dict[str, Any]
    user_id: str
    channel_id: str | None
    guild_id: str | None
    responder: Responder
    # Optional DI: settings and llm client for handlers that need them
    settings: Any | None = None
    llm_client: Any | None = None
    # you can add: seed, feature flags, request_id, etc.

# --- Option models for compile-time safety & help text ---
class Option(BaseModel):
    """Base for command options; extend per command."""

# --- Command descriptor ---
@dataclass
class Command:
    name: str
    description: str
    option_model: type[Option]
    handler: Callable[[Invocation, Option], Awaitable[None]]
    subcommand: str | None = None
    # optional: default permission, dm_permission, etc.
    metadata: dict[str, Any] = field(default_factory=dict)

# --- Global registry (populated by decorator) ---
_REGISTRY: dict[str, Command] = {}

def slash_command(
    name: str,
    description: str,
    option_model: type[Option] = Option,
    subcommand: str | None = None,
    **metadata: Any,
):
    def wrap(func: Callable[[Invocation, Option], Awaitable[None]]):
        key = name + (f":{subcommand}" if subcommand else "")
        _REGISTRY[key] = Command(name, description, option_model, func, subcommand, metadata)
        return func
    return wrap

def all_commands() -> dict[str, Command]:
    return dict(_REGISTRY)

def find_command(name: str, subcommand: str | None) -> Command | None:
    key = name + (f":{subcommand}" if subcommand else "")
    cmd = _REGISTRY.get(key)
    if cmd is not None:
        return cmd
    # Fallback to a top-level command if no subcommand match
    return _REGISTRY.get(name)
