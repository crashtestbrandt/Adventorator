# llm_utils.py

from __future__ import annotations

import json
import re
from typing import Any

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
        elif ch == "{":
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


_SYSTEM_LINE_RE = re.compile(
    r"^(?i:(system|assistant|developer|tool|function(?:\s*call)?|role\s*:\s*system))\b[:>\-\s]*"
)
_TAG_RE = re.compile(r"</?\s*(system|assistant|developer|tool)\s*>", re.IGNORECASE)
_TAG_BLOCK_RE = re.compile(
    r"<\s*(system|assistant|developer|tool)\s*>.*?</\s*\1\s*>", re.IGNORECASE | re.DOTALL
)


def scrub_system_text(text: str, max_chars: int | None = None) -> str:
    """Remove common system/meta leakage markers and optionally truncate.

    - Drops leading role-like prefixes (e.g., "system:", "assistant>").
    - Removes <system>...</system> tags.
    - Returns a clean string, optionally truncated by max_chars.
    """
    if not text:
        return ""
    # Remove entire <tag>...</tag> blocks first
    t = _TAG_BLOCK_RE.sub("", text)
    # Then strip any stray single tags
    t = _TAG_RE.sub("", t)
    # Remove leading system-like markers per line
    lines = [_SYSTEM_LINE_RE.sub("", ln).strip() for ln in t.splitlines()]
    cleaned = "\n".join([ln for ln in lines if ln])
    if max_chars is not None and max_chars > 0 and len(cleaned) > max_chars:
        return cleaned[:max_chars]
    return cleaned


def looks_system_like(text: str) -> bool:
    """Heuristic: True if a line looks like system/meta leakage."""
    if not text:
        return False
    if _SYSTEM_LINE_RE.match(text.strip()):
        return True
    if _TAG_RE.search(text):
        return True
    # Markdown headings that reveal system
    if text.strip().lower().startswith(("### system", "## system", "# system")):
        return True
    # Role JSON-ish leak
    if '"role"' in text and '"system"' in text:
        return True
    return False


_UNSAFE_RE = re.compile(
    r"(?i:\b(hp|hit\s*points?|inventory|bag|backpack)\b.*\b(add|remove|set|change|increase|decrease|heal|damage|grant|take)\b|\b(add|remove|set|change|increase|decrease|heal|damage|grant|take)\b.*\b(hp|hit\s*points?|inventory|bag|backpack)\b)"
)


def is_unsafe_mechanics(text: str) -> bool:
    """Detect references to unsafe state mutations around HP/inventory.

    A simple regex-based heuristic; returns True if suspicious.
    """
    if not text:
        return False
    return bool(_UNSAFE_RE.search(text))


def truncate_chars(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if max_chars <= 0:
        return ""
    return text if len(text) <= max_chars else text[:max_chars]
