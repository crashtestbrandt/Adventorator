import pytest

from Adventorator.orchestrator import OrchestratorResult, run_orchestrator
from Adventorator.schemas import LLMOutput, LLMProposal


def _neutral_sheet(_ability: str):
    return {
        "score": 10,
        "proficient": False,
        "expertise": False,
        "prof_bonus": 2,
    }


class FakeLLM:
    def __init__(self, output: LLMOutput | None):
        self._out = output

    async def generate_json(self, messages, system_prompt=None):  # noqa: ANN001
        return self._out


@pytest.mark.asyncio
async def test_orchestrator_apply_condition_preview_and_chain(monkeypatch):
    settings = type("S", (), {"features_executor": True})()

    out = LLMOutput(
        proposal=LLMProposal(
            action="apply_condition",
            target="Goblin",
            condition="Prone",
            duration=2,
            reason="Knock them down",
        ),
        narration="The goblin is knocked prone.",
    )

    llm = FakeLLM(out)

    res = await run_orchestrator(
        scene_id=1,
        player_msg="I trip the goblin",
        sheet_info_provider=_neutral_sheet,
        rng_seed=42,
        llm_client=llm,
        settings=settings,
        actor_id="user-1",
    )
    assert isinstance(res, OrchestratorResult)
    assert not res.rejected
    assert res.chain_json is not None
    steps = res.chain_json.get("steps")
    assert steps and steps[0]["tool"] == "apply_condition"
    args = steps[0]["args"]
    assert args["target"] == "Goblin" and args["condition"] == "Prone" and args["duration"] == 2


@pytest.mark.asyncio
async def test_orchestrator_condition_no_executor_fallback(monkeypatch):
    settings = type("S", (), {"features_executor": False})()

    out = LLMOutput(
        proposal=LLMProposal(
            action="remove_condition",
            target="Goblin",
            condition="Poisoned",
            reason="Shake it off",
        ),
        narration="The goblin shakes off the poison.",
    )
    llm = FakeLLM(out)

    res = await run_orchestrator(
        scene_id=1,
        player_msg="Goblin removes poison",
        sheet_info_provider=_neutral_sheet,
        rng_seed=1,
        llm_client=llm,
        settings=settings,
        actor_id="user-1",
    )
    assert res.rejected is False
    assert "Condition tools unavailable" in res.mechanics
