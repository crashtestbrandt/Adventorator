import os

import pytest

from Adventorator.config import Settings
from Adventorator.llm import LLMClient


@pytest.mark.asyncio
@pytest.mark.network
async def test_llm_live_chat_when_configured():
    url = os.environ.get("ADVENTORATOR_LIVE_LLM_URL")
    model = os.environ.get("ADVENTORATOR_LIVE_LLM_MODEL", "gpt-4o-mini")
    if not url:
        pytest.skip("ADVENTORATOR_LIVE_LLM_URL not set; skipping live LLM test")

    settings = Settings(
        llm_api_url=url,
        llm_model_name=model,
        llm_default_system_prompt="You are a helpful assistant.",
    )
    client = LLMClient(settings)
    try:
        resp = await client.generate_response(
            [{"role": "user", "content": "Say one short sentence about Jupiter."}]
        )
        assert isinstance(resp, str) and len(resp) > 0
    finally:
        await client.close()
