from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolSpec:
    name: str
    schema: dict[str, Any]
    handler: Callable[[dict[str, Any], bool], dict[str, Any]]


class ToolRegistry(Protocol):
    def list_tools(self) -> dict[str, ToolSpec]:
        ...

    def get(self, name: str) -> ToolSpec | None:
        ...


class InMemoryToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def list_tools(self) -> dict[str, ToolSpec]:
        return dict(self._tools)

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)
