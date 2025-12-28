import logging
import time
from typing import Optional

from sqlalchemy.orm import Session

from src.services.base_llm import BaseLLMService
from src.models.domain import LLMProvider


logger = logging.getLogger(__name__)


class OpenAIClientService(BaseLLMService):
    """LLM service using the official OpenAI client for OpenAI-compatible APIs."""

    async def query(
        self,
        prompt_zh: str,
        model_name: Optional[str] = None,
        **kwargs,
    ) -> tuple[str, int, int, float]:
        """Query the LLM using OpenAI client."""
        from openai import AsyncOpenAI

        api_key = self._get_api_key()
        model = model_name or self.default_model

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.api_base,
        )

        messages = self._build_messages(prompt_zh)

        start_time = time.time()
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                **kwargs,
            )
            latency = time.time() - start_time

            answer = response.choices[0].message.content or ""
            usage = response.usage

            tokens_in = usage.prompt_tokens if usage else 0
            tokens_out = usage.completion_tokens if usage else 0

            return answer, tokens_in, tokens_out, latency

        except Exception as e:
            logger.error(f"{self.provider.value} OpenAI client error: {e}")
            raise

    def _build_payload(self, messages: list[dict], model_name: str) -> dict:
        """Dummy implementation for abstract method (not used with OpenAI client)."""
        return {}


class OpenAIChatCompletionsService(BaseLLMService):
    """Legacy service using HTTP requests for chat completions (for non-OpenAI compatible APIs)."""

    async def query(
        self,
        prompt_zh: str,
        model_name: Optional[str] = None,
        **kwargs,
    ) -> tuple[str, int, int, float]:
        """Query the LLM using HTTP requests (legacy method)."""
        import httpx

        api_key = self._get_api_key()
        model = model_name or self.default_model
        url = f"{self.api_base}/chat/completions"

        messages = self._build_messages(prompt_zh)
        payload = self._build_payload(messages, model)
        headers = self._build_headers(api_key)

        start_time = time.time()
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                latency = time.time() - start_time
                return self._parse_response(result, latency)
            except httpx.HTTPError as e:
                logger.error(f"{self.provider.value} API error: {e}")
                raise
