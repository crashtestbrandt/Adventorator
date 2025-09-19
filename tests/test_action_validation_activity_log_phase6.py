import pytest

from Adventorator import models, repos
from Adventorator.metrics import get_counter, reset_counters
from Adventorator.orchestrator import run_orchestrator
from Adventorator.schemas import LLMOutput, LLMProposal
from Adventorator.db import session_scope


class _FakeLLM:
    def __init__(self, output: LLMOutput) -> None:
        self._output = output

    async def generate_json(self, _messages, system_prompt=None):  # noqa: ANN001
        return self._output


def _sheet_info(_ability: str) -> dict[str, int | bool]:
    return {
        "score": 12,
        "proficient": False,
        "expertise": False,
        "prof_bonus": 2,
    }


@pytest.mark.asyncio
async def test_orchestrator_records_activity_log(db):
    reset_counters()

    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=10)
        scene = await repos.ensure_scene(s, camp.id, channel_id=101)
        campaign_id = camp.id
        scene_id = scene.id

    output = LLMOutput(
        proposal=LLMProposal(
            action="ability_check",
            ability="INT",
            suggested_dc=14,
            reason="Focus on the arcane weave.",
        ),
        narration="You mutter an incantation as you study the glyphs.",
    )

    settings = type(
        "Settings",
        (),
        {
            "features_action_validation": True,
            "features_activity_log": True,
            "features_executor": False,
        },
    )()

    result = await run_orchestrator(
        scene_id=scene_id,
        player_msg="I inspect the glyphs",
        sheet_info_provider=_sheet_info,
        rng_seed=7,
        llm_client=_FakeLLM(output),
        settings=settings,
        actor_id="wizard-1",
    )

    assert result.activity_log_id is not None
    assert get_counter("activity_log.created") == 1

    async with session_scope() as s:
        row = await s.get(models.ActivityLog, result.activity_log_id)
        assert row is not None
        assert row.campaign_id == campaign_id
        assert row.scene_id == scene_id
        assert row.event_type == "mechanics.check"
        assert row.summary.startswith("INT check")
        assert row.payload.get("mechanics") == result.mechanics
        assert row.payload.get("plan_id") == row.request_id == row.correlation_id


@pytest.mark.asyncio
async def test_transcript_link_increments_counter(db):
    reset_counters()

    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=11)
        scene = await repos.ensure_scene(s, camp.id, channel_id=202)
        log_row = await repos.create_activity_log(
            s,
            campaign_id=camp.id,
            scene_id=scene.id,
            actor_ref="cleric",
            event_type="mechanics.check",
            summary="WIS check vs DC 12",
            payload={"mechanics": "Check summary", "plan_id": "test"},
            correlation_id="log-202",
            request_id="log-202",
        )
        campaign_id = camp.id
        scene_id = scene.id
        log_id = log_row.id

    async with session_scope() as s:
        tx = await repos.write_transcript(
            s,
            campaign_id=campaign_id,
            scene_id=scene_id,
            channel_id=202,
            author="bot",
            content="Narration",
            author_ref="cleric",
            meta={"mechanics": "Check summary"},
            status="complete",
            activity_log_id=log_id,
        )
        assert tx.activity_log_id == log_id

    assert get_counter("activity_log.linked_to_transcript") == 1
