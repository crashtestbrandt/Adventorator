from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import Adventorator.commands.pending as pending_module
from Adventorator import models, repos
from Adventorator.commanding import Invocation
from Adventorator.commands.cancel import CancelOpts
from Adventorator.commands.cancel import cancel as cancel_cmd
from Adventorator.commands.confirm import ConfirmOpts
from Adventorator.commands.confirm import confirm as confirm_cmd
from Adventorator.commands.do import do_command
from Adventorator.commands.pending import pending as pending_cmd
from Adventorator.config import Settings
from Adventorator.db import session_scope
from Adventorator.metrics import get_counter, reset_counters


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


@pytest.mark.asyncio
async def test_pending_missing_context():
    responder = _Responder()
    inv = Invocation(
        name="pending",
        subcommand=None,
        options={},
        user_id=None,
        channel_id=None,
        guild_id="42",
        responder=responder,
        settings=None,
        llm_client=None,
    )

    await pending_cmd(inv)

    assert responder.messages == [("❌ Missing context.", True)]


@pytest.mark.asyncio
async def test_pending_lists_latest_action(db):
    responder = _Responder()

    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=9)
        scene = await repos.ensure_scene(s, camp.id, channel_id=900)
        pa = await repos.create_pending_action(
            s,
            campaign_id=camp.id,
            scene_id=scene.id,
            channel_id=900,
            user_id="u900",
            request_id="req-900",
            chain={"steps": []},
            mechanics="Test mechanics",
            narration="Test narration",
            player_tx_id=None,
            bot_tx_id=None,
            ttl_seconds=None,
        )

    inv = Invocation(
        name="pending",
        subcommand=None,
        options={},
        user_id="u900",
        channel_id="900",
        guild_id="9",
        responder=responder,
        settings=None,
        llm_client=None,
    )

    await pending_cmd(inv)

    assert len(responder.messages) == 1
    msg, ephemeral = responder.messages[0]
    assert ephemeral is True
    assert f"[{pa.id}]" in msg
    assert "Test mechanics" in msg


@pytest.mark.asyncio
async def test_pending_no_action_informs_user(db):
    responder = _Responder()

    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=12)
        await repos.ensure_scene(s, camp.id, channel_id=1200)

    inv = Invocation(
        name="pending",
        subcommand=None,
        options={},
        user_id="u1200",
        channel_id="1200",
        guild_id="12",
        responder=responder,
        settings=None,
        llm_client=None,
    )

    await pending_cmd(inv)

    assert responder.messages == [("No pending action found.", True)]


def test_fmt_pending_includes_ttl(monkeypatch):
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    class _FakeDatetime:
        @staticmethod
        def now(tz):  # noqa: ANN001
            assert tz is timezone.utc
            return now

    monkeypatch.setattr("Adventorator.commands.pending.datetime", _FakeDatetime)

    pa = SimpleNamespace(
        id=42,
        created_at=now - timedelta(seconds=30),
        expires_at=now + timedelta(seconds=90),
        mechanics="Mechanics line\nMore text",
        narration="Narration\nMore",
    )

    out = pending_module._fmt_pending(pa)

    assert "ttl 90s" in out
    assert "Mechanics line" in out


@pytest.mark.asyncio
async def test_confirm_disabled_features():
    responder = _Responder()
    inv = Invocation(
        name="confirm",
        subcommand=None,
        options={},
        user_id="1",
        channel_id="10",
        guild_id="20",
        responder=responder,
        settings=Settings(features_executor=False),
        llm_client=None,
    )

    await confirm_cmd(inv, ConfirmOpts())

    assert responder.messages == [("Pending actions are disabled.", True)]


@pytest.mark.asyncio
async def test_confirm_no_pending_action(db):
    reset_counters()
    responder = _Responder()
    settings = Settings(features_executor=True)

    inv = Invocation(
        name="confirm",
        subcommand=None,
        options={},
        user_id="2",
        channel_id="200",
        guild_id="300",
        responder=responder,
        settings=settings,
        llm_client=None,
    )

    await confirm_cmd(inv, ConfirmOpts())

    assert responder.messages == [("No pending action to confirm.", True)]
    assert get_counter("pending.confirm.none") == 1


