import pytest
from pydantic import SecretStr

from Adventorator.config import Settings
from Adventorator.llm import LLMClient


@pytest.mark.parametrize(
    "input_url, expected",
    [
        ("https://api.openai.com", "https://api.openai.com/v1"),
        ("https://api.openai.com/v1", "https://api.openai.com/v1"),
        ("https://api.somehost.com/openai/v1", "https://api.somehost.com/openai/v1"),
        ("http://host:11434/api", "http://host:11434/v1"),
        ("http://host:11434/api/chat", "http://host:11434/v1"),
    ],
)
@pytest.mark.asyncio
async def test_openai_base_url_normalization(input_url, expected):
    s = Settings(
        llm_api_provider="openai",
        llm_api_url=input_url,
        llm_model_name="gpt-4o-mini",
        llm_api_key=SecretStr("sk-test"),
    )
    client = LLMClient(s)
    try:
        assert client.api_url == expected
        # The OpenAI SDK will append '/chat/completions' internally; ensure we didn't
        # embed '/api/chat' in the base which would create '/api/chat/v1/chat/completions'.
        assert "/api/chat/v1" not in client.api_url
    finally:
        await client.close()
