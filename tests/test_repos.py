# tests/test_repos.py

import pytest

from Adventorator import repos
from Adventorator.schemas import CharacterSheet


@pytest.mark.asyncio
async def test_character_upsert_and_get(db):
    camp = await repos.get_or_create_campaign(db, guild_id=123, name="Test")
    player = await repos.get_or_create_player(db, 42, "Goose")
    sheet = CharacterSheet.model_validate(
        {
            "name": "Goose",
            "class": "Rogue",
            "level": 3,
            "abilities": {"STR": 13, "DEX": 17, "CON": 14, "INT": 15, "WIS": 13, "CHA": 13},
            "proficiency_bonus": 2,
            "ac": 15,
            "hp": {"current": 21, "max": 21, "temp": 0},
            "speed": 30,
        }
    )
    ch = await repos.upsert_character(db, camp.id, player.id, sheet)
    assert ch.name == "Goose"

    got = await repos.get_character(db, camp.id, "Goose")
    assert got is not None and got.sheet["class"] == "Rogue"
