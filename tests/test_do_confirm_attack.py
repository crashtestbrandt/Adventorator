import pytest

from Adventorator.command_loader import load_all_commands
from Adventorator.commanding import Invocation, find_command
from Adventorator.metrics import get_counter, reset_counters
from Adventorator.schemas import LLMOutput, LLMProposal


class _SpyResponder:
    def __init__(self):
        self.messages = []

    async def send(self, content: str, *, ephemeral: bool = False):  # noqa: ANN001
        self.messages.append((content, ephemeral))


class _FakeLLM:
    def __init__(self, output: LLMOutput | None):
        self._out = output

    async def generate_json(self, messages, system_prompt=None):  # noqa: ANN001
        return self._out


def _neutral_sheet(_ability: str):
    return {
        "score": 10,
        "proficient": False,
        "expertise": False,
        "prof_bonus": 2,
    }


@pytest.mark.asyncio
async def test_do_then_confirm_attack_writes_events(monkeypatch, db):
    reset_counters()
    load_all_commands()
    # Enable executor + confirm + events + combat
    settings = type(
        "S",
        (),
        {
            "features_llm": True,
            "features_llm_visible": False,
            "features_executor": True,
            "features_executor_confirm": True,
            "features_events": True,
            "features_combat": True,
            "features_action_validation": True,
            "llm_max_prompt_tokens": None,
        },
    )()

    # Fake LLM to propose an attack
    out = LLMOutput(
        proposal=LLMProposal(
            action="attack",
            attacker="Alice",
            target="Goblin",
            attack_bonus=5,
            target_ac=10,
            damage={"dice": "1d6", "mod": 2},
            reason="Strike the goblin.",
        ),
        narration="Alice strikes the goblin.",
    )
    llm = _FakeLLM(out)

    # Build invocation for /do
    responder = _SpyResponder()
    inv = Invocation(
        name="do",
        subcommand=None,
        options={"message": "I attack the goblin"},
        user_id="1",
        channel_id="1",
        guild_id="1",
        responder=responder,
        settings=settings,
        llm_client=llm,
    )

    cmd_do = find_command("do", None)
    assert cmd_do is not None
    opts_do = cmd_do.option_model.model_validate(inv.options)
    await cmd_do.handler(inv, opts_do)

    # Should present pending action with mechanics and instructions
    assert responder.messages, "Expected a pending message"
    assert any("Confirm with /confirm" in m[0] for m in responder.messages)

    # Now run /confirm
    cmd_confirm = find_command("confirm", None)
    assert cmd_confirm is not None
    inv_confirm = Invocation(
        name="confirm",
        subcommand=None,
        options={},
        user_id="1",
        channel_id="1",
        guild_id="1",
        responder=_SpyResponder(),
        settings=settings,
    )
    opts_conf = cmd_confirm.option_model.model_validate(inv_confirm.options)
    await cmd_confirm.handler(inv_confirm, opts_conf)

    # Metrics: ensure apply path recorded attack tool usage
    assert get_counter("pending.confirm.ok") >= 1
    assert get_counter("executor.apply.ok") >= 1
    assert get_counter("executor.apply.tool.attack") >= 1
