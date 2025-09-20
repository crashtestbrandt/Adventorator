import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

import Adventorator.app as appmod
from Adventorator.app import app

client = TestClient(app)


class _DummyAsyncCM:
    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _stub_repos(monkeypatch):
    import Adventorator.repos as reposmod

    async def _campaign(*args, **kwargs):
        return SimpleNamespace(id=1)

    async def _scene(*args, **kwargs):
        return SimpleNamespace(id=1)

    async def _write(*args, **kwargs):
        return None

    async def _get_recent(*args, **kwargs):
        # Make orchestrator facts minimal
        return []

    async def _list_names(*args, **kwargs):
        return []

    monkeypatch.setattr(reposmod, "get_or_create_campaign", _campaign)
    monkeypatch.setattr(reposmod, "ensure_scene", _scene)
    monkeypatch.setattr(reposmod, "write_transcript", _write)
    monkeypatch.setattr(reposmod, "get_recent_transcripts", _get_recent)
    monkeypatch.setattr(reposmod, "list_character_names", _list_names)


def test_do_shadow_ephemeral(monkeypatch):
    # Disable signature verification and DB
    monkeypatch.setattr(appmod, "verify_ed25519", lambda *a, **k: True)
    monkeypatch.setattr(appmod, "session_scope", lambda: _DummyAsyncCM())

    # Enable LLM feature but shadow visibility off
    monkeypatch.setattr(
        appmod,
        "settings",
        SimpleNamespace(
            features_llm=True,
            features_llm_visible=False,
            llm_max_prompt_tokens=256,
            discord_public_key="",
            env="test",
            discord_dev_public_key="",
        ),
    )

    # Fake LLM client injected at module level
    class _FakeLLM:
        async def generate_json(self, messages, system_prompt=None):
            from Adventorator.schemas import LLMOutput, LLMProposal

            return LLMOutput(
                proposal=LLMProposal(
                    action="ability_check",
                    ability="DEX",
                    suggested_dc=12,
                    reason="nimble",
                ),
                narration="You slip by.",
            )

    monkeypatch.setattr(appmod, "llm_client", _FakeLLM())

    _stub_repos(monkeypatch)

    body = {
        "type": 2,
        "id": "123",
        "token": "tok",
        "application_id": "app",
        "guild": {"id": "1"},
        "channel": {"id": "1"},
        "member": {"user": {"id": "2", "username": "u"}},
        "data": {
            "name": "do",
            "options": [{"name": "message", "type": 3, "value": "I sneak past."}],
        },
    }

    r = client.post(
        "/interactions",
        content=json.dumps(body).encode(),
        headers={"X-Signature-Ed25519": "00", "X-Signature-Timestamp": "0"},
    )

    # First response is the deferred ack
    assert r.status_code == 200
    assert r.json() == {"type": 5}


def test_do_visible_post(monkeypatch):
    monkeypatch.setattr(appmod, "verify_ed25519", lambda *a, **k: True)
    monkeypatch.setattr(appmod, "session_scope", lambda: _DummyAsyncCM())
    # The command handler imports session_scope directly from Adventorator.db,
    # so patch the symbol in the handler module as well.
    import Adventorator.commands.do as do_mod

    monkeypatch.setattr(do_mod, "session_scope", lambda: _DummyAsyncCM())
    monkeypatch.setattr(
        appmod,
        "settings",
        SimpleNamespace(
            features_llm=True,
            features_llm_visible=True,
            llm_max_prompt_tokens=256,
            discord_public_key="",
            env="test",
            discord_dev_public_key="",
        ),
    )

    class _FakeLLM:
        async def generate_json(self, messages, system_prompt=None):
            from Adventorator.schemas import LLMOutput, LLMProposal

            return LLMOutput(
                proposal=LLMProposal(
                    action="ability_check",
                    ability="STR",
                    suggested_dc=10,
                    reason="simple",
                ),
                narration="You push through.",
            )

    monkeypatch.setattr(appmod, "llm_client", _FakeLLM())

    _stub_repos(monkeypatch)

    body = {
        "type": 2,
        "id": "123",
        "token": "tok",
        "application_id": "app",
        "guild": {"id": "1"},
        "channel": {"id": "1"},
        "member": {"user": {"id": "2", "username": "u"}},
        "data": {
            "name": "do",
            "options": [{"name": "message", "type": 3, "value": "I force the door."}],
        },
    }

    captured = {}

    async def _spy_followup(app_id, token, content, ephemeral=False):  # noqa: ANN001
        captured["content"] = content
        return None

    # Patch the symbol used in app module (followup imported as symbol)
    monkeypatch.setattr(appmod, "followup_message", _spy_followup)

    r = client.post(
        "/interactions",
        content=json.dumps(body).encode(),
        headers={"X-Signature-Ed25519": "00", "X-Signature-Timestamp": "0"},
    )

    assert r.status_code == 200
    assert r.json() == {"type": 5}
    # After deferred ack, background task should call followup with mechanics+ narration
    # Give the background task a short window to post follow-up
    import time as _t

    for _ in range(50):  # up to ~0.5s
        if captured.get("content"):
            break
        _t.sleep(0.01)
    assert "Mechanics" in captured.get("content", "")
    assert "Narration" in captured.get("content", "")
