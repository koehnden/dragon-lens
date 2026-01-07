import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config import settings
from models.domain import LLMProvider, LLMRoute
from services.base_llm import BaseLLMService, OpenAICompatibleService
from services.remote_llms import DeepSeekService, KimiService, LLMRouter, OpenRouterService


class TestOpenAICompatibleService:
    def test_inherits_base_llm_service(self):
        assert issubclass(OpenAICompatibleService, BaseLLMService)

    def test_builds_messages_without_system_prompt(self):
        service = DeepSeekService()
        messages = service._build_messages("测试提示")

        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "测试提示"

    def test_builds_messages_with_system_prompt(self):
        service = KimiService()
        messages = service._build_messages("测试提示")

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "测试提示"

    @pytest.mark.asyncio
    async def test_query_uses_openai_client(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="测试回答"))]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)

        with patch("services.base_llm.AsyncOpenAI") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            service = DeepSeekService(api_key="test-key")
            answer, tokens_in, tokens_out, latency = await service.query("测试")

            assert answer == "测试回答"
            assert tokens_in == 10
            assert tokens_out == 20
            mock_client_class.assert_called_once()
            mock_client.chat.completions.create.assert_called_once()


class TestDeepSeekService:
    def test_has_correct_provider(self):
        assert DeepSeekService.provider == LLMProvider.DEEPSEEK

    def test_has_default_model(self):
        assert DeepSeekService.default_model == "deepseek-chat"

    def test_inherits_openai_compatible_service(self):
        assert issubclass(DeepSeekService, OpenAICompatibleService)

    def test_has_temperature(self):
        assert DeepSeekService.temperature == 0.7


class TestKimiService:
    def test_has_correct_provider(self):
        assert KimiService.provider == LLMProvider.KIMI

    def test_has_default_model(self):
        assert KimiService.default_model == "moonshot-v1-8k"

    def test_inherits_openai_compatible_service(self):
        assert issubclass(KimiService, OpenAICompatibleService)

    def test_has_system_prompt(self):
        assert KimiService.system_prompt is not None
        assert "中文" in KimiService.system_prompt

    def test_has_max_tokens(self):
        assert KimiService.max_tokens == 2000

    def test_builds_messages_with_system_prompt(self):
        service = KimiService()
        messages = service._build_messages("测试提示")

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "测试提示"


class TestOpenRouterService:
    def test_has_correct_provider(self):
        assert OpenRouterService.provider == LLMProvider.OPENROUTER

    def test_inherits_openai_compatible_service(self):
        assert issubclass(OpenRouterService, OpenAICompatibleService)


class TestLLMRouter:
    def test_lazy_service_creation(self):
        router = LLMRouter()
        assert len(router._services) == 0

    def test_creates_deepseek_service(self):
        router = LLMRouter()
        service = router._get_service(LLMProvider.DEEPSEEK)
        assert isinstance(service, DeepSeekService)

    def test_creates_kimi_service(self):
        router = LLMRouter()
        service = router._get_service(LLMProvider.KIMI)
        assert isinstance(service, KimiService)

    def test_creates_openrouter_service(self):
        router = LLMRouter()
        service = router._get_service(LLMProvider.OPENROUTER)
        assert isinstance(service, OpenRouterService)

    def test_caches_services(self):
        router = LLMRouter()
        service1 = router._get_service(LLMProvider.DEEPSEEK)
        service2 = router._get_service(LLMProvider.DEEPSEEK)
        assert service1 is service2

    def test_raises_for_unknown_remote_provider(self):
        router = LLMRouter()
        with pytest.raises(ValueError, match="No remote service"):
            router._create_service(LLMProvider.QWEN)

    def test_resolve_prefers_vendor_key(self, monkeypatch):
        monkeypatch.setattr(settings, "deepseek_api_key", "test-deepseek")
        monkeypatch.setattr(settings, "openrouter_api_key", "test-openrouter")
        router = LLMRouter()
        resolution = router.resolve("deepseek", "deepseek-chat")
        assert resolution.route == LLMRoute.VENDOR
        assert isinstance(resolution.service, DeepSeekService)

    def test_resolve_falls_back_to_openrouter(self, monkeypatch):
        monkeypatch.setattr(settings, "deepseek_api_key", None)
        monkeypatch.setattr(settings, "openrouter_api_key", "test-openrouter")
        router = LLMRouter()
        resolution = router.resolve("deepseek", "deepseek-chat")
        assert resolution.route == LLMRoute.OPENROUTER
        assert isinstance(resolution.service, OpenRouterService)

    def test_resolve_openrouter_preserves_model_name(self, monkeypatch):
        monkeypatch.setattr(settings, "openrouter_api_key", "test-openrouter")
        router = LLMRouter()
        model_name = "baidu/ernie-4.5-300b-a47b"
        resolution = router.resolve("openrouter", model_name)
        assert resolution.model_name == model_name
        assert resolution.route == LLMRoute.OPENROUTER

    def test_resolve_openrouter_normalizes_minimax_model(self, monkeypatch):
        monkeypatch.setattr(settings, "openrouter_api_key", "test-openrouter")
        router = LLMRouter()
        resolution = router.resolve("openrouter", "MiniMaxAI/MiniMax-M2.1")
        assert resolution.model_name == "minimax/minimax-m2.1"
        assert resolution.route == LLMRoute.OPENROUTER


class TestBaseLLMService:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            BaseLLMService()

    def test_concrete_implementation_works(self):
        service = DeepSeekService()
        assert service.provider == LLMProvider.DEEPSEEK
