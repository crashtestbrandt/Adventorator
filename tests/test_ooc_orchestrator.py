# tests/test_ooc_orchestrator.py

import json
from fastapi.testclient import TestClient
import Adventorator.app as appmod
from Adventorator.app import app
from types import SimpleNamespace
import pytest

client = TestClient(app)

class _DummyAsyncCM:
    async def __aenter__(self):
        return SimpleNamespace()
    async def __aexit__(self, exc_type, exc, tb):
        return False

class FakeLLM:
    def __init__(self, out):
        self._out = out
    async def generate_json(self, messages, system_prompt=None):
        return self._out

@pytest.mark.asyncio
async def test_ooc_shadow_mode_ephemeral(monkeypatch):
    # enable LLM but invisible
    monkeypatch.setattr(appmod, "verify_ed25519", lambda *a, **k: True)
    monkeypatch.setattr(appmod, "session_scope", lambda: _DummyAsyncCM())
    # repos stubs
    async def _camp(*a, **k): return SimpleNamespace(id=1)
    async def _scene(*a, **k): return SimpleNamespace(id=1)
    async def _write(*a, **k): return None
    import Adventorator.repos as reposmod
    monkeypatch.setattr(reposmod, "get_or_create_campaign", _camp)
    monkeypatch.setattr(reposmod, "ensure_scene", _scene)
    monkeypatch.setattr(reposmod, "write_transcript", _write)

    # Configure settings flags
    appmod.settings.features_llm = True
    appmod.settings.features_llm_visible = False

    # Fake LLM client + output
    from Adventorator.schemas import LLMOutput, LLMProposal
    fake_out = LLMOutput(proposal=LLMProposal(action="ability_check", ability="DEX", suggested_dc=12, reason="""safe"""), narration="narr")
    appmod.llm_client = FakeLLM(fake_out)

    body = {"type": 2, "id": "1", "token": "t", "application_id": "a", "data": {"name": "ooc", "options": [{"name": "message", "type": 3, "value": "hi"}]}}
    r = client.post("/interactions", content=json.dumps(body).encode(), headers={"X-Signature-Ed25519": "00", "X-Signature-Timestamp": "0"})
    assert r.status_code == 200
    # Deferred response; follow-up happens out-of-band. We can't capture follow-up here, but reaching here means no crash.

@pytest.mark.asyncio
async def test_ooc_visible_path(monkeypatch):
    monkeypatch.setattr(appmod, "verify_ed25519", lambda *a, **k: True)
    monkeypatch.setattr(appmod, "session_scope", lambda: _DummyAsyncCM())
    async def _camp(*a, **k): return SimpleNamespace(id=1)
    async def _scene(*a, **k): return SimpleNamespace(id=1)
    async def _write(*a, **k): return None
    import Adventorator.repos as reposmod
    monkeypatch.setattr(reposmod, "get_or_create_campaign", _camp)
    monkeypatch.setattr(reposmod, "ensure_scene", _scene)
    monkeypatch.setattr(reposmod, "write_transcript", _write)

    appmod.settings.features_llm = True
    appmod.settings.features_llm_visible = True

    from Adventorator.schemas import LLMOutput, LLMProposal
    fake_out = LLMOutput(proposal=LLMProposal(action="ability_check", ability="STR", suggested_dc=10, reason="ok"), narration="text")
    appmod.llm_client = FakeLLM(fake_out)

    body = {"type": 2, "id": "1", "token": "t", "application_id": "a", "data": {"name": "ooc", "options": [{"name": "message", "type": 3, "value": "go"}]}}
    r = client.post("/interactions", content=json.dumps(body).encode(), headers={"X-Signature-Ed25519": "00", "X-Signature-Timestamp": "0"})
    assert r.status_code == 200

@pytest.mark.asyncio
async def test_ooc_degraded_ephemeral(monkeypatch):
    monkeypatch.setattr(appmod, "verify_ed25519", lambda *a, **k: True)
    monkeypatch.setattr(appmod, "session_scope", lambda: _DummyAsyncCM())
    async def _camp(*a, **k): return SimpleNamespace(id=1)
    async def _scene(*a, **k): return SimpleNamespace(id=1)
    async def _write(*a, **k): return None
    import Adventorator.repos as reposmod
    monkeypatch.setattr(reposmod, "get_or_create_campaign", _camp)
    monkeypatch.setattr(reposmod, "ensure_scene", _scene)
    monkeypatch.setattr(reposmod, "write_transcript", _write)

    appmod.settings.features_llm = True
    appmod.settings.features_llm_visible = False
    appmod.llm_client = FakeLLM(None)

    body = {"type": 2, "id": "1", "token": "t", "application_id": "a", "data": {"name": "ooc", "options": [{"name": "message", "type": 3, "value": "uh"}]}}
    r = client.post("/interactions", content=json.dumps(body).encode(), headers={"X-Signature-Ed25519": "00", "X-Signature-Timestamp": "0"})
    assert r.status_code == 200
