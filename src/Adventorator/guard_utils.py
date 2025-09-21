"""Utilities for formatting and parsing guard identifiers.

Guard Identifier Format (forward-compatible placeholder):
    <category>:<name>[:key=value[,key2=value2]]

Categories (reserved): predicate, resource, state, cooldown, line_of_effect

Currently unused; added to stabilize future contract shape.
"""

from __future__ import annotations


def format_guard(category: str, name: str, **kwargs) -> str:
    base = f"{category}:{name}"
    if not kwargs:
        return base
    parts = [f"{k}={v}" for k, v in sorted(kwargs.items())]
    return base + ":" + ",".join(parts)


def parse_guard(guard: str) -> tuple[str, str, dict[str, str]]:
    # Split category and remainder
    if ":" not in guard:
        raise ValueError("Invalid guard format")
    category, remainder = guard.split(":", 1)
    if ":" in remainder:
        name, args_raw = remainder.split(":", 1)
        args: dict[str, str] = {}
        for segment in args_raw.split(","):
            if not segment:
                continue
            if "=" not in segment:
                # Treat as a flag with implicit True value
                args[segment] = "true"
            else:
                k, v = segment.split("=", 1)
                args[k] = v
        return category, name, args
    else:
        return category, remainder, {}
