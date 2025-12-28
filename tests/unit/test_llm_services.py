import pytest

from src.models.domain import LLMProvider
from src.services.base_llm import BaseLLMService
from src.services.remote_llms import DeepSeekService, KimiService, LLMRouter


class TestDeepSeekService:
    def test_has_correct_provider(self):
        assert DeepSeekService.provider == LLMProvider.DEEPSEEK

    def test_has_default_model(self):
        assert DeepSeekService.default_model == "deepseek-chat"

    def test_inherits_base_llm_service(self):
        assert issubclass(DeepSeekService, BaseLLMService)

    def test_inherits_openai_client_service(self):
        from src.services.openai_client import OpenAIClientService
        assert issubclass(DeepSeekService, OpenAIClientService)


class TestKimiService:
    def test_has_correct_provider(self):
        assert KimiService.provider == LLMProvider.KIMI

    def test_has_default_model(self):
        assert KimiService.default_model == "moonshot-v1-8k"

    def test_inherits_base_llm_service(self):
        assert issubclass(KimiService, BaseLLMService)

    def test_inherits_openai_client_service(self):
        from src.services.openai_client import OpenAIClientService
        assert issubclass(KimiService, OpenAIClientService)

    def test_builds_messages_with_system_prompt(self):
        service = KimiService()
        messages = service._build_messages("测试提示")

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "测试提示"

    def test_build_payload_is_dummy(self):
        """_build_payload is a dummy method in OpenAIClientService."""
        service = KimiService()
        messages = [{"role": "user", "content": "test"}]
        payload = service._build_payload(messages, "moonshot-v1-8k")
        # Should return empty dict as dummy implementation
        assert isinstance(payload, dict)


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

    def test_caches_services(self):
        router = LLMRouter()
        service1 = router._get_service(LLMProvider.DEEPSEEK)
        service2 = router._get_service(LLMProvider.DEEPSEEK)
        assert service1 is service2

    def test_raises_for_unknown_remote_provider(self):
        router = LLMRouter()
        with pytest.raises(ValueError, match="No remote service"):
            router._create_service(LLMProvider.QWEN)


class TestBaseLLMService:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            BaseLLMService()

    def test_concrete_implementation_works(self):
        service = DeepSeekService()
        assert service.provider == LLMProvider.DEEPSEEK
