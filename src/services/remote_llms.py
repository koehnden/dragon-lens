import logging
from typing import Optional

from sqlalchemy.orm import Session

from config import settings
from models.domain import LLMProvider
from services.base_llm import BaseLLMService, OpenAICompatibleService

logger = logging.getLogger(__name__)


class DeepSeekService(OpenAICompatibleService):
    provider = LLMProvider.DEEPSEEK
    default_model = "deepseek-chat"
    temperature = 0.7
    SUPPORTED_MODELS = ["deepseek-chat", "deepseek-reasoner"]

    def __init__(self, db: Optional[Session] = None, api_key: Optional[str] = None):
        super().__init__(db, api_key)
        self.api_base = settings.deepseek_api_base

    def validate_model(self, model: str) -> None:
        if model not in self.SUPPORTED_MODELS:
            raise ValueError(f"Unsupported DeepSeek model: {model}")


class KimiService(OpenAICompatibleService):
    provider = LLMProvider.KIMI
    default_model = "moonshot-v1-8k"
    temperature = 0.7
    max_tokens = 2000
    system_prompt = "你是一个中文助手，请用中文回答所有问题。"

    def __init__(self, db: Optional[Session] = None, api_key: Optional[str] = None):
        super().__init__(db, api_key)
        self.api_base = settings.kimi_api_base


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
