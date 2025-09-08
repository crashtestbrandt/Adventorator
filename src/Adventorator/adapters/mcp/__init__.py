"""MCP adapter package.

This package contains MCP-facing handlers and (optionally) a server runner.
The tool handlers are kept framework-agnostic so they can be unit-tested
without importing any MCP libraries.
"""

from .tools import roll_dice_tool

__all__ = [
    "roll_dice_tool",
]
