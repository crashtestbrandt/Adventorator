import pytest

from Adventorator.executor import Executor, ToolCallChain, ToolStep


@pytest.mark.asyncio
async def test_executor_preview_attack_hit_and_miss():
    ex = Executor()
    # First, a hit with deterministic seed
    chain = ToolCallChain(
        request_id="req-attack-1",
        scene_id=1,
        steps=[
            ToolStep(
                tool="attack",
                args={
                    "attacker": "Alice",
                    "target": "Goblin",
                    "attack_bonus": 5,
                    "target_ac": 10,
                    "damage": {"dice": "1d6", "mod": 2, "type": "slashing"},
                    "seed": 42,
                },
            ),
        ],
    )
    prev = await ex.execute_chain(chain, dry_run=True)
    assert len(prev.items) == 1
    mech = prev.items[0].mechanics
    # Predicted events should exist (apply_damage on hit or attack.missed)
    assert prev.items[0].predicted_events is not None
    assert "Attack +5 vs AC 10" in mech
    # Seed should give a valid d20 and a HIT/CRIT/MISS label present
    assert any(x in mech for x in ["-> HIT", "-> CRIT", "-> MISS"])  # formatting presence check

    # Now a guaranteed miss by setting very high AC
    chain_miss = ToolCallChain(
        request_id="req-attack-2",
        scene_id=1,
        steps=[
            ToolStep(
                tool="attack",
                args={
                    "attacker": "Alice",
                    "target": "Goblin",
                    "attack_bonus": 0,
                    "target_ac": 30,
                    "damage": {"dice": "1d6"},
                    "seed": 1,
                },
            ),
        ],
    )
    prev2 = await ex.execute_chain(chain_miss, dry_run=True)
    mech2 = prev2.items[0].mechanics
    assert "-> MISS" in mech2
    # Predicted events should include an attack.missed event
    assert any(ev.get("type") == "attack.missed" for ev in prev2.items[0].predicted_events)
