import pytest

from Adventorator.executor import Executor, ToolCallChain, ToolStep


@pytest.mark.asyncio
async def test_executor_preview_roll_and_check():
    ex = Executor()
    chain = ToolCallChain(
        request_id="req-1",
        scene_id=1,
        steps=[
            ToolStep(tool="roll", args={"expr": "1d6", "seed": 123}),
            ToolStep(tool="check", args={"ability": "DEX", "score": 12, "dc": 10, "seed": 123}),
        ],
    )
    prev = await ex.execute_chain(chain, dry_run=True)
    assert len(prev.items) == 2
    assert "Roll 1d6" in prev.items[0].mechanics
    assert "Check: DEX vs DC 10" in prev.items[1].mechanics
