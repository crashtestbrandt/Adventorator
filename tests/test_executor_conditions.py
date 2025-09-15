import pytest

from Adventorator.executor import Executor, ToolCallChain, ToolStep


@pytest.mark.asyncio
async def test_executor_preview_apply_condition_and_clear():
    ex = Executor()
    chain_apply = ToolCallChain(
        request_id="req-cond-1",
        scene_id=1,
        steps=[
            ToolStep(
                tool="apply_condition",
                args={"target": "Goblin", "condition": "Prone", "duration": 2},
            )
        ],
    )
    prev = await ex.execute_chain(chain_apply, dry_run=True)
    assert prev.items and "Apply condition 'Prone'" in prev.items[0].mechanics
    assert prev.items[0].predicted_events is not None
    assert prev.items[0].predicted_events[0]["type"] == "condition.applied"

    chain_clear = ToolCallChain(
        request_id="req-cond-2",
        scene_id=1,
        steps=[
            ToolStep(
                tool="clear_condition",
                args={"target": "Goblin", "condition": "Prone"},
            )
        ],
    )
    prev2 = await ex.execute_chain(chain_clear, dry_run=True)
    assert prev2.items and "Clear condition 'Prone'" in prev2.items[0].mechanics
    assert prev2.items[0].predicted_events and prev2.items[0].predicted_events[0]["type"] == "condition.cleared"
