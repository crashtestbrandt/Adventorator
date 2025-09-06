# src/Adventorator/llm.py

import httpx
import orjson
import structlog
from typing import List, Dict, Optional

from Adventorator.config import Settings
from Adventorator.llm_utils import extract_first_json, validate_llm_output
from Adventorator.schemas import LLMOutput

log = structlog.get_logger()

class LLMClient:
    def __init__(self, settings: Settings):
        self.api_url = settings.llm_api_url
        self.model_name = settings.llm_model_name
        self.system_prompt = settings.llm_default_system_prompt
        self.headers = {"Content-Type": "application/json"}
        self._max_chars = getattr(settings, "llm_max_response_chars", 8000) or 8000
        # We use a persistent client for connection pooling
        self._client = httpx.AsyncClient(timeout=60.0)
        log.info("LLMClient initialized", model=self.model_name, url=self.api_url)

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> Optional[str]:
        """
        Generates a response from the LLM based on a list of messages.
        """
        if not self.api_url or not self.model_name:
            log.warning("LLM service is not configured (api_url or model_name missing).")
            return None

        # The first message should always be the system prompt
        full_prompt = [{"role": "system", "content": system_prompt or self.system_prompt}]
        full_prompt.extend(messages)

        # Ollama API payload structure
        data = {
            "model": self.model_name,
            "messages": full_prompt,
            "stream": False,  # For MVP, we'll wait for the full response
            "temperature": 0.6,
        }

        try:
            response = await self._client.post(self.api_url, content=orjson.dumps(data), headers=self.headers, timeout=60.0)
            response.raise_for_status()
            
            result = response.json()
            content = result.get("message", {}).get("content")

            if not content:
                log.error("LLM API response missing 'content'", response_body=result)
                return "The narrator seems lost for words..."
                
            return content.strip()

        except httpx.RequestError as e:
            log.error("LLM API request failed", url=e.request.url, error=str(e))
            return "The connection to the ethereal plane was lost. (LLM request failed)"
        except Exception as e:
            log.error("Failed to process LLM response", error=str(e))
            return "A strange psychic interference prevents a clear response. (LLM response error)"

    async def generate_json(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> Optional[LLMOutput]:
        """Call the chat API and return validated LLMOutput or None.

        Expects messages to already include any system prompt if desired. Enforces
        a response character cap and validates the first JSON object in content.
        """
        if not self.api_url or not self.model_name:
            log.warning("LLM service is not configured (api_url or model_name missing).")
            return None

        data = {
            "model": self.model_name,
            "messages": messages if messages else ([{"role": "system", "content": system_prompt or self.system_prompt}]),
            "stream": False,
            "temperature": 0.2,
        }

        try:
            response = await self._client.post(self.api_url, content=orjson.dumps(data), headers=self.headers)
            response.raise_for_status()
            result = response.json()
            content = (result.get("message", {}) or {}).get("content")
            if not content:
                log.error("LLM API response missing 'content'", response_body=result)
                return None

            # Enforce cap
            if len(content) > self._max_chars:
                content = content[: self._max_chars]

            parsed = extract_first_json(content, max_chars=self._max_chars)
            out = validate_llm_output(parsed)
            if not out:
                log.warning("LLM JSON validation failed", raw_preview=content[:200])
            return out
        except httpx.RequestError as e:
            log.error("LLM API request failed", url=str(e.request.url) if getattr(e, "request", None) else None, error=str(e))
            return None
        except Exception as e:
            log.error("Failed to process LLM JSON response", error=str(e))
            return None

    async def close(self):
        """Gracefully close the HTTP client."""
        await self._client.aclose()