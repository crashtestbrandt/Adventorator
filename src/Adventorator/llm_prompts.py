"""Prompt builders and system prompts for LLM calls."""

from __future__ import annotations  # noqa: I001

from collections.abc import Iterable
from typing import Any

from Adventorator.models import Transcript


SYSTEM_PROMPT_CLERK = (
    "You are the Fact Clerk. Extract concise, factual summaries of the recent scene. "
    "Do not invent details. Ignore system meta. Keep it compact."
)

# OOC narrator system prompt: produce narration only, no mechanics or dice.
SYSTEM_PROMPT_OOC = (
    "You are the Narrator. Write a brief, evocative narration in response to the player's input, "
    "grounded in the provided recent facts. Do NOT mention dice, DCs, mechanics, or game rules. "
    "Stay concise (1-3 sentences)."
)

# Narrator system prompt: strictly emit a single JSON object only.
SYSTEM_PROMPT_NARRATOR = (
    "You are the Narrator. Using the provided facts and the player's latest input, "
    "decide if a single d20 ability check is warranted. Respond with ONLY a single JSON object, "
    "no extra text or markdown. The JSON schema (both keys required) is:\n"
    "{\n"
    '  "proposal": {\n'
    '    "action": "ability_check",\n'
    '    "ability": "STR|DEX|CON|INT|WIS|CHA",\n'
    '    "suggested_dc": <int 1-40>,\n'
    '    "reason": "short justification"\n'
    "  },\n"
    '  "narration": "brief evocative narration"\n'
    "}\n"
    "Rules: If no check is needed, pick the most relevant ability and a reasonable DC anyway. "
    "Always include a concise 'narration' string. Do not include commentary outside the JSON."
)


def _approx_tokens(s: str) -> int:
    # Simple heuristic: ~4 chars per token
    return max(1, (len(s) + 3) // 4)


def _summarize_transcript_line(t: Transcript) -> str:
    author = t.author
    content = (t.content or "").strip()
    # Drop empty lines fast
    if not content:
        return ""
    # Prefix with author for clarity
    return f"{author}: {content}"


def build_clerk_messages(
    transcripts: Iterable[Transcript],
    player_msg: str | None,
    max_tokens: int | None = None,
) -> list[dict[str, Any]]:
    """Build messages for the clerk LLM call.

    - transcripts: expected chronological order (oldest first).
    - Excludes entries with author == 'system'.
    - Applies a rough token cap if provided.
    """
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT_CLERK}]

    budget = max_tokens or 10_000
    # Do not count system tokens against budget; reserve space for player's message if provided.
    used = 0
    player_line = (player_msg or "").strip()
    reserve = _approx_tokens(player_line) if player_line else 0

    # Include recent lines, skipping system
    for t in transcripts:
        if t.author == "system":
            continue
        line = _summarize_transcript_line(t)
        if not line:
            continue
        cost = _approx_tokens(line)
        # Keep space for the player's message, if present
        if used + cost > max(0, budget - reserve):
            break
        messages.append({"role": "user" if t.author == "player" else "assistant", "content": line})
        used += cost

    # Append the current player's message if provided
    if player_line:
        cost = _approx_tokens(player_line)
        if used + cost <= budget:
            messages.append({"role": "user", "content": player_line})

    return messages


def build_narrator_messages(
    facts: Iterable[str],
    player_msg: str | None,
    max_tokens: int | None = None,
) -> list[dict[str, Any]]:
    """Build messages for the narrator in JSON-only mode.

    - facts: ordered list of short fact strings
    - Ensures the player's current input is included
    - Applies a rough token cap if provided (not counting system prompt)
    """
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT_NARRATOR}]

    budget = max_tokens or 10_000
    used = 0
    player_line = (player_msg or "").strip()
    reserve = _approx_tokens(player_line) if player_line else 0

    picked_facts: list[str] = []
    for f in facts:
        f = (f or "").strip()
        if not f:
            continue
        line = f"- {f}"
        cost = _approx_tokens(line)
        if used + cost > max(0, budget - reserve):
            break
        picked_facts.append(line)
        used += cost

    content_lines: list[str] = []
    if picked_facts:
        content_lines.append("Facts:")
        content_lines.extend(picked_facts)
    if player_line:
        content_lines.append(f"Player input: {player_line}")

    # Always provide at least the player input to the model
    if not content_lines:
        content_lines.append("Player input: ")

    user_content = "\n".join(content_lines)
    messages.append({"role": "user", "content": user_content})

    return messages


def build_ooc_narration_messages(
    facts: Iterable[str],
    player_msg: str | None,
    max_tokens: int | None = None,
) -> list[dict[str, Any]]:
    """Build messages for OOC narration-only flow.

    - facts: short fact strings for context
    - player_msg: the user's latest OOC note or request
    """
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT_OOC}]

    budget = max_tokens or 10_000
    used = 0
    player_line = (player_msg or "").strip()
    reserve = _approx_tokens(player_line) if player_line else 0

    picked_facts: list[str] = []
    for f in facts:
        f = (f or "").strip()
        if not f:
            continue
        line = f"- {f}"
        cost = _approx_tokens(line)
        if used + cost > max(0, budget - reserve):
            break
        picked_facts.append(line)
        used += cost

    content_lines: list[str] = []
    if picked_facts:
        content_lines.append("Facts:")
        content_lines.extend(picked_facts)
    if player_line:
        content_lines.append(f"Player input: {player_line}")

    if not content_lines:
        content_lines.append("Player input: ")

    user_content = "\n".join(content_lines)
    messages.append({"role": "user", "content": user_content})
    return messages
