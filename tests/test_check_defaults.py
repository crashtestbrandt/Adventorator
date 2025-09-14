# test_check_defaults.py

import asyncio

import pytest

from Adventorator.commanding import Invocation
from Adventorator.commands.check import check_command, CheckOpts
from Adventorator.db import session_scope
from Adventorator import repos, models


class _SpyResponder:
    def __init__(self):
        self.messages: list[str] = []

    async def send(self, content: str, *, ephemeral: bool = False) -> None:  # noqa: D401
        self.messages.append(content)


@pytest.mark.asyncio
async def test_check_defaults_from_character(db):
    # Setup: create campaign, player, character sheet with DEX 16, PB 3
    guild_id = 123
    channel_id = 456
    user_id = 789
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        await repos.ensure_scene(s, campaign.id, channel_id)
        # Create player and character
        player = await repos.get_or_create_player(s, user_id, display_name="Tester")
        sheet = {
            "abilities": {"STR": 10, "DEX": 16, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
            "proficiency_bonus": 3,
        }
        c = models.Character(
            campaign_id=campaign.id,
            player_id=player.id,
            name="Aria Nightwind",
            sheet=sheet,
        )
        s.add(c)
        await s.flush()

    # Invoke /check without specifying score/prof bonus
    inv = Invocation(
        name="check",
        subcommand=None,
        options={},
        user_id=str(user_id),
        channel_id=str(channel_id),
        guild_id=str(guild_id),
        responder=_SpyResponder(),
        settings=None,
        llm_client=None,
        ruleset=None,
    )
    opts = CheckOpts(ability="DEX")

    await check_command(inv, opts)
    # Validate that the responder got a message including mod for DEX 16 (mod +3) and PB 3 only applies if proficient, which defaults to False.
    # We at least ensure the text contains "DEX" and a total consistent with d20 +/- mod cannot be easily asserted since RNG is in ruleset; but we can ensure the header is correct.
    assert len(inv.responder.messages) == 1
    assert "DEX" in inv.responder.messages[0]
    assert "DC" in inv.responder.messages[0]
    assert "mod: +3" in inv.responder.messages[0]
