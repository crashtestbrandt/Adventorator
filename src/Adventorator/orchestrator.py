from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict
import time
import re
import structlog

from Adventorator import repos
from Adventorator.db import session_scope
from Adventorator.llm import LLMClient
from Adventorator.llm_prompts import build_clerk_messages, build_narrator_messages
from Adventorator.models import Transcript as TranscriptModel
from Adventorator.rules.checks import ABILS, CheckInput, compute_check
from Adventorator.rules.dice import DiceRNG
from Adventorator.schemas import LLMOutput
from Adventorator.metrics import inc_counter

log = structlog.get_logger()


@dataclass(frozen=True)
class OrchestratorResult:
    mechanics: str
    narration: str
    rejected: bool = False
    reason: str | None = None


def _format_mechanics_block(result, ability: str, dc: int) -> str:
    # Show both d20 rolls when applicable
    if len(result.d20) == 3:  # adv/dis path packs [a,b,pick]
        d20_str = f"d20: {result.d20[0]}/{result.d20[1]} -> {result.pick}"
    else:
        d20_str = f"d20: {result.d20[0]}"
    outcome = (
        "SUCCESS" if (result.success is True) else ("FAIL" if result.success is False else "—")
    )
    return (
        f"Check: {ability} vs DC {dc}\n"
        f"{d20_str} | mod: {result.mod:+d} | total: {result.total} -> {outcome}"
    )


def _validate_proposal(out: LLMOutput) -> tuple[bool, str | None]:
    p = out.proposal
    # action gate
    if p.action != "ability_check":
        return False, "Unsupported action"
    # ability whitelist
    if p.ability not in ABILS:
        return False, "Unknown ability"
    # DC guard (narrator can propose 1-40; orchestrator narrows to sane 5-30)
    if not (5 <= p.suggested_dc <= 30):
        return False, "DC out of acceptable range"
    # reason non-empty
    if not p.reason or not p.reason.strip():
        return False, "Missing reason"
    return True, None


_BANNED_VERBS = (
    # verbs/phrases implying state mutation, inventory, HP changes, etc.
    "change hp",
    "set hp",
    "reduce hp",
    "increase hp",
    "heal hp",
    "grant hp",
    "deal damage",
    "apply damage",
    "modify inventory",
    "add to inventory",
    "remove from inventory",
    "give item",
    "take item",
    "transfer item",
)


def _contains_banned_verbs(text: str) -> bool:
    t = (text or "").lower()
    return any(phrase in t for phrase in _BANNED_VERBS)


_NAME_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")


def _unknown_actor_present(narration: str, allowed: set[str]) -> str | None:
    if not narration:
        return None
    # Find proper-noun-like tokens and compare to allowed actors (case-sensitive match)
    tokens = set(_NAME_RE.findall(narration))
    disallowed = tokens - allowed
    if disallowed:
        return ", ".join(sorted(disallowed))
    return None


# Simple 30s prompt cache (keyed by scene and player_msg)
_CACHE_TTL = 30.0
_prompt_cache: dict[tuple[int, str], tuple[float, OrchestratorResult]] = {}


async def _facts_from_transcripts(
    scene_id: int, player_msg: str | None, max_tokens: int | None = None
) -> list[str]:
    async with session_scope() as s:
        txs: list[TranscriptModel] = await repos.get_recent_transcripts(
            s, scene_id=scene_id, limit=15
        )
    msgs = build_clerk_messages(txs, player_msg=player_msg, max_tokens=max_tokens)
    # Convert assistant/user content lines (excluding system) into facts (strings)
    facts: list[str] = []
    for m in msgs:
        if m.get("role") == "system":
            continue
        facts.append(str(m.get("content", "")).strip())
    return [f for f in facts if f]


class _SheetInfo(TypedDict, total=False):
    score: int
    proficient: bool
    expertise: bool
    prof_bonus: int


