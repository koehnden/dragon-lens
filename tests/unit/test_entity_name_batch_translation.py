import pytest

from services.translater import TranslaterService


class DummyOllama:
    translation_model = "qwen"

    def __init__(self, first: str, retry: str):
        self._first = first
        self._retry = retry
        self.calls: list[tuple[str, str]] = []

    async def _call_ollama(self, model: str, prompt: str, system_prompt: str, temperature: float = 0.1) -> str:
        self.calls.append((prompt, system_prompt))
        if "romanization" in (system_prompt or "").lower():
            return self._retry
        return self._first


class FailingOllama:
    translation_model = "qwen"

    async def _call_ollama(self, model: str, prompt: str, system_prompt: str, temperature: float = 0.1) -> str:
        raise RuntimeError("ollama down")


@pytest.mark.asyncio
async def test_translate_entities_to_english_batch_success_no_retry():
    first = '[{"type":"brand","name":"比亚迪","english":"BYD"},{"type":"product","name":"宋PLUS DM-i","english":"Song Plus DM-i"}]'
    ollama = DummyOllama(first=first, retry="[]")
    translator = TranslaterService(ollama)
    items = [{"type": "brand", "name": "比亚迪"}, {"type": "product", "name": "宋PLUS DM-i"}]

    mapping = await translator.translate_entities_to_english_batch(items, "cars", "car brands and models")

    assert mapping[("brand", "比亚迪")] == "BYD"
    assert mapping[("product", "宋PLUS DM-i")] == "Song Plus DM-i"
    assert len(ollama.calls) == 1


@pytest.mark.asyncio
async def test_translate_entities_to_english_batch_normalizes_type_casing():
    first = '[{"type":"Brand","name":"比亚迪","english":"BYD"},{"type":"PRODUCT","name":"宋PLUS DM-i","english":"Song Plus DM-i"}]'
    ollama = DummyOllama(first=first, retry="[]")
    translator = TranslaterService(ollama)
    items = [{"type": "brand", "name": "比亚迪"}, {"type": "product", "name": "宋PLUS DM-i"}]

    mapping = await translator.translate_entities_to_english_batch(items, "cars", "car brands and models")

    assert mapping[("brand", "比亚迪")] == "BYD"
    assert mapping[("product", "宋PLUS DM-i")] == "Song Plus DM-i"
    assert len(ollama.calls) == 1


@pytest.mark.asyncio
async def test_translate_entities_to_english_batch_retries_missing_or_invalid():
    first = '[{"type":"brand","name":"广汽","english":null},{"type":"brand","name":"大众","english":"Volkswagen Group (大众)"}]'
    retry = '[{"type":"brand","name":"广汽","english":"GAC"},{"type":"brand","name":"大众","english":"Volkswagen"}]'
    ollama = DummyOllama(first=first, retry=retry)
    translator = TranslaterService(ollama)
    items = [{"type": "brand", "name": "广汽"}, {"type": "brand", "name": "大众"}]

    mapping = await translator.translate_entities_to_english_batch(items, "cars", "car brands and models")

    assert mapping[("brand", "广汽")] == "GAC"
    assert mapping[("brand", "大众")] == "Volkswagen"
    assert len(ollama.calls) == 2


@pytest.mark.asyncio
async def test_translate_entities_to_english_batch_ignores_ollama_errors():
    translator = TranslaterService(FailingOllama())
    items = [{"type": "brand", "name": "比亚迪"}]

    mapping = await translator.translate_entities_to_english_batch(items, "cars", "car brands and models")

    assert mapping == {}
