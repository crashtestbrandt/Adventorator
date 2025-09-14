from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict

import structlog

from Adventorator import models as _models
from Adventorator import repos
from Adventorator.db import session_scope
from Adventorator.llm_prompts import build_clerk_messages, build_narrator_messages
from Adventorator.metrics import inc_counter
from Adventorator.models import Transcript as TranscriptModel
from Adventorator.retrieval import ContentSnippet, build_retriever

try:  # Optional: Phase 7 Executor preview path (module-level)
    from Adventorator import executor as _executor_mod  # type: ignore
except Exception:  # pragma: no cover - phased rollout, executor may not exist
    _executor_mod = None  # type: ignore[assignment]
from Adventorator.rules.checks import ABILS, CheckInput, compute_check
from Adventorator.rules.dice import DiceRNG
from Adventorator.schemas import LLMOutput

log = structlog.get_logger()


@dataclass(frozen=True)
class OrchestratorResult:
    mechanics: str
    narration: str
    rejected: bool = False
    reason: str | None = None
    chain_json: dict | None = None


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
    # reason is optional
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
# Common pronouns and sentence-starters to ignore in name detection
_PRONOUNS = {
    # second person
    "You",
    "Your",
    "Yours",
    "Yourself",
    "Yourselves",
    # third person plural
    "They",
    "Them",
    "Their",
    "Theirs",
    "Themselves",
    # third person singular
    "She",
    "Her",
    "Hers",
    "Herself",
    "He",
    "Him",
    "His",
    "Himself",
    "It",
    "Its",
    "Itself",
    # first person
    "We",
    "Us",
    "Our",
    "Ours",
    "Ourselves",
    "I",
    "Me",
    "My",
    "Mine",
    "Myself",
    # common capitalized determiners/conjunctions at sentence start
    "The",
    "A",
    "An",
    "This",
    "That",
    "These",
    "Those",
    "And",
    "But",
    "Then",
    "However",
    "Meanwhile",
}


