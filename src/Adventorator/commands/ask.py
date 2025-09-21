from __future__ import annotations

import re

import structlog
from pydantic import Field
from time import perf_counter

from Adventorator.action_validation.logging_utils import log_event
from Adventorator.commanding import Invocation, Option, slash_command
from Adventorator.metrics import inc_counter, observe_histogram
from Adventorator.schemas import AffordanceTag, AskReport, IntentFrame

log = structlog.get_logger()


class AskOpts(Option):
    message: str = Field(description="What do you want to do?")


# Extremely lightweight token-based action inference to avoid external NLP.
# Finds the first non-stopword alphabetic token as the action.
_STOPWORDS: set[str] = {
    "i",
    "we",
    "you",
    "he",
    "she",
    "they",
    "it",
    "me",
    "him",
    # 'her' already covered above in pronouns; avoid duplicate
    "them",
    "the",
    "a",
    "an",
    "to",
    "with",
    "and",
    "then",
    "please",
    "at",
    "on",
    "in",
    "into",
    "of",
    "from",
    "that",
    "this",
    "those",
    "these",
    "my",
    "your",
    "our",
    "their",
    "his",
    "her",
    "its",
}


def _infer_action(text: str) -> str:
    tokens = [t.lower() for t in re.findall(r"[A-Za-z]+", text)]
    for t in tokens:
        if t in _STOPWORDS:
            continue
        return t
    # Fallback when no suitable token found
    return (tokens[0].lower() if tokens else "say")


def _safe_echo(text: str, limit: int = 120) -> str:
    """Return a sanitized, truncated echo of user text for ephemeral display.

    - Collapses newlines/tabs to spaces
    - Trims surrounding whitespace
    - Truncates to limit characters and appends an ellipsis if needed
    """
    sanitized = re.sub(r"\s+", " ", text).strip()
    if len(sanitized) <= limit:
        return sanitized
    return sanitized[:limit] + "…"


@slash_command(
    name="ask",
    description="Interpret your intent and suggest actions.",
    option_model=AskOpts,
)
async def ask_cmd(inv: Invocation, opts: AskOpts):
    settings = inv.settings
    # Gate behind both epic and command flags
    if not (
        getattr(settings, "features_improbability_drive", False)
        and getattr(settings, "features_ask", False)
    ):
        await inv.responder.send("❌ /ask is currently disabled.", ephemeral=True)
        return

    start = perf_counter()
    user_msg = (opts.message or "").strip()
    if not user_msg:
        # Validation failure when enabled
        inc_counter("ask.failed")
        log_event(
            "ask",
            "failed",
            reason="empty_input",
            error_code="EMPTY_INPUT",
            user_id=str(inv.user_id or ""),
        )
        observe_histogram("ask.handler.duration", int((perf_counter() - start) * 1000))
        await inv.responder.send("❌ You need to provide a message.", ephemeral=True)
        return

    inc_counter("ask.received")
    log_event("ask", "initiated", user_id=str(inv.user_id or ""))

    # Minimal baseline: rule-based scaffold placeholder when enabled
    # Future Story C/D will replace this with real parsing and optional KB lookups.
    intent = IntentFrame(action=_infer_action(user_msg), actor_ref=None, target_ref=None)
    tags: list[AffordanceTag] = []
    if getattr(settings, "features_ask_nlu_rule_based", True):
        # Extremely naive tag based on first token; acts as a scaffold
        first = intent.action
        if first:
            tags.append(AffordanceTag(key=f"action.{first}", confidence=1.0))

    _report = AskReport(raw_text=user_msg, intent=intent, tags=tags)

    # Emit observability; Story F will expand metrics/logs
    inc_counter("ask.ask_report.emitted")
    log_event("ask", "completed", action=intent.action, tags=len(tags))

    # Duration metric for the enabled path
    observe_histogram("ask.handler.duration", int((perf_counter() - start) * 1000))

    # Short textual summary for the user; full report is internal for now
    echo = _safe_echo(user_msg)
    summary = f"🧭 Interpreted intent: action='{intent.action}' • you said: \"{echo}\""
    if intent.target_ref:
        summary += f", target='{intent.target_ref}'"
    await inv.responder.send(summary, ephemeral=True)
