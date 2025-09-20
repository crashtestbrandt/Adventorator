import pytest

from Adventorator.action_validation import plan_registry
from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, find_command
from Adventorator.metrics import get_counter, reset_counters


class _SpyResponder:
    def __init__(self):
        self.messages = []

    async def send(self, content: str, *, ephemeral: bool = False):  # noqa: ANN001
        self.messages.append((content, ephemeral))


class _FakeLLM:
    def __init__(self, payload: str):
        self._payload = payload

    async def generate_response(self, messages):  # noqa: ANN001
        return self._payload


@pytest.mark.asyncio
async def test_predicate_gate_success_metrics():
    """Success path increments ok metric and plan feasible True."""
    reset_counters()
    plan_registry.reset()
    load_all_commands()
    cmd = find_command("plan", None)
    assert cmd is not None

    # LLM output uses /roll which should not trigger any predicate failures
    inv = Invocation(
        name="plan",
        subcommand=None,
        options={"message": "roll a d20"},
        user_id="20",
        channel_id="701",
        guild_id="801",
        responder=_SpyResponder(),
        settings=type(
            "S",
            (),
            {
                "features_llm": True,
                "features_llm_visible": False,
                "features_action_validation": True,
                "features_predicate_gate": True,
            },
        )(),
        llm_client=_FakeLLM('{"command": "roll", "args": {"expr": "1d20"}}'),
    )
    opts = cmd.option_model.model_validate(inv.options)
    await cmd.handler(inv, opts)

    assert get_counter("predicate.gate.ok") == 1
    assert get_counter("predicate.gate.error") == 0


@pytest.mark.asyncio
async def test_predicate_gate_failure_metrics_known_ability():
    """Unknown ability triggers known_ability failure and counters."""
    reset_counters()
    plan_registry.reset()
    load_all_commands()
    cmd = find_command("plan", None)
    assert cmd is not None

    # Ability is invalid triggering known_ability predicate failure
    inv = Invocation(
        name="plan",
        subcommand=None,
        options={"message": "do an XYZ ability check"},
        user_id="21",
        channel_id="702",
        guild_id="802",
        responder=_SpyResponder(),
        settings=type(
            "S",
            (),
            {
                "features_llm": True,
                "features_llm_visible": False,
                "features_action_validation": True,
                "features_predicate_gate": True,
            },
        )(),
        # Fake planner output with invalid ability
        llm_client=_FakeLLM('{"command": "check", "args": {"ability": "XYZ"}}'),
    )
    opts = cmd.option_model.model_validate(inv.options)
    await cmd.handler(inv, opts)

    assert get_counter("predicate.gate.ok") == 0
    assert get_counter("predicate.gate.error") == 1
    # Failure reason counter should exist
    assert get_counter("predicate.gate.fail_reason.known_ability") == 1


@pytest.mark.asyncio
async def test_predicate_gate_failure_plan_feasible_false():
    """Failure stores infeasible plan with predicate failures recorded."""
    reset_counters()
    plan_registry.reset()
    load_all_commands()
    cmd = find_command("plan", None)
    assert cmd is not None

    inv = Invocation(
        name="plan",
        subcommand=None,
        options={"message": "check ABC with dc 900"},
        user_id="22",
        channel_id="703",
        guild_id="803",
        responder=_SpyResponder(),
        settings=type(
            "S",
            (),
            {
                "features_llm": True,
                "features_llm_visible": False,
                "features_action_validation": True,
                "features_predicate_gate": True,
            },
        )(),
        llm_client=_FakeLLM('{"command": "check", "args": {"ability": "ABC", "dc": 900}}'),
    )
    opts = cmd.option_model.model_validate(inv.options)
    await cmd.handler(inv, opts)

    # Metrics
    assert get_counter("predicate.gate.error") == 1
    assert get_counter("predicate.gate.fail_reason.known_ability") == 1
    assert get_counter("predicate.gate.fail_reason.dc_in_bounds") == 1

    # Registry should contain exactly one plan with feasible False
    plans = list(plan_registry._PLANS.values())  # noqa: SLF001 accessing internal for test
    assert len(plans) == 1
    p = plans[0]
    assert p.feasible is False
    assert p.steps == []
    assert len(p.failed_predicates) >= 2
