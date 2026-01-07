import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from config import settings
from models.domain import LLMProvider, LLMRoute
from services.base_llm import BaseLLMService, OpenAICompatibleService

logger = logging.getLogger(__name__)

_OPENROUTER_MODEL_ALIASES = {
    "MiniMaxAI/MiniMax-M2.1": "minimax/minimax-m2.1",
}


def _normalize_openrouter_model(model_name: str) -> str:
    return _OPENROUTER_MODEL_ALIASES.get(model_name, model_name)


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
    temperature = 0.6
    max_tokens = 2000
    system_prompt = "你是一个中文助手，请用中文回答所有问题。"

    def __init__(self, db: Optional[Session] = None, api_key: Optional[str] = None):
        super().__init__(db, api_key)
        self.api_base = settings.kimi_api_base

    def _is_k2_model(self, model_name: str) -> bool:
        return any(k2 in model_name.lower() for k2 in ["kimi-k2", "k2-"])

    async def query(
        self,
        prompt_zh: str,
        model_name: Optional[str] = None,
        **kwargs,
    ) -> tuple[str, int, int, float]:
        import httpx
        import time
        from openai import AsyncOpenAI

        api_key = self._get_api_key()
        model = model_name or self.default_model
        is_k2 = self._is_k2_model(model)

        http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.api_base,
            http_client=http_client,
        )

        messages = self._build_messages(prompt_zh)
        request_kwargs = {"model": model, "messages": messages, "temperature": self.temperature}

        if not is_k2 and self.max_tokens is not None:
            request_kwargs["max_tokens"] = self.max_tokens

        logger.info(f"Kimi request: model={model}, is_k2={is_k2}, max_tokens={'none' if is_k2 else self.max_tokens}")

        start_time = time.time()
        try:
            response = await client.chat.completions.create(**request_kwargs)
            latency = time.time() - start_time
            return self._parse_openai_response(response, latency)
        except Exception as e:
            logger.error(f"{self.provider.value} API error: {e}")
            raise
        finally:
            await http_client.aclose()


class OpenRouterService(OpenAICompatibleService):
    provider = LLMProvider.OPENROUTER
    default_model = "openrouter/auto"
    temperature = 0.7

    def __init__(self, db: Optional[Session] = None, api_key: Optional[str] = None):
        super().__init__(db, api_key)
        self.api_base = settings.openrouter_api_base


@dataclass(frozen=True)
class LLMResolution:
    service: Optional[BaseLLMService]
    model_name: str
    route: LLMRoute


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
        if provider == LLMProvider.OPENROUTER:
            return OpenRouterService(self.db)
        raise ValueError(f"No remote service for provider: {provider}")

    def resolve(self, provider: str, model_name: str) -> LLMResolution:
        provider_enum = LLMProvider(provider.lower())
        if provider_enum == LLMProvider.QWEN:
            return LLMResolution(None, model_name, LLMRoute.LOCAL)
        if provider_enum == LLMProvider.OPENROUTER:
            return self._resolve_openrouter(model_name)
        return self._resolve_vendor(provider_enum, model_name)

    def _resolve_vendor(self, provider: LLMProvider, model_name: str) -> LLMResolution:
        vendor_service = self._get_service(provider)
        if vendor_service.has_api_key():
            return LLMResolution(vendor_service, model_name, LLMRoute.VENDOR)
        return self._resolve_openrouter(model_name)

    def _resolve_openrouter(self, model_name: str) -> LLMResolution:
        service = self._get_service(LLMProvider.OPENROUTER)
        if not service.has_api_key():
            raise ValueError("No active openrouter API key found")
        return LLMResolution(service, _normalize_openrouter_model(model_name), LLMRoute.OPENROUTER)

    async def _query_local(self, prompt_zh: str, model_name: str) -> tuple[str, int, int, float]:
        from services.ollama import OllamaService
        ollama = OllamaService()
        return await ollama.query_main_model(prompt_zh, model_name)

    async def query_with_resolution(
        self,
        resolution: LLMResolution,
        prompt_zh: str,
    ) -> tuple[str, int, int, float]:
        if resolution.route == LLMRoute.LOCAL:
            return await self._query_local(prompt_zh, resolution.model_name)
        if not resolution.service:
            raise ValueError("No service available for route")
        return await resolution.service.query(prompt_zh, resolution.model_name)

    async def query(
        self,
        provider: str,
        model_name: str,
        prompt_zh: str,
        enable_web_search: bool = False,
    ) -> tuple[str, int, int, float, LLMRoute]:
        resolution = self.resolve(provider, model_name)
        answer = await self.query_with_resolution(resolution, prompt_zh)
        return *answer, resolution.route
