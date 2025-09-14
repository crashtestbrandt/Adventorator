# tests/test_encounter_status_command.py

import pytest

from Adventorator import repos
from Adventorator.commanding import Invocation
from Adventorator.commands.encounter import EncounterStatusOpts, encounter_status
from Adventorator.db import session_scope


class _SpyResponder:
    def __init__(self):
        self.messages: list[str] = []

    async def send(self, content: str, *, ephemeral: bool = False) -> None:  # noqa: D401
        self.messages.append(content)


@pytest.mark.asyncio
async def test_encounter_status_setup_and_active(db, monkeypatch):
    # Force features_combat on through a fake settings on invocation
    class _S:
        features_combat = True

    guild_id = 42
    channel_id = 99
    user_id = 7

    # Create a scene and an encounter with a couple of combatants
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        enc = await repos.create_encounter(s, scene_id=scene.id)
        cb1 = await repos.add_combatant(s, encounter_id=enc.id, name="Aria", hp=10)
        cb2 = await repos.add_combatant(s, encounter_id=enc.id, name="Borin", hp=12)
        # Still setup: no initiative yet

    inv = Invocation(
        name="encounter",
        subcommand="status",
        options={},
        user_id=str(user_id),
        channel_id=str(channel_id),
        guild_id=str(guild_id),
        responder=_SpyResponder(),
        settings=_S(),
        llm_client=None,
        ruleset=None,
    )
    opts = EncounterStatusOpts()
    await encounter_status(inv, opts)
    assert len(inv.responder.messages) == 1
    txt = inv.responder.messages[0]
    assert "Encounter status" in txt
    assert "(no combatants)" not in txt
    assert "Aria" in txt and "Borin" in txt

    # Now set initiative and mark encounter active
    async with session_scope() as s:
        # Re-fetch enc id via latest in this scene
        enc2 = await repos.get_active_or_setup_encounter_for_scene(s, scene_id=scene.id)
        assert enc2 is not None
        # Set initiatives
        # Order: Borin 15, Aria 12 -> Borin first
        await repos.set_combatant_initiative(s, combatant_id=cb2.id, initiative=15)
        await repos.set_combatant_initiative(s, combatant_id=cb1.id, initiative=12)
        # Manually move to active state like service would once all have initiative
        await repos.update_encounter_state(
            s,
            encounter_id=enc2.id,
            status="active",
            round=1,
            active_idx=0,
        )

    inv2 = Invocation(
        name="encounter",
        subcommand="status",
        options={},
        user_id=str(user_id),
        channel_id=str(channel_id),
        guild_id=str(guild_id),
        responder=_SpyResponder(),
        settings=_S(),
        llm_client=None,
        ruleset=None,
    )
    await encounter_status(inv2, EncounterStatusOpts())
    out = inv2.responder.messages[0]
    assert "round 1" in out
    # Active marker should point at first in order (Borin 15)
    # Expect a line starting with the marker and Borin's name
    assert "➡️" in out and "Borin" in out


@pytest.mark.asyncio
async def test_encounter_status_feature_flag_off(db):
    class _S:
        features_combat = False

    inv = Invocation(
        name="encounter",
        subcommand="status",
        options={},
        user_id="1",
        channel_id="2",
        guild_id="3",
        responder=_SpyResponder(),
        settings=_S(),
        llm_client=None,
        ruleset=None,
    )
    await encounter_status(inv, EncounterStatusOpts())
    assert "Combat features disabled" in inv.responder.messages[0]
