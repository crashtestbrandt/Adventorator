import pytest
from sqlalchemy import select

from Adventorator import models, repos
from Adventorator.commanding import Invocation
from Adventorator.commands.check import CheckOpts, check_command
from Adventorator.commands.roll import RollOpts, roll
from Adventorator.db import session_scope
from Adventorator.metrics import get_counter, reset_counters
from Adventorator.orchestrator import run_orchestrator
from Adventorator.rules.engine import Dnd5eRuleset
from Adventorator.schemas import LLMOutput, LLMProposal


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


class _SpyResponder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, content: str, *, ephemeral: bool = False) -> None:  # noqa: D401, ANN001
        self.messages.append(content)


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


@pytest.mark.asyncio
async def test_check_command_records_activity_log(db):
    reset_counters()

    settings = type(
        "Settings",
        (),
        {
            "features_activity_log": True,
            "features_events": False,
        },
    )()

    inv = Invocation(
        name="check",
        subcommand=None,
        options={},
        user_id="55",
        channel_id="303",
        guild_id="404",
        responder=_SpyResponder(),
        settings=settings,
        llm_client=None,
        ruleset=Dnd5eRuleset(seed=11),
    )
    opts = CheckOpts(
        ability="INT",
        score=15,
        prof_bonus=3,
        proficient=False,
        expertise=False,
        dc=12,
    )

    await check_command(inv, opts)

    assert len(inv.responder.messages) == 1
    assert get_counter("activity_log.created") == 1

    async with session_scope() as s:
        logs = (await s.execute(select(models.ActivityLog))).scalars().all()
        assert len(logs) == 1
        row = logs[0]
        assert row.event_type == "mechanics.check"
        assert row.summary == "INT check vs DC 12"
        assert row.actor_ref == "55"
        assert row.payload.get("ability") == "INT"
        assert row.payload.get("dc") == 12
        assert row.payload.get("text") == inv.responder.messages[0]


@pytest.mark.asyncio
async def test_roll_command_activity_log_toggle(db):
    reset_counters()

    enabled_settings = type(
        "Settings",
        (),
        {
            "features_activity_log": True,
            "features_events": False,
        },
    )()
    disabled_settings = type(
        "Settings",
        (),
        {
            "features_activity_log": False,
            "features_events": False,
        },
    )()

    enabled_inv = Invocation(
        name="roll",
        subcommand=None,
        options={},
        user_id="77",
        channel_id="909",
        guild_id="808",
        responder=_SpyResponder(),
        settings=enabled_settings,
        llm_client=None,
        ruleset=Dnd5eRuleset(seed=17),
    )
    await roll(enabled_inv, RollOpts(expr="2d6+1"))

    async with session_scope() as s:
        logs = (await s.execute(select(models.ActivityLog))).scalars().all()
        assert len(logs) == 1
        row = logs[0]
        assert row.event_type == "mechanics.roll"
        assert row.summary == "Roll 2d6+1"
        assert row.actor_ref == "77"
        payload = row.payload
        assert payload.get("expression") == "2d6+1"
        assert payload.get("text") == enabled_inv.responder.messages[0]
        assert isinstance(payload.get("total"), int)

    # Disable flag and ensure no additional rows are written
    disabled_inv = Invocation(
        name="roll",
        subcommand=None,
        options={},
        user_id="77",
        channel_id="909",
        guild_id="808",
        responder=_SpyResponder(),
        settings=disabled_settings,
        llm_client=None,
        ruleset=Dnd5eRuleset(seed=21),
    )
    await roll(disabled_inv, RollOpts(expr="1d20"))

    assert get_counter("activity_log.created") == 1
    async with session_scope() as s:
        rows = (await s.execute(select(models.ActivityLog))).scalars().all()
        assert len(rows) == 1
