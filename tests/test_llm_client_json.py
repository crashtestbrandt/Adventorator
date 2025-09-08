import pytest

from Adventorator.config import Settings
from Adventorator.llm import LLMClient


class _Resp:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise RuntimeError("bad status")

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_generate_json_valid_object(monkeypatch):
    # Given an Ollama-style JSON response with content as dict
    s = Settings(
        llm_api_provider="ollama",
        llm_api_url="http://test/api",
        llm_model_name="test-model",
    )
    client = LLMClient(s)

    async def _post(url, content):  # noqa: ANN001
        payload = {
            "message": {
                "content": {
                    "proposal": {
                        "action": "ability_check",
                        "ability": "DEX",
                        "suggested_dc": 12,
                        "reason": "lock",
                    },
                    "narration": "You deftly pick the lock.",
                }
            }
        }
        return _Resp(payload)

    monkeypatch.setattr(client._client, "post", _post)

    out = await client.generate_json([{"role": "user", "content": "do thing"}])
    assert out is not None
    assert out.proposal.ability == "DEX"
    assert out.narration.startswith("You deftly")

    await client.close()


@pytest.mark.asyncio
async def test_generate_json_extracts_from_prose(monkeypatch):
    # Given the model returns prose with embedded JSON, ensure extractor works
    s = Settings(
        llm_api_provider="ollama",
        llm_api_url="http://test/api",
        llm_model_name="test-model",
    )
    client = LLMClient(s)

    calls = {"n": 0}

    async def _post(url, content):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            # First call (with format=json): return content as a string with extra prose
            payload = {
                "message": {
                    "content": (
                        "Here is the result: {\n"
                        '  "proposal": {"action": "ability_check", "ability": "STR", '
                        '"suggested_dc": 10, "reason": "simple"},\n'
                        '  "narration": "You push through."\n'
                        "} Thanks!"
                    )
                }
            }
            return _Resp(payload)
        else:
            # Second call (fallback w/o format) shouldn't be needed, but return same
            return _Resp({"message": {"content": "{}"}})

    monkeypatch.setattr(client._client, "post", _post)

    out = await client.generate_json([{"role": "user", "content": "do"}])
    assert out is not None
    assert out.proposal.action == "ability_check"
    assert out.proposal.ability == "STR"

    await client.close()


@pytest.mark.asyncio
async def test_generate_json_invalid_returns_none(monkeypatch):
    s = Settings(
        llm_api_provider="ollama",
        llm_api_url="http://test/api",
        llm_model_name="test-model",
    )
    client = LLMClient(s)

    async def _post(url, content):  # noqa: ANN001
        # Content missing JSON object entirely
        return _Resp({"message": {"content": "no json here"}})

    monkeypatch.setattr(client._client, "post", _post)

    out = await client.generate_json([{"role": "user", "content": "hi"}])
    assert out is None

    await client.close()
