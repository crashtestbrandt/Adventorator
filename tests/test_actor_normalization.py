import pytest

from Adventorator import repos
from Adventorator.db import session_scope
from Adventorator.schemas import CharacterSheet


@pytest.mark.asyncio
async def test_normalize_actor_ref_with_id_and_name(db):
    guild_id = 2101
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        # create a character with known id
        sheet = CharacterSheet(
            name="Thorin",
            **{
                "class": "Fighter",
                "level": 3,
                "abilities": {"STR": 16, "DEX": 10, "CON": 14, "INT": 8, "WIS": 12, "CHA": 10},
                "proficiency_bonus": 2,
                "ac": 16,
                "speed": 30,
            },
        )
        char = await repos.upsert_character(s, campaign_id=campaign.id, player_id=None, sheet=sheet)
        # id case
        from_id = await repos.normalize_actor_ref(s, campaign_id=campaign.id, ident=char.id)
        assert from_id == "Thorin"
        # string id case
        from_str = await repos.normalize_actor_ref(s, campaign_id=campaign.id, ident=str(char.id))
        assert from_str == "Thorin"
        # name passthrough
        from_name = await repos.normalize_actor_ref(s, campaign_id=campaign.id, ident="Aria")
        assert from_name == "Aria"
