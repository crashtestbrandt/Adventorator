import pytest

from Adventorator import repos
from Adventorator.db import session_scope
from Adventorator.schemas import CharacterSheet


@pytest.mark.asyncio
async def test_append_event_normalizes_actor_name(db):
    guild_id = 3201
    channel_id = 3202
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        # create a character so we have a numeric id to reference
        sheet = CharacterSheet(
            name="Borin",
            **{
                "class": "Fighter",
                "level": 2,
                "abilities": {"STR": 15, "DEX": 12, "CON": 14, "INT": 8, "WIS": 10, "CHA": 9},
                "proficiency_bonus": 2,
                "ac": 15,
                "speed": 30,
            },
        )
        ch = await repos.upsert_character(s, campaign_id=campaign.id, player_id=None, sheet=sheet)
        # Append an event with actor as numeric id (int)
        ev = await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id=ch.id,  # int ident
            type="apply_damage",
            payload={"target": "x", "amount": 1},
            request_id="req-norm-1",
        )
        assert ev.actor_id == "Borin"
        # And when using string id
        ev2 = await repos.append_event(
            s,
            scene_id=scene.id,
            actor_id=str(ch.id),
            type="heal",
            payload={"target": "x", "amount": 1},
            request_id="req-norm-2",
        )
        assert ev2.actor_id == "Borin"
