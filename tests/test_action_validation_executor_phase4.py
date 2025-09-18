"""Integration tests for Phase 4: Executor interop with ExecutionRequest."""

from __future__ import annotations

import pytest

from Adventorator.action_validation import tool_chain_from_execution_request
from Adventorator.executor import Executor, ToolCallChain, ToolStep
from Adventorator.orchestrator import run_orchestrator
from Adventorator.schemas import LLMOutput, LLMProposal


def _neutral_sheet(_ability: str) -> dict[str, int | bool]:
    return {
        "score": 10,
        "proficient": False,
        "expertise": False,
        "prof_bonus": 2,
    }


class _FakeLLM:
    def __init__(self, output: LLMOutput) -> None:
        self._output = output

    async def generate_json(self, _messages, system_prompt=None):  # noqa: ANN001
        return self._output


def _chain_from_json(payload: dict) -> ToolCallChain:
    steps = [
        ToolStep(
            tool=str(step.get("tool")),
            args=dict(step.get("args", {})),
            requires_confirmation=bool(step.get("requires_confirmation", False)),
            visibility=str(step.get("visibility", "ephemeral")),
        )
        for step in payload.get("steps", [])
    ]
    return ToolCallChain(
        request_id=str(payload.get("request_id", "")),
        scene_id=int(payload.get("scene_id", 0)),
        steps=steps,
        actor_id=payload.get("actor_id"),
    )


@pytest.mark.asyncio
async def test_execution_request_chain_matches_json_and_preview():
    settings = type(
        "Settings",
        (),
        {
            "features_executor": True,
            "features_action_validation": True,
        },
    )()

    out = LLMOutput(
        proposal=LLMProposal(
            action="ability_check",
            ability="INT",
            suggested_dc=12,
            reason="Concentrate carefully.",
        ),
        narration="You focus on the arcane pattern.",
    )

    llm = _FakeLLM(out)

    result = await run_orchestrator(
        scene_id=77,
        player_msg="I study the runes",
        sheet_info_provider=_neutral_sheet,
        rng_seed=5,
        llm_client=llm,
        settings=settings,
        actor_id="actor-77",
    )

    assert result.execution_request is not None
    assert result.chain_json is not None

    req = result.execution_request
    chain_from_req = tool_chain_from_execution_request(req)
    chain_from_payload = _chain_from_json(result.chain_json)

    assert chain_from_req == chain_from_payload
    assert chain_from_req.actor_id == "actor-77"
    assert result.chain_json.get("execution_request") == req.model_dump()

    executor = Executor()
    preview = await executor.execute_chain(chain_from_req, dry_run=True)
    assert preview.items
    assert preview.items[0].mechanics == result.mechanics
