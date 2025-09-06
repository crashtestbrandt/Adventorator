import asyncio
import pytest

from Adventorator.orchestrator import run_orchestrator, OrchestratorResult
from Adventorator.schemas import LLMProposal, LLMOutput


class FakeLLM:
    def __init__(self, output: LLMOutput | None):
        self._out = output

    async def generate_json(self, messages, system_prompt=None):
        return self._out


def _neutral_sheet(ability: str):
    return {"score": 12, "proficient": False, "expertise": False, "prof_bonus": 2}


@pytest.mark.asyncio
async def test_orchestrator_happy_path(monkeypatch):
    # Prepare fixed LLM output
    out = LLMOutput(
        proposal=LLMProposal(action="ability_check", ability="DEX", suggested_dc=12, reason="nimble"),
        narration="You nimbly avoid the trap." 
    )
    llm = FakeLLM(out)

    # Ensure recent transcripts fetch returns empty (facts minimal)
    from Adventorator import repos

    async def fake_get_recent_transcripts(s, scene_id, limit=15, user_id=None):
        return []

    monkeypatch.setattr(repos, "get_recent_transcripts", fake_get_recent_transcripts)

    res = await run_orchestrator(scene_id=1, player_msg="I step forward.", sheet_getter=_neutral_sheet, rng_seed=42, llm_client=llm)
    assert isinstance(res, OrchestratorResult)
    assert not res.rejected
    assert "Check: DEX vs DC 12" in res.mechanics
    assert "total:" in res.mechanics
    assert res.narration.startswith("You nimbly")


@pytest.mark.asyncio
async def test_orchestrator_rejects_bad_dc(monkeypatch):
    out = LLMOutput(
        proposal=LLMProposal(action="ability_check", ability="STR", suggested_dc=40, reason="too hard"),
        narration="—"
    )
    llm = FakeLLM(out)

    from Adventorator import repos

    async def fake_get_recent_transcripts(s, scene_id, limit=15, user_id=None):
        return []

    monkeypatch.setattr(repos, "get_recent_transcripts", fake_get_recent_transcripts)

    res = await run_orchestrator(scene_id=1, player_msg="I lift.", sheet_getter=_neutral_sheet, rng_seed=1, llm_client=llm)
    assert res.rejected
    assert "Proposal rejected" in res.mechanics or res.reason is not None


@pytest.mark.asyncio
async def test_orchestrator_rejects_bad_ability(monkeypatch):
    # ability invalid
    out = LLMOutput(
        proposal=LLMProposal(action="ability_check", ability="LCK", suggested_dc=10, reason="luck"),
        narration="—"
    )
    llm = FakeLLM(out)

    from Adventorator import repos

    async def fake_get_recent_transcripts(s, scene_id, limit=15, user_id=None):
        return []

    monkeypatch.setattr(repos, "get_recent_transcripts", fake_get_recent_transcripts)

    res = await run_orchestrator(scene_id=1, player_msg="I try.", sheet_getter=_neutral_sheet, rng_seed=1, llm_client=llm)
    assert res.rejected
    assert "Unknown ability" in (res.reason or "") or "Proposal rejected" in res.mechanics
