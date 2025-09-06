# llm_utils.py

from __future__ import annotations

from typing import Any
import json

from .schemas import LLMOutput


def extract_first_json(text: str, max_chars: int = 50_000) -> dict[str, Any] | None:
    """Extract the first valid top-level JSON object from text.

    - Scans for the first '{' and attempts to find the matching closing '}'.
    - Enforces a hard character cap to avoid pathological scans.
    - Returns dict on success; None on failure.
    """
    if not text:
        return None
    snippet = text[:max_chars]
    start = snippet.find("{")
    if start == -1:
        return None

    # Simple stack-based brace matching to find the first balanced object
    depth = 0
    in_string = False
    escape = False
    end_idx = None
    for i, ch in enumerate(snippet[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{" :
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break

    if end_idx is None:
        return None

    candidate = snippet[start:end_idx]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        return data
    return None


def validate_llm_output(data: dict[str, Any] | None) -> LLMOutput | None:
    """Validate raw dict against LLMOutput; return instance or None on error."""
    if not isinstance(data, dict):
        return None
    try:
        return LLMOutput.model_validate(data)
    except Exception:
        return None
