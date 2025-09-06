# llm_prompts.py

from __future__ import annotations

from typing import Any, Iterable

from .models import Transcript


SYSTEM_PROMPT_CLERK = (
    "You are the Fact Clerk. Extract concise, factual summaries of the recent scene. "
    "Do not invent details. Ignore system meta. Keep it compact."
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
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT_CLERK}
    ]

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
