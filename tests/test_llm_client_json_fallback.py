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
async def test_generate_json_fills_missing_narration_from_reason(monkeypatch):
    # Given a valid proposal but missing narration, client fills narration from reason
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
                        "ability": "WIS",
                        "suggested_dc": 12,
                        "reason": "stay focused",
                    }
                }
            }
        }
        return _Resp(payload)

    monkeypatch.setattr(client._client, "post", _post)

    out = await client.generate_json([{"role": "user", "content": "do thing"}])
    assert out is not None
    assert out.proposal.ability == "WIS"
    # Fallback uses proposal.reason as narration when narration is omitted
    assert out.narration == "stay focused"

    await client.close()