@pytest.mark.asyncio
async def test_confirm_executor_failure(monkeypatch, db):
    reset_counters()

    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=400)
        scene = await repos.ensure_scene(s, camp.id, channel_id=401)
        pa = await repos.create_pending_action(
            s,
            campaign_id=camp.id,
            scene_id=scene.id,
            channel_id=401,
            user_id="3",
            request_id="req-confirm",
            chain={"steps": []},
            mechanics="Test mechanics",
            narration="Test narration",
            player_tx_id=None,
            bot_tx_id=None,
            ttl_seconds=120,
        )

    async def _boom(self, chain):  # noqa: D401, ANN001
        raise RuntimeError("executor failed")

    monkeypatch.setattr("Adventorator.executor.Executor.apply_chain", _boom)

    responder = _Responder()
    inv = Invocation(
        name="confirm",
        subcommand=None,
        options={},
        user_id="3",
        channel_id="401",
        guild_id="400",
        responder=responder,
        settings=Settings(features_executor=True),
        llm_client=None,
    )

    await confirm_cmd(inv, ConfirmOpts(id=pa.id))

    assert any("Failed to apply action" in msg for msg, _ in responder.messages)
    assert get_counter("pending.confirm.error") == 1

    async with session_scope() as s:
        row = await s.get(models.PendingAction, pa.id)
        assert row is not None and row.status == "error"


@pytest.mark.asyncio
async def test_cancel_disabled_features():
    responder = _Responder()
    inv = Invocation(
        name="cancel",
        subcommand=None,
        options={},
        user_id="10",
        channel_id="20",
        guild_id="30",
        responder=responder,
        settings=Settings(features_executor=False),
        llm_client=None,
    )

    await cancel_cmd(inv, CancelOpts())

    assert responder.messages == [("Pending actions are disabled.", True)]


@pytest.mark.asyncio
async def test_cancel_no_pending_action(db):
    reset_counters()
    responder = _Responder()
    inv = Invocation(
        name="cancel",
        subcommand=None,
        options={},
        user_id="11",
        channel_id="210",
        guild_id="310",
        responder=responder,
        settings=Settings(features_executor=True),
        llm_client=None,
    )

    await cancel_cmd(inv, CancelOpts())

    assert responder.messages == [("No pending action to cancel.", True)]
    assert get_counter("pending.cancel.none") == 1


@pytest.mark.asyncio
async def test_cancel_success_updates_status(db):
    reset_counters()

    async with session_scope() as s:
        camp = await repos.get_or_create_campaign(s, guild_id=500)
        scene = await repos.ensure_scene(s, camp.id, channel_id=501)
        player_tx = await repos.write_transcript(
            s,
            campaign_id=camp.id,
            scene_id=scene.id,
            channel_id=501,
            author="player",
            content="Pending action",
            author_ref="4",
            meta={},
            status="pending",
        )
        pa = await repos.create_pending_action(
            s,
            campaign_id=camp.id,
            scene_id=scene.id,
            channel_id=501,
            user_id="4",
            request_id="req-cancel",
            chain={"steps": []},
            mechanics="Mechanics",
            narration="Narration",
            player_tx_id=player_tx.id,
            bot_tx_id=None,
            ttl_seconds=300,
        )

    responder = _Responder()
    inv = Invocation(
        name="cancel",
        subcommand=None,
        options={},
        user_id="4",
        channel_id="501",
        guild_id="500",
        responder=responder,
        settings=Settings(features_executor=True),
        llm_client=None,
    )

    await cancel_cmd(inv, CancelOpts(id=pa.id))

    assert any("Canceled your pending action" in msg for msg, _ in responder.messages)
    assert get_counter("pending.cancel.ok") == 1

    async with session_scope() as s:
        row = await s.get(models.PendingAction, pa.id)
        assert row is not None and row.status == "cancelled"
        tx = await s.get(models.Transcript, player_tx.id)
        assert tx is not None and tx.status == "error"
