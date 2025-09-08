import pytest

from Adventorator.orchestrator import run_orchestrator
from Adventorator.schemas import LLMOutput, LLMProposal


class _FakeLLM:
    def __init__(self, out):
        self._out = out

    async def generate_json(self, messages, system_prompt=None):  # noqa: ANN001
        return self._out


def _ok_output(ability="DEX", dc=12, reason="nimble", narration="You slip by."):  # noqa: ANN001
    return LLMOutput(
        proposal=LLMProposal(
            action="ability_check", ability=ability, suggested_dc=dc, reason=reason
        ),
        narration=narration,
    )


@pytest.mark.asyncio
async def test_rejects_banned_verbs_in_reason(monkeypatch):
    from Adventorator import repos

    async def _get_recent(*a, **k):  # noqa: ANN001
        return []

    monkeypatch.setattr(repos, "get_recent_transcripts", _get_recent)

    out = _ok_output(reason="change HP by 5")
    res = await run_orchestrator(scene_id=1, player_msg="go", llm_client=_FakeLLM(out))
    assert res.rejected
    assert res.reason == "unsafe_verb"


@pytest.mark.asyncio
async def test_rejects_unknown_actors(monkeypatch):
    from Adventorator import repos

    async def _get_recent(*a, **k):  # noqa: ANN001
        return []

    monkeypatch.setattr(repos, "get_recent_transcripts", _get_recent)

    out = _ok_output(narration="Bob hands Alice a potion.")
    # Only allow the Player and GM; Bob/Alice should be rejected
    res = await run_orchestrator(
        scene_id=1, player_msg="go", llm_client=_FakeLLM(out), allowed_actors={"Player", "GM"}
    )
    assert res.rejected
    assert res.reason == "unknown_actor"


@pytest.mark.asyncio
async def test_cache_hits(monkeypatch):
    from Adventorator import repos

    async def _get_recent(*a, **k):  # noqa: ANN001
        return []

    monkeypatch.setattr(repos, "get_recent_transcripts", _get_recent)

    out = _ok_output()
    llm = _FakeLLM(out)
    r1 = await run_orchestrator(scene_id=1, player_msg="same", llm_client=llm)
    r2 = await run_orchestrator(scene_id=1, player_msg="same", llm_client=llm)
    assert r1.mechanics == r2.mechanics