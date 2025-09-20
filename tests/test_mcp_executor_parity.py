"""Parity tests for the MCP adapter layer in the executor."""

from __future__ import annotations

from Adventorator import metrics
from Adventorator.executor import Executor


def _invoke(executor: Executor, tool: str, args: dict, monkeypatch, *, enabled: bool):
    monkeypatch.setenv("FEATURES_MCP", "true" if enabled else "false")
    spec = executor.registry.get(tool)
    assert spec is not None
    return spec.handler(args, dry_run=True)


def test_mcp_check_matches_legacy(monkeypatch):
    executor = Executor()
    args = {
        "ability": "DEX",
        "score": 14,
        "dc": 12,
        "proficient": True,
        "expertise": False,
        "prof_bonus": 2,
        "seed": 42,
    }
    legacy = _invoke(executor, "check", args, monkeypatch, enabled=False)
    metrics.reset_counters()
    mcp = _invoke(executor, "check", args, monkeypatch, enabled=True)
    assert mcp == legacy
    assert metrics.get_counter("executor.mcp.call") == 1


def test_mcp_attack_matches_legacy(monkeypatch):
    executor = Executor()
    args = {
        "attacker": "Hero",
        "target": "Goblin",
        "attack_bonus": 5,
        "target_ac": 12,
        "damage": {"dice": "1d8", "mod": 3, "type": "slashing"},
        "advantage": False,
        "disadvantage": False,
        "seed": 99,
    }
    legacy = _invoke(executor, "attack", args, monkeypatch, enabled=False)
    metrics.reset_counters()
    mcp = _invoke(executor, "attack", args, monkeypatch, enabled=True)
    assert mcp == legacy
    # Attack calls MCP once for the attack roll (damage handled inside adapter).
    assert metrics.get_counter("executor.mcp.call") == 1


def test_mcp_apply_damage_noop_matches(monkeypatch):
    executor = Executor()
    args = {"target": "Goblin", "amount": 4}
    legacy = _invoke(executor, "apply_damage", args, monkeypatch, enabled=False)
    metrics.reset_counters()
    mcp = _invoke(executor, "apply_damage", args, monkeypatch, enabled=True)
    assert mcp == legacy
    # Adapter still invoked even though no HP context provided.
    assert metrics.get_counter("executor.mcp.call") == 1
