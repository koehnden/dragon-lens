import pytest


def test_ollama_service_init_does_not_load_sentiment(monkeypatch):
    from services import ollama as ollama_module

    def _boom():
        raise AssertionError("get_sentiment_service should not be called during init")

    monkeypatch.setattr(ollama_module, "get_sentiment_service", _boom)

    ollama_module.OllamaService()


@pytest.mark.asyncio
async def test_classify_sentiment_lazy_loads_once(monkeypatch):
    from services import ollama as ollama_module

    class DummySentimentService:
        def __init__(self):
            self.calls = 0

        def classify_sentiment(self, text: str) -> str:
            self.calls += 1
            return "positive"

    dummy = DummySentimentService()
    loader_calls: list[int] = []

    def _loader():
        loader_calls.append(1)
        return dummy

    monkeypatch.setattr(ollama_module.settings, "use_erlangshen_sentiment", True)
    monkeypatch.setattr(ollama_module, "get_sentiment_service", _loader)

    service = ollama_module.OllamaService()

    assert await service.classify_sentiment("测试") == "positive"
    assert await service.classify_sentiment("再测") == "positive"
    assert dummy.calls == 2
    assert len(loader_calls) == 1


@pytest.mark.asyncio
async def test_classify_sentiment_does_not_load_when_disabled(monkeypatch):
    from services import ollama as ollama_module

    async def _fake_qwen(_: str) -> str:
        return "neutral"

    def _boom():
        raise AssertionError("get_sentiment_service should not be called when disabled")

    monkeypatch.setattr(ollama_module.settings, "use_erlangshen_sentiment", False)
    monkeypatch.setattr(ollama_module, "get_sentiment_service", _boom)

    service = ollama_module.OllamaService()
    monkeypatch.setattr(service, "_classify_sentiment_with_qwen", _fake_qwen)

    assert await service.classify_sentiment("测试") == "neutral"

