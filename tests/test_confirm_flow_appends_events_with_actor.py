import pytest

from Adventorator import repos
from Adventorator.commanding import Invocation
from Adventorator.commands.confirm import ConfirmOpts, confirm
from Adventorator.config import Settings
from Adventorator.db import session_scope


class _SpyResponder:
    def __init__(self):
        self.messages = []

    async def send(self, content: str, *, ephemeral: bool = False) -> None:
        self.messages.append(content)


@pytest.mark.asyncio
async def test_confirm_appends_predicted_events_with_actor(db, monkeypatch):
    # Setup a pending action with an executor chain calling apply_damage
    guild_id = 5001
    channel_id = 5002
    user_id = 5003
    async with session_scope() as s:
        campaign = await repos.get_or_create_campaign(s, guild_id)
        scene = await repos.ensure_scene(s, campaign.id, channel_id)
        pa = await repos.create_pending_action(
            s,
            campaign_id=campaign.id,
            scene_id=scene.id,
            channel_id=channel_id,
            user_id=str(user_id),
            request_id="req-confirm-1",
            chain={
                "request_id": "req-confirm-1",
                "scene_id": scene.id,
                "actor_id": str(user_id),
                "steps": [
                    {
                        "tool": "apply_damage",
                        "args": {"target": "char-2", "amount": 7},
                        "requires_confirmation": True,
                        "visibility": "ephemeral",
                    }
                ],
            },
            mechanics="Apply 7 damage",
            narration="You strike true.",
            player_tx_id=None,
            bot_tx_id=None,
        )

    # Enable executor + confirm + events
    settings = Settings(
        features_executor=True,
        features_executor_confirm=True,
        features_events=True,
    )
    monkeypatch.setattr("Adventorator.executor.load_settings", lambda: settings, raising=True)

    inv = Invocation(
        name="confirm",
        subcommand=None,
        options={},
        user_id=str(user_id),
        channel_id=str(channel_id),
        guild_id=str(guild_id),
        responder=_SpyResponder(),
        settings=settings,
        llm_client=None,
        ruleset=None,
    )

    await confirm(inv, ConfirmOpts(id=pa.id))

    # Assert event appended with actor
    async with session_scope() as s:
        evs = await repos.list_events(s, scene_id=scene.id)
        assert any(
            (e.type == "apply_damage")
            and (e.payload == {"target": "char-2", "amount": 7})
            and (e.actor_id == str(user_id))
            for e in evs
        )
