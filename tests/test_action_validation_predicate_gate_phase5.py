import pytest

from Adventorator import models
from Adventorator.action_validation import PredicateContext, evaluate_predicates
from Adventorator.db import session_scope
from Adventorator.planner_schemas import PlannerOutput


@pytest.mark.asyncio
async def test_predicate_gate_passes_for_known_character():
    async with session_scope() as session:
        campaign = models.Campaign(guild_id=1, name="Test Campaign")
        session.add(campaign)
        await session.flush()
        scene = models.Scene(campaign_id=campaign.id, channel_id=123)
        session.add(scene)
        await session.flush()
        character = models.Character(
            campaign_id=campaign.id,
            name="Aria",
            sheet={"abilities": {"DEX": 14}},
        )
        session.add(character)
        await session.flush()
        campaign_id = campaign.id
        scene_id = scene.id

    out = PlannerOutput(command="check", args={"ability": "DEX", "dc": 12, "actor": "Aria"})
    ctx = PredicateContext(
        campaign_id=campaign_id,
        scene_id=scene_id,
        user_id=42,
        allowed_actors=("Aria",),
    )
    result = await evaluate_predicates(out, context=ctx)
    assert result.ok
    assert result.failed == []


@pytest.mark.asyncio
async def test_predicate_gate_unknown_ability_rejected():
    async with session_scope() as session:
        campaign = models.Campaign(guild_id=1, name="Test Campaign")
        session.add(campaign)
        await session.flush()
        scene = models.Scene(campaign_id=campaign.id, channel_id=456)
        session.add(scene)
        await session.flush()
        campaign_id = campaign.id
        scene_id = scene.id

    out = PlannerOutput(command="check", args={"ability": "LCK", "dc": 12})
    ctx = PredicateContext(
        campaign_id=campaign_id,
        scene_id=scene_id,
        user_id=None,
        allowed_actors=(),
    )
    result = await evaluate_predicates(out, context=ctx)
    assert not result.ok
    assert any(f.code == "known_ability" for f in result.failed)


@pytest.mark.asyncio
async def test_predicate_gate_missing_actor_rejected():
    async with session_scope() as session:
        campaign = models.Campaign(guild_id=1, name="Test Campaign")
        session.add(campaign)
        await session.flush()
        scene = models.Scene(campaign_id=campaign.id, channel_id=789)
        session.add(scene)
        await session.flush()
        # Seed a different character to ensure DB lookups work
        character = models.Character(
            campaign_id=campaign.id,
            name="Existing",
            sheet={"abilities": {"STR": 12}},
        )
        session.add(character)
        await session.flush()
        campaign_id = campaign.id
        scene_id = scene.id

    out = PlannerOutput(command="check", args={"ability": "DEX", "actor": "Unknown"})
    ctx = PredicateContext(
        campaign_id=campaign_id,
        scene_id=scene_id,
        user_id=None,
        allowed_actors=("Existing",),
    )
    result = await evaluate_predicates(out, context=ctx)
    assert not result.ok
    failure_codes = {f.code for f in result.failed}
    assert "actor_in_allowed_actors" in failure_codes
    assert "exists(actor)" in failure_codes
