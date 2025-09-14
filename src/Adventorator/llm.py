# src/Adventorator/llm.py

from typing import Any, cast

import httpx
import orjson
import structlog

# Import the official OpenAI library and its specific error types
from openai import APIError as OpenAIError
from openai import AsyncOpenAI

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
            raise ValueError(
                "LLMClient requires llm_api_url to be set in configuration."
            )
        # The client instance will be one of two types (set below based on provider).
        # Use Any here to keep mypy happy across provider branches.
        self._client: Any

        if self.provider == "ollama":
            base = (settings.llm_api_url or "").rstrip("/")
            # Accept either base (http://host:11434) or explicit chat endpoint (/api/chat)
            if base.endswith("/api/chat"):
                self.api_url = base
            elif base.endswith("/api"):
                self.api_url = f"{base}/chat"
            else:
                self.api_url = f"{base}/api/chat"
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
            url=self.api_url,
        )

    async def generate_response(
        self, messages: list[dict], system_prompt: str | None = None
    ) -> str | None:
        """Generates a text response from the LLM based on a list of messages."""
        full_prompt = [{"role": "system", "content": system_prompt or self.system_prompt}]
        full_prompt.extend(messages)
        prompt_chars = sum(len(str(m.get("content", ""))) for m in full_prompt)

        log.info(
            "llm.call.initiated",
            provider=self.provider,
            model=self.model_name,
            prompt_approx_chars=prompt_chars,
        )
        import time
        start = time.perf_counter()
        status = "success"
        try:
            if isinstance(self._client, httpx.AsyncClient):  # Ollama provider
                data = {"model": self.model_name, "messages": full_prompt, "stream": False}
                httpx_resp = await self._client.post(self.api_url, content=orjson.dumps(data))
                httpx_resp.raise_for_status()
                result = httpx_resp.json()
                content = result.get("message", {}).get("content")

            else:  # OpenAI provider
                oa_resp = await self._client.chat.completions.create(
                    model=self.model_name,
                    messages=cast(Any, full_prompt),
                )
                content = oa_resp.choices[0].message.content

            if not content:
                status = "empty_content"
                log.error("LLM API response missing 'content'")
                return "The narrator seems lost for words..."

            return content.strip()

        except OpenAIError as e:
            status = "api_error"
            log.error("OpenAI API error", error=str(e), status_code=getattr(e, 'status_code', None))
            return "A strange psychic interference prevents a clear response. (LLM API error)"
        except httpx.RequestError as e:
            status = "request_error"
            log.error("Ollama API request failed", url=e.request.url, error=str(e))
            return "The connection to the ethereal plane was lost. (LLM request failed)"
        except Exception as e:
            status = "processing_error"
            log.error("Failed to process LLM response", error=str(e), provider=self.provider)
            return "A strange psychic interference prevents a clear response. (LLM response error)"
        finally:
            import math
            dur_ms = math.trunc((time.perf_counter() - start) * 1000)
            log.info(
                "llm.call.completed",
                provider=self.provider,
                model=self.model_name,
                duration_ms=dur_ms,
                status=status,
            )

    async def generate_json(
        self,
        messages: list[dict],
        system_prompt: str | None = None,  # Note: system_prompt is now part of messages
    ) -> LLMOutput | None:
        """Call the chat API and return validated LLMOutput or None."""
        full_prompt = [{"role": "system", "content": system_prompt or self.system_prompt}]
        full_prompt.extend(messages)

        import time
        start = time.perf_counter()
        status = "success"
        try:
            parsed_json = None
            raw_content = ""

            if isinstance(self._client, httpx.AsyncClient):  # Ollama provider
                data = {
                    "model": self.model_name,
                    "messages": full_prompt,
                    "stream": False,
                    "format": "json",
                }
                httpx_resp = await self._client.post(self.api_url, content=orjson.dumps(data))
                httpx_resp.raise_for_status()
                result = httpx_resp.json()
                raw_content = result.get("message", {}).get("content")
                if raw_content is not None:
                    # Ollama may return the content as a dict when format=json is used
                    if isinstance(raw_content, dict | list):
                        parsed_json = raw_content
                    elif isinstance(raw_content, str):
                        # Try strict load first; fall back to best-effort extractor
                        try:
                            parsed_json = orjson.loads(raw_content)
                        except Exception:
                            parsed_json = extract_first_json(raw_content, max_chars=self._max_chars)

                # Fallback: some models misbehave with format=json and return empty objects.
                # Retry once without format hint and try to extract JSON from the text.
                if not parsed_json:
                    data_fallback = {
                        "model": self.model_name,
                        "messages": full_prompt,
                        "stream": False,
                    }
                    try:
                        resp_fb = await self._client.post(
                            self.api_url,
                            content=orjson.dumps(data_fallback),
                        )
                        resp_fb.raise_for_status()
                        res_fb = resp_fb.json()
                        fb_content = res_fb.get("message", {}).get("content")
                        if isinstance(fb_content, dict | list):
                            parsed_json = fb_content
                        elif isinstance(fb_content, str):
                            try:
                                parsed_json = orjson.loads(fb_content)
                            except Exception:
                                parsed_json = extract_first_json(
                                    fb_content,
                                    max_chars=self._max_chars,
                                )
                    except Exception:
                        # Ignore fallback errors; we'll handle as invalid below
                        pass

            else:  # OpenAI provider
                oa_resp = await self._client.chat.completions.create(
                    model=self.model_name,
                    messages=cast(Any, full_prompt),
                )
                # Use attribute access per OpenAI SDK; dict-like access may fail
                raw_content = oa_resp.choices[0].message.content
                if raw_content:
                    if isinstance(raw_content, dict | list):
                        parsed_json = raw_content
                    elif isinstance(raw_content, str):
                        parsed_json = orjson.loads(raw_content)

            if not parsed_json:
                status = "validation_failed"
                log.warning(
                    "LLM did not return valid JSON content",
                    raw_preview=str(raw_content)[:200],
                )
                return None

            # Gentle fallback: some models omit 'narration' but include a proposal.
            if (
                isinstance(parsed_json, dict)
                and "proposal" in parsed_json
                and "narration" not in parsed_json
            ):
                try:
                    reason = ""
                    prop = parsed_json.get("proposal")
                    if isinstance(prop, dict):
                        reason = str(prop.get("reason") or "").strip()
                    parsed_json["narration"] = reason or ""
                except Exception:
                    # If anything goes wrong, proceed to normal validation which may fail
                    pass

            # Validate the parsed dictionary against our Pydantic schema
            out = validate_llm_output(
                cast(
                    dict[str, Any] | None,
                    parsed_json if isinstance(parsed_json, dict) else None,
                )
            )
            if not out:
                status = "validation_failed"
                log.warning("LLM JSON validation failed", raw_preview=str(raw_content)[:200])
            return out

        except OpenAIError as e:
            status = "api_error"
            log.error(
                "OpenAI API JSON error",
                error=str(e),
                status_code=getattr(e, "status_code", None),
            )
            return None
        except httpx.RequestError as e:
            status = "request_error"
            log.error("Ollama API JSON request failed", url=e.request.url, error=str(e))
            return None
        except Exception as e:
            status = "processing_error"
            log.error("Failed to process LLM JSON response", error=str(e), provider=self.provider)
            return None
        finally:
            import math
            dur_ms = math.trunc((time.perf_counter() - start) * 1000)
            log.info(
                "llm.call.completed",
                provider=self.provider,
                model=self.model_name,
                duration_ms=dur_ms,
                status=status,
            )

    async def close(self):
        """Gracefully close the underlying HTTP client."""
        if not getattr(self, "_client", None):
            return
        try:
            # httpx.AsyncClient has aclose; OpenAI AsyncOpenAI has async close method too
            if isinstance(self._client, httpx.AsyncClient):
                await self._client.aclose()
            else:
                close = getattr(self._client, "close", None)
                if close is not None:
                    res = close()
                    # Some clients return coroutine for close
                    if hasattr(res, "__await__"):
                        await res  # type: ignore[misc]
        finally:
            log.info("LLMClient closed.")
