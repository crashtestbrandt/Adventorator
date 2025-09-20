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
async def test_pending_dedup_create_idempotent(db):
    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=1)
        scene = await repos.ensure_scene(s, camp.id, channel_id=100)
    pa1 = await repos.create_pending_action(
        s,
        campaign_id=camp.id,
        scene_id=scene.id,
        channel_id=100,
        user_id="u1",
        request_id="req-1",
        chain={"steps": [{"tool": "check", "args": {"dc": 10}}]},
        mechanics="m",
        narration="n",
        player_tx_id=None,
        bot_tx_id=None,
        ttl_seconds=300,
    )
    pa2 = await repos.create_pending_action(
        s,
        campaign_id=camp.id,
        scene_id=scene.id,
        channel_id=100,
        user_id="u1",
        request_id="req-2",
        chain={"steps": [{"tool": "check", "args": {"dc": 10}}]},
        mechanics="m",
        narration="n",
        player_tx_id=None,
        bot_tx_id=None,
        ttl_seconds=300,
    )
    assert pa1.id == pa2.id, "same chain should dedup"


@pytest.mark.asyncio
async def test_pending_expire_marks_status(db):
    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=1)
        scene = await repos.ensure_scene(s, camp.id, channel_id=200)
    await repos.create_pending_action(
        s,
        campaign_id=camp.id,
        scene_id=scene.id,
        channel_id=200,
        user_id="u2",
        request_id="req-exp",
        chain={"steps": []},
        mechanics="m",
        narration="n",
        player_tx_id=None,
        bot_tx_id=None,
        ttl_seconds=0,
    )
    count = await repos.expire_stale_pending_actions(s)
    assert isinstance(count, int)


@pytest.mark.asyncio
async def test_confirm_then_cancel_noop(db):
    settings = Settings(features_llm=True, features_llm_visible=True, features_executor=True)

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
        user_id="2",
        channel_id="300",
        guild_id="1",
        responder=responder,
        settings=settings,
        llm_client=_FakeLLM(),
    )

    class _Opts:
        message = "I try to sneak by."

    await do_command(inv, _Opts())
    await confirm_cmd(inv, type("O", (), {"id": None})())
    # Subsequent cancel should report none
    await cancel_cmd(inv, type("O", (), {"id": None})())
    assert any("No pending action" in m[0] for m in responder.messages)
