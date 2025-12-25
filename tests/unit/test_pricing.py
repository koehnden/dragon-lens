import pytest

from src.models.domain import LLMProvider
from src.services.pricing import PRICING, calculate_cost


class TestPricingData:
    def test_all_providers_have_pricing(self):
        for provider in LLMProvider:
            assert provider in PRICING

    def test_qwen_is_free(self):
        assert PRICING[LLMProvider.QWEN] == {}

    def test_deepseek_has_models(self):
        assert "deepseek-chat" in PRICING[LLMProvider.DEEPSEEK]

    def test_kimi_has_all_models(self):
        kimi_models = PRICING[LLMProvider.KIMI]
        assert "moonshot-v1-8k" in kimi_models
        assert "moonshot-v1-32k" in kimi_models
        assert "moonshot-v1-128k" in kimi_models


class TestCalculateCost:
    def test_qwen_returns_zero(self):
        result = calculate_cost("qwen", "qwen2.5:7b", 1000, 500)
        assert result == 0.0

    def test_deepseek_chat_cost(self):
        result = calculate_cost("deepseek", "deepseek-chat", 1_000_000, 1_000_000)
        expected = 0.14 + 0.28
        assert result == pytest.approx(expected, rel=1e-4)

    def test_kimi_8k_cost(self):
        result = calculate_cost("kimi", "moonshot-v1-8k", 1000, 1000)
        expected = 2 * 0.012
        assert result == pytest.approx(expected, rel=1e-4)

    def test_kimi_32k_cost(self):
        result = calculate_cost("kimi", "moonshot-v1-32k", 1000, 1000)
        expected = 2 * 0.024
        assert result == pytest.approx(expected, rel=1e-4)

    def test_kimi_128k_cost(self):
        result = calculate_cost("kimi", "moonshot-v1-128k", 1000, 1000)
        expected = 2 * 0.06
        assert result == pytest.approx(expected, rel=1e-4)

    def test_unknown_provider_returns_zero(self):
        result = calculate_cost("unknown", "model", 1000, 500)
        assert result == 0.0

    def test_unknown_model_returns_zero(self):
        result = calculate_cost("deepseek", "unknown-model", 1000, 500)
        assert result == 0.0

    def test_case_insensitive_provider(self):
        result1 = calculate_cost("DEEPSEEK", "deepseek-chat", 1000, 500)
        result2 = calculate_cost("deepseek", "deepseek-chat", 1000, 500)
        assert result1 == result2

    def test_case_insensitive_model(self):
        result1 = calculate_cost("kimi", "MOONSHOT-V1-8K", 1000, 500)
        result2 = calculate_cost("kimi", "moonshot-v1-8k", 1000, 500)
        assert result1 == result2
