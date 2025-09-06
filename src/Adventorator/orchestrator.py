from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from Adventorator.db import session_scope
from Adventorator import repos
from Adventorator.models import Transcript as TranscriptModel
from Adventorator.llm_prompts import build_clerk_messages, build_narrator_messages
from Adventorator.llm import LLMClient
from Adventorator.rules.dice import DiceRNG
from Adventorator.rules.checks import CheckInput, compute_check, ABILS
from Adventorator.schemas import LLMOutput


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
    outcome = "SUCCESS" if (result.success is True) else ("FAIL" if result.success is False else "—")
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


async def _facts_from_transcripts(scene_id: int, player_msg: str | None) -> list[str]:
    async with session_scope() as s:
        txs: list[TranscriptModel] = await repos.get_recent_transcripts(s, scene_id=scene_id, limit=15)
    msgs = build_clerk_messages(txs, player_msg=player_msg)
    # Convert assistant/user content lines (excluding system) into facts (strings)
    facts: list[str] = []
    for m in msgs:
        if m.get("role") == "system":
            continue
        facts.append(str(m.get("content", "")).strip())
    return [f for f in facts if f]


async def run_orchestrator(
    scene_id: int,
    player_msg: str,
    sheet_getter: callable | None = None,
    rng_seed: Optional[int] = None,
    llm_client: Optional[LLMClient] = None,
) -> OrchestratorResult:
    """End-to-end shadow-mode orchestration.

    - scene_id: active scene to fetch transcripts
    - player_msg: latest user input to include
    - sheet_getter: optional callable returning a minimal sheet dict for ability scores
      signature: (ability: str) -> dict(score: int, proficient: bool, expertise: bool, prof_bonus: int)
      If not provided, defaults to a benign 10 score and no proficiency.
    - rng_seed: stable seed for deterministic tests
    - llm_client: inject to mock in tests; construct externally from settings in app layer
    """

    # 1) transcripts -> facts (clerk)
    facts = await _facts_from_transcripts(scene_id, player_msg)

    # 2) narrator -> JSON output
    narrator_msgs = build_narrator_messages(facts, player_msg)
    if not llm_client:
        return OrchestratorResult(
            mechanics="LLM not configured.", narration="", rejected=True, reason="llm_unconfigured"
        )
    out = await llm_client.generate_json(narrator_msgs)
    if not out:
        return OrchestratorResult(
            mechanics="Unable to generate a proposal.", narration="",
            rejected=True, reason="llm_invalid_or_empty"
        )

    # 3) validate proposal defensively
    ok, why = _validate_proposal(out)
    if not ok:
        return OrchestratorResult(mechanics="Proposal rejected: " + (why or "invalid"), narration="", rejected=True, reason=why)

    # 4) map proposal -> rules.CheckInput using provided sheet_getter
    p = out.proposal
    if sheet_getter is None:
        # Default neutral sheet
        def sheet_getter(ability: str):  # type: ignore
            return {"score": 10, "proficient": False, "expertise": False, "prof_bonus": 2}

    sheet_info = sheet_getter(p.ability)
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
    return OrchestratorResult(mechanics=mechanics, narration=out.narration)
