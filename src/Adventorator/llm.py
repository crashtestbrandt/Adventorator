# src/Adventorator/llm.py

import httpx
import orjson
import structlog
from Adventorator.config import Settings
from typing import List, Dict, Optional

log = structlog.get_logger()

class LLMClient:
    def __init__(self, settings: Settings):
        self.api_url = settings.llm_api_url
        self.model_name = settings.llm_model_name
        self.system_prompt = settings.llm_default_system_prompt
        self.headers = {"Content-Type": "application/json"}
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
            "temperature": 0.4,
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

    async def close(self):
        """Gracefully close the HTTP client."""
        await self._client.aclose()