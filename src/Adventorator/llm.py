# src/Adventorator/llm.py

import httpx
import orjson
import structlog
from typing import Union

# Import the official OpenAI library and its specific error types
from openai import AsyncOpenAI, APIError as OpenAIError

from Adventorator.config import Settings
from Adventorator.llm_utils import extract_first_json, validate_llm_output
from Adventorator.schemas import LLMOutput

log = structlog.get_logger()


class LLMClient:
    """
    An asynchronous client for interacting with LLM APIs.
    
    This client supports two providers, configured via settings:
    1. 'openai': Uses the official `openai` library to connect to any
                 OpenAI-compatible API endpoint (e.g., OpenAI, Together.ai, Groq).
                 Handles authentication and typed errors.
    2. 'ollama': Uses a direct `httpx` client to connect to a local or remote
                 Ollama instance.
    """
    def __init__(self, settings: Settings):
        self.provider = settings.llm_api_provider
        self.model_name = settings.llm_model_name
        self.system_prompt = settings.llm_default_system_prompt
        self._max_chars = settings.llm_max_response_chars

        if not settings.llm_api_url:
            raise ValueError("LLMClient requires llm_api_url to be set in configuration.")
        
        # The client instance will be one of two types.
        self._client: Union[AsyncOpenAI, httpx.AsyncClient]

        if self.provider == "ollama":
            self.api_url = f"{settings.llm_api_url.rstrip('/')}/api/chat"
            headers = {"Content-Type": "application/json"}
            self._client = httpx.AsyncClient(timeout=60.0, headers=headers)
        
        elif self.provider == "openai":
            # Ensure the API URL is valid for OpenAI
            self.api_url = settings.llm_api_url or "https://api.openai.com/v1"
            if not self.api_url.endswith("/v1"):
                self.api_url = f"{self.api_url.rstrip('/')}/v1"

            api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None

            self._client = AsyncOpenAI(
                base_url=self.api_url,
                api_key=api_key,
                max_retries=2,
                timeout=60.0,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        log.info(
            "LLMClient initialized",
            provider=self.provider,
            model=self.model_name,
            url=self.api_url
        )

    async def generate_response(
        self, messages: list[dict], system_prompt: str | None = None
    ) -> str | None:
        """Generates a text response from the LLM based on a list of messages."""
        full_prompt = [{"role": "system", "content": system_prompt or self.system_prompt}]
        full_prompt.extend(messages)

        try:
            if isinstance(self._client, httpx.AsyncClient):  # Ollama provider
                data = {"model": self.model_name, "messages": full_prompt, "stream": False}
                response = await self._client.post(self.api_url, content=orjson.dumps(data))
                response.raise_for_status()
                result = response.json()
                content = result.get("message", {}).get("content")

            else:  # OpenAI provider
                response = await self._client.chat.completions.create(
                    model=self.model_name,
                    messages=full_prompt,
                )
                content = response.choices[0].message.content

            if not content:
                log.error("LLM API response missing 'content'")
                return "The narrator seems lost for words..."

            return content.strip()

        except OpenAIError as e:
            log.error("OpenAI API error", error=str(e), status_code=getattr(e, 'status_code', None))
            return "A strange psychic interference prevents a clear response. (LLM API error)"
        except httpx.RequestError as e:
            log.error("Ollama API request failed", url=e.request.url, error=str(e))
            return "The connection to the ethereal plane was lost. (LLM request failed)"
        except Exception as e:
            log.error("Failed to process LLM response", error=str(e), provider=self.provider)
            return "A strange psychic interference prevents a clear response. (LLM response error)"

    async def generate_json(
        self,
        messages: list[dict],
        system_prompt: str | None = None,  # Note: system_prompt is now part of messages
    ) -> LLMOutput | None:
        """Call the chat API and return validated LLMOutput or None."""
        full_prompt = [{"role": "system", "content": system_prompt or self.system_prompt}]
        full_prompt.extend(messages)

        try:
            parsed_json = None
            raw_content = ""

            if isinstance(self._client, httpx.AsyncClient):  # Ollama provider
                data = {
                    "model": self.model_name, 
                    "messages": full_prompt, 
                    "stream": False, 
                    "format": "json"
                }
                response = await self._client.post(self.api_url, content=orjson.dumps(data))
                response.raise_for_status()
                result = response.json()
                raw_content = result.get("message", {}).get("content")
                if raw_content:
                    parsed_json = extract_first_json(raw_content, max_chars=self._max_chars)

            else:  # OpenAI provider
                response = await self._client.chat.completions.create(
                    model=self.model_name,
                    messages=full_prompt,
                )
                raw_content = response.choices[0].message["content"]
                if raw_content:
                    parsed_json = orjson.loads(raw_content)

            if not parsed_json:
                log.warning("LLM did not return valid JSON content", raw_preview=str(raw_content)[:200])
                return None

            # Validate the parsed dictionary against our Pydantic schema
            out = validate_llm_output(parsed_json)
            if not out:
                log.warning("LLM JSON validation failed", raw_preview=str(raw_content)[:200])
            return out

        except OpenAIError as e:
            log.error("OpenAI API JSON error", error=str(e), status_code=getattr(e, 'status_code', None))
            return None
        except httpx.RequestError as e:
            log.error("Ollama API JSON request failed", url=e.request.url, error=str(e))
            return None
        except Exception as e:
            log.error("Failed to process LLM JSON response", error=str(e), provider=self.provider)
            return None

    async def close(self):
        """Gracefully close the underlying HTTP client."""
        if self._client:
            await self._client.aclose()
            log.info("LLMClient closed.")