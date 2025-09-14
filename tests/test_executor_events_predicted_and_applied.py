import pytest

from Adventorator import repos
from Adventorator.config import Settings
from Adventorator.db import session_scope
from Adventorator.executor import Executor, ToolCallChain, ToolStep


@pytest.mark.asyncio
async def test_predicted_events_present_in_preview_and_written_on_apply(db, monkeypatch):
    ex = Executor()
    scene_id = 999
    chain = ToolCallChain(
        request_id="req-apply-dmg",
        scene_id=scene_id,
        steps=[
            ToolStep(tool="apply_damage", args={"target": "char-1", "amount": 5}),
        ],
        actor_id="user-1",
    )

    # Preview: predicted events should be present but not written
    prev = await ex.execute_chain(chain, dry_run=True)
    assert len(prev.items) == 1
    item = prev.items[0]
    assert item.predicted_events and item.predicted_events[0]["type"] == "apply_damage"

    # Ensure no events yet in DB (requires a real scene to list; create one and rebind id)
    guild_id = 101
    channel_id = 202
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        scene_id = scene.id
    chain = ToolCallChain(
        request_id="req-apply-dmg",
        scene_id=scene_id,
        steps=[
            ToolStep(tool="apply_damage", args={"target": "char-1", "amount": 5}),
        ],
        actor_id="user-1",
    )

    # Apply with events disabled: nothing written
    monkeypatch.setattr(
        "Adventorator.executor.load_settings",
        lambda: Settings(features_events=False),
        raising=True,
    )
    await ex.apply_chain(chain)
    async with session_scope() as s:
        evs = await repos.list_events(s, scene_id=scene_id)
        assert len(evs) == 0

    # Apply with events enabled: predicted event is written
    monkeypatch.setattr(
        "Adventorator.executor.load_settings",
        lambda: Settings(features_events=True),
        raising=True,
    )
    prev3 = await ex.apply_chain(chain)
    assert "Apply 5 damage" in prev3.items[0].mechanics
    async with session_scope() as s:
        evs2 = await repos.list_events(s, scene_id=scene_id)
        assert len(evs2) == 1
        assert evs2[0].type == "apply_damage"
        assert evs2[0].payload == {"target": "char-1", "amount": 5}
        assert evs2[0].actor_id == "user-1"
