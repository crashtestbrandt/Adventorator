# tests/test_llm_client_json.py

import pytest

from Adventorator.config import Settings
from Adventorator.llm import LLMClient


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FakeAsyncClient:
    def __init__(self, payload):
        self._payload = payload

    async def post(self, url, content=None, headers=None):
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_generate_json_happy(monkeypatch):
    settings = Settings(
        llm_api_url="http://x",
        llm_model_name="m",
        llm_default_system_prompt="s",
        discord_public_key="x",
    )
    c = LLMClient(settings)
    # Patch the internal client
    monkeypatch.setattr(
        c,
        "_client",
        _FakeAsyncClient(
            {
                "message": {
                        "content": (
                            '{"proposal":{"action":"ability_check","ability":"DEX",'
                            '"suggested_dc":10,"reason":"ok"},"narration":"hi"}'
                        )
                }
            }
        ),
    )
    out = await c.generate_json([{"role": "user", "content": "hi"}])
    assert out is not None
    assert out.proposal.ability == "DEX"


@pytest.mark.asyncio
async def test_generate_json_invalid_returns_none(monkeypatch):
    settings = Settings(
        llm_api_url="http://x",
        llm_model_name="m",
        llm_default_system_prompt="s",
        discord_public_key="x",
    )
    c = LLMClient(settings)
    monkeypatch.setattr(c, "_client", _FakeAsyncClient({"message": {"content": "not json"}}))
    out = await c.generate_json([{"role": "user", "content": "hi"}])
    assert out is None