def _unknown_actor_present(narration: str, allowed: set[str]) -> str | None:
    if not narration:
        return None
    # Tokenize proper-noun-like words from narration
    # Heuristic: ignore the first token of each sentence to avoid false positives
    # from sentence-initial capitalization (e.g., "Dust motes ...").
    sentences = re.split(r"(?<=[.!?])\s+", narration)
    tokens: list[str] = []
    for s in sentences:
        words = _NAME_RE.findall(s)
        if not words:
            continue
        # Skip the first candidate in this sentence; take the rest
        for w in words[1:]:
            if w not in _PRONOUNS:
                tokens.append(w)
    nar_tokens = set(tokens)
    nar_tokens = {t.lower() for t in nar_tokens}
    if not nar_tokens:
        return None
    # Build an allowed token set from provided actor names (supports full names)
    allowed_tokens: set[str] = set()
    for name in allowed:
        for t in _NAME_RE.findall(name):
            allowed_tokens.add(t.lower())
    # If no allowed tokens provided, skip defense
    if not allowed_tokens:
        return None
    disallowed = nar_tokens - allowed_tokens
    if disallowed:
        # Return a display string using original casing best-effort
        return ", ".join(sorted({t.capitalize() for t in disallowed}))
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
    character_summary_provider: Callable[[], str | None] | None = None,
    rng_seed: int | None = None,
    llm_client: object | None = None,
    prompt_token_cap: int | None = None,
    allowed_actors: list[str] | set[str] | None = None,
    settings: Any | None = None,
    actor_id: str | None = None,
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
    _orc_start = time.monotonic()
    cache_key = (scene_id, player_msg.strip())
    now = time.time()
    if player_msg and cache_key in _prompt_cache:
        ts, cached = _prompt_cache[cache_key]
        if now - ts <= _CACHE_TTL:
            log.info("orchestrator.cache.hit", scene_id=scene_id)
            return cached

    inc_counter("llm.request.enqueued")
    log.info("llm.request.enqueued", scene_id=scene_id)

    # 0) Optional: retrieval augmentation (Phase 6, feature-flagged)
    retrieval_snippets: list[ContentSnippet] = []
    if settings is not None and getattr(settings, "retrieval", None) is not None:
        try:
            # Fetch campaign_id for the scene
            async with session_scope() as s:
                sc = await s.get(_models.Scene, scene_id)
                if sc is not None and bool(getattr(settings.retrieval, "enabled", False)):
                    # DI note: build_retriever(settings) constructs a retriever with its
                    # dependencies (e.g., async sessionmaker) injected. Tests can also
                    # instantiate SqlFallbackRetriever() directly with a custom sessionmaker.
                    retriever = build_retriever(settings)
                    retrieval_snippets = await retriever.retrieve(
                        sc.campaign_id, player_msg, k=getattr(settings.retrieval, "top_k", 4)
                    )
                    log.info(
                        "retrieval.ok",
                        scene_id=scene_id,
                        campaign_id=sc.campaign_id,
                        count=len(retrieval_snippets),
                    )
        except Exception:
            # Non-fatal: log and proceed without retrieval
            inc_counter("retrieval.errors")
            log.warning("retrieval.error", scene_id=scene_id, exc_info=True)

    # 1) transcripts -> facts (clerk), augmented by retrieval player-safe text
    facts = await _facts_from_transcripts(scene_id, player_msg, max_tokens=prompt_token_cap)
    if retrieval_snippets:
        # Add retrieval snippets as facts (player-visible only)
        facts.extend([f"[ref] {snip.title}: {snip.text}" for snip in retrieval_snippets])

    # 2) narrator -> JSON output
    char_summary = character_summary_provider() if character_summary_provider else None
    narrator_msgs = build_narrator_messages(
        facts,
        player_msg,
        max_tokens=prompt_token_cap,
        character_summary=char_summary,
    )
    if not llm_client:
        return OrchestratorResult(
            mechanics="LLM not configured.", narration="", rejected=True, reason="llm_unconfigured"
        )
    out = await llm_client.generate_json(narrator_msgs)  # type: ignore[attr-defined]
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
        log.warning(
            "llm.defense.rejected",
            reason=why,
            proposal=out.proposal.model_dump(),
            narration=out.narration,
        )
        return OrchestratorResult(
            mechanics="Proposal rejected: invalid",
            narration="",
            rejected=True,
            reason=why,
        )

    # 3b) additional defenses: banned verbs and unknown actors
    if _contains_banned_verbs(out.proposal.reason) or _contains_banned_verbs(out.narration):
        inc_counter("llm.defense.rejected")
        log.warning(
            "llm.defense.rejected",
            reason="unsafe_verb",
            proposal=out.proposal.model_dump(),
            narration=out.narration,
        )
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
            log.warning(
                "llm.defense.rejected",
                reason="unknown_actor",
                unknown=bad,
                proposal=out.proposal.model_dump(),
                narration=out.narration,
            )
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

    # 5) If Executor preview is enabled, use it for mechanics; otherwise, compute locally
    use_executor = bool(getattr(settings, "features_executor", False)) if (
        settings is not None
    ) else False
    mechanics: str
    chain_json: dict | None = None
    if use_executor and (_executor_mod is not None) and hasattr(_executor_mod, "Executor"):
        try:
            ex = _executor_mod.Executor()
            chain = _executor_mod.ToolCallChain(
                request_id=f"orc-{scene_id}-{int(now*1000)}",
                scene_id=scene_id,
                steps=[
                    _executor_mod.ToolStep(
                        tool="check",
                        args={
                            "ability": p.ability,
                            "score": score,
                            "dc": p.suggested_dc,
                            "proficient": proficient,
                            "expertise": expertise,
                            "prof_bonus": prof_bonus,
                            "seed": rng_seed,
                        },
                        requires_confirmation=True,
                    )
                ],
                actor_id=actor_id,
            )
            _exec_start = time.monotonic()
            prev = await ex.execute_chain(chain, dry_run=True)
            try:
                inc_counter(
                    "orchestrator.executor.preview_ms",
                    int((time.monotonic() - _exec_start) * 1000),
                )
            except Exception:
                pass
            mechanics = prev.items[0].mechanics if prev.items else ""
            chain_json = {
                "request_id": chain.request_id,
                "scene_id": chain.scene_id,
                "actor_id": chain.actor_id,
                "steps": [
                    {
                        "tool": st.tool,
                        "args": st.args,
                        "requires_confirmation": st.requires_confirmation,
                        "visibility": st.visibility,
                    }
                    for st in chain.steps
                ],
            }
        except Exception:
            log.warning("executor.preview.error", scene_id=scene_id, exc_info=True)
            use_executor = False
    if not use_executor:
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
        rng = DiceRNG(seed=rng_seed)
        d20_rolls = [rng.roll("1d20").rolls[0]]
        result = compute_check(check_inp, d20_rolls=d20_rolls)
        mechanics = _format_mechanics_block(result, ability=p.ability, dc=p.suggested_dc)
    final = OrchestratorResult(mechanics=mechanics, narration=out.narration, chain_json=chain_json)
    inc_counter("orchestrator.format.sent")
    try:
        inc_counter("orchestrator.total_ms", int((time.monotonic() - _orc_start) * 1000))
    except Exception:
        pass
    log.info("orchestrator.format.sent", scene_id=scene_id)
    _prompt_cache[cache_key] = (now, final)
    return final
