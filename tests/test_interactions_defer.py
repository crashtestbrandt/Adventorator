# tests/test_interactions_defer.py
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

import Adventorator.app as appmod
from Adventorator.app import app

client = TestClient(app)


def test_slash_command_defers(monkeypatch):
    monkeypatch.setattr(appmod, "verify_ed25519", lambda *a, **k: True)

    # 1) Fake async context manager for session_scope()
    class _DummyAsyncCM:
        async def __aenter__(self):
            # A minimal "session" object (unused by our test after stubbing repos)
            return SimpleNamespace()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(appmod, "session_scope", lambda: _DummyAsyncCM())

    # 2) Stub the repo functions used in interactions() before deferring
    async def _noop_campaign(*args, **kwargs):
        return SimpleNamespace(id=1)

    async def _noop_scene(*args, **kwargs):
        return SimpleNamespace(id=1)

    async def _noop_transcript(*args, **kwargs):
        return None

    import Adventorator.repos as reposmod

    monkeypatch.setattr(reposmod, "get_or_create_campaign", _noop_campaign)
    monkeypatch.setattr(reposmod, "ensure_scene", _noop_scene)
    monkeypatch.setattr(reposmod, "write_transcript", _noop_transcript)

    body = {
        "type": 2,
        "id": "123",
        "token": "tok",
        "application_id": "app",
        "data": {"name": "roll", "options": [{"name": "expr", "type": 3, "value": "1d20"}]},
    }
    r = client.post(
        "/interactions",
        content=json.dumps(body).encode(),
        headers={"X-Signature-Ed25519": "00", "X-Signature-Timestamp": "0"},
    )
    assert r.status_code == 200
    assert r.json() == {"type": 5}  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
