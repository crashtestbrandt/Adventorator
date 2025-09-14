# Integration tests for Phase 9 events emission from commands

import pytest

from Adventorator import repos
from Adventorator.commanding import Invocation
from Adventorator.commands.check import CheckOpts, check_command
from Adventorator.commands.roll import RollOpts, roll
from Adventorator.config import Settings
from Adventorator.db import session_scope


class _SpyResponder:
    def __init__(self):
        self.messages: list[str] = []

    async def send(self, content: str, *, ephemeral: bool = False) -> None:  # noqa: D401
        self.messages.append(content)


@pytest.mark.asyncio
async def test_roll_appends_event_when_enabled(db):
    guild_id = 1001
    channel_id = 2002
    user_id = 3003

    # Pre-create scene to keep test focused
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        scene_id = scene.id

    inv = Invocation(
        name="roll",
        subcommand=None,
        options={},
        user_id=str(user_id),
        channel_id=str(channel_id),
        guild_id=str(guild_id),
        responder=_SpyResponder(),
        settings=Settings(features_events=True),
        llm_client=None,
        ruleset=None,
    )

    opts = RollOpts(expr="1d6")
    await roll(inv, opts)

    # Assert an event exists for this scene
    async with session_scope() as s:
        evs = await repos.list_events(s, scene_id=scene_id, limit=10)
        assert any(e.type == "roll.performed" for e in evs), "Expected a roll.performed event"


@pytest.mark.asyncio
async def test_check_appends_event_when_enabled(db):
    guild_id = 1111
    channel_id = 2222
    user_id = 3333

    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        scene_id = scene.id

    inv = Invocation(
        name="check",
        subcommand=None,
        options={},
        user_id=str(user_id),
        channel_id=str(channel_id),
        guild_id=str(guild_id),
        responder=_SpyResponder(),
        settings=Settings(features_events=True),
        llm_client=None,
        ruleset=None,
    )

    opts = CheckOpts(
        ability="STR",
        score=10,
        dc=10,
        proficient=False,
        expertise=False,
        prof_bonus=2,
    )
    await check_command(inv, opts)

    async with session_scope() as s:
        evs = await repos.list_events(s, scene_id=scene_id, limit=10)
        assert any(e.type == "check.performed" for e in evs), "Expected a check.performed event"
