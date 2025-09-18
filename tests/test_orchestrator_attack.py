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
async def test_orchestrator_attack_preview_and_chain(monkeypatch):
    # Enable executor preview path
    settings = type("S", (), {"features_executor": True, "features_action_validation": True})()

    out = LLMOutput(
        proposal=LLMProposal(
            action="attack",
            attacker="Alice",
            target="Goblin",
            attack_bonus=5,
            target_ac=10,
            damage={"dice": "1d6", "mod": 2, "type": "slashing"},
            reason="Strike the goblin.",
        ),
        narration="Alice darts forward and strikes the goblin.",
    )

    llm = FakeLLM(out)

    res = await run_orchestrator(
        scene_id=1,
        player_msg="I attack the goblin",
        sheet_info_provider=_neutral_sheet,
        rng_seed=42,
        llm_client=llm,
        settings=settings,
        actor_id="user-1",
    )
    assert isinstance(res, OrchestratorResult)
    assert not res.rejected
    assert "Attack +5 vs AC 10" in res.mechanics
    assert res.chain_json is not None
    steps = res.chain_json.get("steps")
    assert steps and steps[0]["tool"] == "attack"
    assert res.execution_request is not None
    assert res.execution_request.steps[0].op == "attack"


@pytest.mark.asyncio
async def test_orchestrator_attack_no_executor_fallback(monkeypatch):
    # Disable executor preview
    settings = type("S", (), {"features_executor": False})()

    out = LLMOutput(
        proposal=LLMProposal(
            action="attack",
            attacker="Alice",
            target="Goblin",
            attack_bonus=3,
            target_ac=12,
            damage={"dice": "1d4"},
            reason="Strike",
        ),
        narration="Alice swings.",
    )
    llm = FakeLLM(out)

    res = await run_orchestrator(
        scene_id=1,
        player_msg="I attack",
        sheet_info_provider=_neutral_sheet,
        rng_seed=1,
        llm_client=llm,
        settings=settings,
        actor_id="user-1",
    )
    assert res.rejected is False
    # Fallback message when executor disabled
    assert "Combat tools unavailable" in res.mechanics
