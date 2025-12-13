import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class DeepSeekService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.deepseek_api_key
        self.api_base = settings.deepseek_api_base

    async def query(self, prompt_zh: str) -> tuple[str, int, int]:
        if not self.api_key:
            raise ValueError("DeepSeek API key is not configured")

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": prompt_zh}
            ],
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()

                answer = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {})
                tokens_in = usage.get("prompt_tokens", 0)
                tokens_out = usage.get("completion_tokens", 0)

                return answer, tokens_in, tokens_out

            except httpx.HTTPError as e:
                logger.error(f"DeepSeek API error: {e}")
                raise


class KimiService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.kimi_api_key
        self.api_base = settings.kimi_api_base

    async def query(
        self,
        prompt_zh: str,
        enable_web_search: bool = False,
    ) -> tuple[str, int, int]:
        if not self.api_key:
            raise ValueError("Kimi API key is not configured")

        raise NotImplementedError("Kimi integration not yet implemented")


class LLMRouter:
    def __init__(self):
        from services.ollama import OllamaService

        self.ollama = OllamaService()
        self.deepseek = DeepSeekService()
        self.kimi = KimiService()

    async def query(
        self,
        model_name: str,
        prompt_zh: str,
        enable_web_search: bool = False,
    ) -> tuple[str, int, int]:
        model_name = model_name.lower()

        if model_name == "qwen":
            return await self.ollama.query_main_model(prompt_zh)
        elif model_name == "deepseek":
            return await self.deepseek.query(prompt_zh)
        elif model_name == "kimi":
            return await self.kimi.query(prompt_zh, enable_web_search=enable_web_search)
        else:
            raise ValueError(f"Unsupported model: {model_name}")
