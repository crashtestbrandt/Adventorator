"""Optional MCP server runner.

This file demonstrates wiring the framework-agnostic tool functions into an MCP
server. Importing the MCP SDK is intentionally inside `run()` to avoid adding a
hard dependency during regular tests or when the server is not used.
"""

from __future__ import annotations

from typing import Any, cast

from .tools import roll_dice_tool


def run(*, host: str = "127.0.0.1", port: int = 8765) -> None:
    # Import lazily to keep base install light.
    try:
        from mcp import Server  # type: ignore
    except Exception as e:  # pragma: no cover - only hit when running server without deps
        raise RuntimeError(
            "MCP server dependencies are not installed. Install an MCP SDK to run."
        ) from e

    server = Server("adventorator")

    # Register tools
    @server.tool("roll_dice")
    def _roll_dice(params: dict[str, Any]) -> dict[str, Any]:
        # Convert TypedDict output to a plain dict for the MCP layer.
        return cast(dict[str, Any], roll_dice_tool(params))

    server.run(host=host, port=port)
