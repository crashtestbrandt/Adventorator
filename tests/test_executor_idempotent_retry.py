import pytest

from Adventorator import repos
from Adventorator.config import load_settings
from Adventorator.executor import (
    ToolCallChain,
    ToolCallItem,
    execute_tool_call_chain,
)
from Adventorator.metrics import get_counter, reset_counters


@pytest.mark.asyncio
async def test_executor_idempotent_retry_events_disabled_flag_guard(db):
    # Ensure events disabled causes no append attempts (baseline safety)
    settings = load_settings()
    assert settings.features_events is False
    camp = await repos.get_or_create_campaign(db, 9, name="Idem")
    scene = await repos.ensure_scene(db, camp.id, 900)
    chain = ToolCallChain(
        scene_id=scene.id,
        actor_id="c",
        request_id="req-x",
        items=[ToolCallItem(tool="roll", mechanics="d20", narration="n")],
    )
    reset_counters()
    await execute_tool_call_chain(chain)
    # No events.applied increment when flag disabled
    assert get_counter("events.applied") == 0


@pytest.mark.asyncio
async def test_executor_idempotent_retry_same_request_id(db, monkeypatch):
    # Force-enable events for this test run
    from Adventorator import config as cfg

    monkeypatch.setenv("FEATURES_EVENTS", "true")
    cfg._SETTINGS = None  # reset cache
    camp = await repos.get_or_create_campaign(db, 10, name="IdemRetry")
    scene = await repos.ensure_scene(db, camp.id, 1000)
    chain1 = ToolCallChain(
        scene_id=scene.id,
        actor_id="c",
        request_id="req-repeat",
        items=[ToolCallItem(tool="roll", mechanics="d20", narration="n")],
    )
    chain2 = ToolCallChain(
        scene_id=scene.id,
        actor_id="c",
        request_id="req-repeat",
        items=[ToolCallItem(tool="roll", mechanics="d20", narration="n")],
    )

    reset_counters()

    await execute_tool_call_chain(chain1)
    await execute_tool_call_chain(chain2)
    evs = await repos.list_events(db, scene_id=scene.id)

    assert len(evs) == 1
    assert [e.replay_ordinal for e in evs] == [0]
    assert get_counter("events.idempotent_reuse") == 1
