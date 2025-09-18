import pytest

from Adventorator.metrics import get_counter, reset_counters
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

    async def generate_json(self, _messages, system_prompt=None):  # noqa: ANN001
        return self._out


@pytest.mark.asyncio
async def test_orchestrator_rejects_banned_reason_has_reason_and_counter(monkeypatch):
    reset_counters()
    settings = type(
        "Settings",
        (),
        {
            "features_executor": False,
            "features_action_validation": True,
        },
    )()

    out = LLMOutput(
        proposal=LLMProposal(
            action="ability_check",
            ability="DEX",
            suggested_dc=12,
            reason="We should apply damage to the foe.",
        ),
        narration="A burst of energy applies damage everywhere.",
    )

    llm = FakeLLM(out)

    res = await run_orchestrator(
        scene_id=99,
        player_msg="I want to roll",
        sheet_info_provider=_neutral_sheet,
        rng_seed=7,
        llm_client=llm,
        settings=settings,
        actor_id="actor-1",
    )

    assert isinstance(res, OrchestratorResult)
    assert res.rejected is True
    assert res.reason == "unsafe_verb"
    assert res.execution_request is None
    assert get_counter("llm.defense.rejected") == 1


@pytest.mark.asyncio
async def test_orchestrator_execution_request_only_with_feature_flag(monkeypatch):
    reset_counters()
    settings = type(
        "Settings",
        (),
        {
            "features_executor": False,
            "features_action_validation": False,
        },
    )()

    out = LLMOutput(
        proposal=LLMProposal(
            action="ability_check",
            ability="INT",
            suggested_dc=10,
            reason="Consider the arcane symbols carefully.",
        ),
        narration="You study the runes intently.",
    )

    llm = FakeLLM(out)

    res = await run_orchestrator(
        scene_id=22,
        player_msg="I investigate",
        sheet_info_provider=_neutral_sheet,
        rng_seed=11,
        llm_client=llm,
        settings=settings,
        actor_id="actor-2",
    )

    assert isinstance(res, OrchestratorResult)
    assert res.rejected is False
    assert res.execution_request is None
    # Mechanics text is still produced
    assert "Check" in res.mechanics

    # Enabling the flag produces an ExecutionRequest
    settings.features_action_validation = True

    res_flagged = await run_orchestrator(
        scene_id=22,
        player_msg="I investigate again",
        sheet_info_provider=_neutral_sheet,
        rng_seed=11,
        llm_client=llm,
        settings=settings,
        actor_id="actor-2",
    )

    assert res_flagged.execution_request is not None
    assert res_flagged.execution_request.steps
    assert res_flagged.execution_request.steps[0].op == "check"

