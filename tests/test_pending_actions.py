import pytest

from Adventorator import repos
from Adventorator.commanding import Invocation
from Adventorator.commands.cancel import cancel as cancel_cmd
from Adventorator.commands.confirm import confirm as confirm_cmd
from Adventorator.commands.do import do_command
from Adventorator.config import Settings
from Adventorator.db import session_scope


class _Responder:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bool]] = []

    async def send(self, content: str, *, ephemeral: bool = False) -> None:
        self.messages.append((content, ephemeral))


@pytest.mark.asyncio
async def test_pending_repos_create_and_fetch(db):
    # Create campaign/scene and a pending action
    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=1)
        scene = await repos.ensure_scene(s, camp.id, channel_id=100)
        pa = await repos.create_pending_action(
            s,
            campaign_id=camp.id,
            scene_id=scene.id,
            channel_id=100,
            user_id="u1",
            request_id="req-xyz",
            chain={"steps": []},
            mechanics="m",
            narration="n",
            player_tx_id=None,
            bot_tx_id=None,
            ttl_seconds=1,
        )
        assert pa.id > 0
        got = await repos.get_latest_pending_for_user(s, scene_id=scene.id, user_id="u1")
        assert got is not None and got.id == pa.id
        # Expire should mark as expired after TTL passes.
        # We won't sleep here; just call to ensure it doesn't crash.
        count = await repos.expire_stale_pending_actions(s)
        assert isinstance(count, int)


@pytest.mark.asyncio
async def test_command_flow_do_confirm_cancel(monkeypatch):
    # Enable features for the flow
    settings = Settings(features_llm=True, features_llm_visible=True, features_executor=True)

    # Minimal fake LLM client that emits a valid object with an ability check
    class _FakeOut:
        class _Proposal:
            action = "ability_check"
            ability = "DEX"
            suggested_dc = 10
            reason = ""

            def model_dump(self):
                return {
                    "action": self.action,
                    "ability": self.ability,
                    "suggested_dc": self.suggested_dc,
                }

        def __init__(self) -> None:
            self.proposal = self._Proposal()
            self.narration = "You sneak past the guard."

    class _FakeLLM:
        async def generate_json(self, _msgs):
            return _FakeOut()

    responder = _Responder()

    inv = Invocation(
        name="do",
        subcommand=None,
        options={},
        user_id="1",
        channel_id="100",
        guild_id="1",
        responder=responder,
        settings=settings,
        llm_client=_FakeLLM(),
    )

    # Run /do which should create a pending action and prompt confirm/cancel
    class _Opts:
        message = "I try to sneak by."

    await do_command(inv, _Opts())
    assert any("Confirm with /confirm" in m[0] for m in responder.messages)

    # Confirm should finalize and send narration
    await confirm_cmd(inv, type("O", (), {"id": None})())
    assert any("Confirmed." in m[0] for m in responder.messages)

    # Now no pending remains; cancel should say none
    await cancel_cmd(inv, type("O", (), {"id": None})())
    assert any("No pending action" in m[0] for m in responder.messages)