async def run_orchestrator(
    scene_id: int,
    player_msg: str,
    sheet_info_provider: Callable[[str], _SheetInfo] | None = None,
    rng_seed: int | None = None,
    llm_client: object | None = None,
    prompt_token_cap: int | None = None,
    allowed_actors: list[str] | set[str] | None = None,
) -> OrchestratorResult:
    """End-to-end shadow-mode orchestration.

    - scene_id: active scene to fetch transcripts
    - player_msg: latest user input to include
            - sheet_getter: optional callable returning a minimal sheet dict for
                ability scores. Signature:
                (ability: str) -> dict(score: int, proficient: bool,
                expertise: bool, prof_bonus: int)
      If not provided, defaults to a benign 10 score and no proficiency.
    - rng_seed: stable seed for deterministic tests
    - llm_client: inject to mock in tests; construct externally from settings in app layer
    """

    # Cache check to control duplicate prompts spam
    cache_key = (scene_id, player_msg.strip())
    now = time.time()
    if player_msg and cache_key in _prompt_cache:
        ts, cached = _prompt_cache[cache_key]
        if now - ts <= _CACHE_TTL:
            log.info("orchestrator.cache.hit", scene_id=scene_id)
            return cached

    inc_counter("llm.request.enqueued")
    log.info("llm.request.enqueued", scene_id=scene_id)

    # 1) transcripts -> facts (clerk)
    facts = await _facts_from_transcripts(scene_id, player_msg, max_tokens=prompt_token_cap)

    # 2) narrator -> JSON output
    narrator_msgs = build_narrator_messages(facts, player_msg, max_tokens=prompt_token_cap)
    if not llm_client:
        return OrchestratorResult(
            mechanics="LLM not configured.", narration="", rejected=True, reason="llm_unconfigured"
        )
    out = await llm_client.generate_json(narrator_msgs)  # type: ignore[attribute-defined-outside-init]
    if not out:
        inc_counter("llm.parse.failed")
        log.warning("llm.parse.failed", scene_id=scene_id)
        return OrchestratorResult(
            mechanics="Unable to generate a proposal.",
            narration="",
            rejected=True,
            reason="llm_invalid_or_empty",
        )
    inc_counter("llm.response.received")
    log.info("llm.response.received", scene_id=scene_id)

    # 3) validate proposal defensively
    ok, why = _validate_proposal(out)
    if not ok:
        inc_counter("llm.defense.rejected")
        log.warning("llm.defense.rejected", reason=why)
        return OrchestratorResult(
            mechanics="Proposal rejected: " + (why or "invalid"),
            narration="",
            rejected=True,
            reason=why,
        )

    # 3b) additional defenses: banned verbs and unknown actors
    if _contains_banned_verbs(out.proposal.reason) or _contains_banned_verbs(out.narration):
        inc_counter("llm.defense.rejected")
        log.warning("llm.defense.rejected", reason="unsafe_verb")
        return OrchestratorResult(
            mechanics="Proposal rejected: unsafe content",
            narration="",
            rejected=True,
            reason="unsafe_verb",
        )

    if allowed_actors:
        allowed_set = set(allowed_actors)
        bad = _unknown_actor_present(out.narration, allowed_set)
        if bad:
            inc_counter("llm.defense.rejected")
            log.warning("llm.defense.rejected", reason="unknown_actor", unknown=bad)
            return OrchestratorResult(
                mechanics="Proposal rejected: unknown actors",
                narration="",
                rejected=True,
                reason="unknown_actor",
            )

    # 4) map proposal -> rules.CheckInput using provided sheet_getter
    p = out.proposal
    if sheet_info_provider is None:
        # Default neutral sheet
        def _default_sheet_info(ability: str) -> _SheetInfo:
            return {
                "score": 10,
                "proficient": False,
                "expertise": False,
                "prof_bonus": 2,
            }
        sheet_info_provider = _default_sheet_info

    sheet_info = sheet_info_provider(p.ability)
    score = int(sheet_info.get("score", 10))
    proficient = bool(sheet_info.get("proficient", False))
    expertise = bool(sheet_info.get("expertise", False))
    prof_bonus = int(sheet_info.get("prof_bonus", 2))

    check_inp = CheckInput(
        ability=p.ability,
        score=score,
        proficient=proficient,
        expertise=expertise,
        proficiency_bonus=prof_bonus,
        dc=p.suggested_dc,
        advantage=False,
        disadvantage=False,
    )

    # 5) compute mechanics via DiceRNG on a single d20
    rng = DiceRNG(seed=rng_seed)
    # We pass two d20s to compute_check to support adv/dis selection; here both same seed path
    d20_rolls = [rng.roll("1d20").rolls[0]]
    result = compute_check(check_inp, d20_rolls=d20_rolls)

    # 6) format mechanics + narration
    mechanics = _format_mechanics_block(result, ability=p.ability, dc=p.suggested_dc)
    final = OrchestratorResult(mechanics=mechanics, narration=out.narration)
    inc_counter("orchestrator.format.sent")
    log.info("orchestrator.format.sent", scene_id=scene_id)
    _prompt_cache[cache_key] = (now, final)
    return final
