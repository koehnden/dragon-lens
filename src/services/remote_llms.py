import logging
from typing import Optional

from sqlalchemy.orm import Session

from config import settings
from models.domain import LLMProvider
from services.base_llm import BaseLLMService

logger = logging.getLogger(__name__)


class DeepSeekService(BaseLLMService):
    provider = LLMProvider.DEEPSEEK
    default_model = "deepseek-chat"

    def __init__(self, db: Optional[Session] = None, api_key: Optional[str] = None):
        super().__init__(db, api_key)
        self.api_base = settings.deepseek_api_base

    def _build_payload(self, messages: list[dict], model_name: str) -> dict:
        return {
            "model": model_name,
            "messages": messages,
            "temperature": 0.7,
        }


class KimiService(BaseLLMService):
    provider = LLMProvider.KIMI
    default_model = "moonshot-v1-8k"

    def __init__(self, db: Optional[Session] = None, api_key: Optional[str] = None):
        super().__init__(db, api_key)
        self.api_base = settings.kimi_api_base

    def _build_messages(self, prompt_zh: str) -> list[dict]:
        return [
            {"role": "system", "content": "你是一个中文助手，请用中文回答所有问题。"},
            {"role": "user", "content": prompt_zh},
        ]

    def _build_payload(self, messages: list[dict], model_name: str) -> dict:
        return {
            "model": model_name,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000,
        }


class LLMRouter:
    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self._services: dict[LLMProvider, BaseLLMService] = {}

    def _get_service(self, provider: LLMProvider) -> BaseLLMService:
        if provider not in self._services:
            self._services[provider] = self._create_service(provider)
        return self._services[provider]

    def _create_service(self, provider: LLMProvider) -> BaseLLMService:
        if provider == LLMProvider.DEEPSEEK:
            return DeepSeekService(self.db)
        if provider == LLMProvider.KIMI:
            return KimiService(self.db)
        raise ValueError(f"No remote service for provider: {provider}")

    async def query(
        self,
        provider: str,
        model_name: str,
        prompt_zh: str,
        enable_web_search: bool = False,
    ) -> tuple[str, int, int, float]:
        provider_enum = LLMProvider(provider.lower())
        model = model_name.lower()

        if provider_enum == LLMProvider.QWEN:
            from services.ollama import OllamaService
            ollama = OllamaService()
            return await ollama.query_main_model(prompt_zh, model)

        service = self._get_service(provider_enum)
        return await service.query(prompt_zh, model)
