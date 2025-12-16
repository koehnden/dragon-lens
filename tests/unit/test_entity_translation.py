import asyncio

from services.translater import (
    TranslaterService,
    format_entity_label,
    has_latin_letters,
)


class FakeOllama:
    def __init__(self, response: str = ""):
        self.response = response
        self.called = False
        self.last_system_prompt = None
        self.last_prompt = None
        self.translation_model = "test-model"

    async def _call_ollama(self, model: str, prompt: str, system_prompt: str = None, temperature: float = 0.7):
        self.called = True
        self.last_system_prompt = system_prompt
        self.last_prompt = prompt
        return self.response


def test_has_latin_letters_detects_ascii():
    assert has_latin_letters("Tesla")
    assert not has_latin_letters("吉利")


def test_translate_skips_latin_names():
    fake = FakeOllama("Skipped")
    translator = TranslaterService(fake)
    result = asyncio.run(translator.translate_entity("BYD"))
    assert result == "BYD"
    assert not fake.called


def test_translate_non_latin_uses_guardrails():
    fake = FakeOllama("Geely")
    translator = TranslaterService(fake)
    result = asyncio.run(translator.translate_entity("吉利"))
    assert result == "Geely"
    assert fake.called
    assert "invent" in (fake.last_system_prompt or "").lower()
    assert "Translate" in fake.last_prompt


def test_translate_text_adds_language_prompts():
    fake = FakeOllama("你好")
    translator = TranslaterService(fake)
    result = asyncio.run(translator.translate_text("Hello", "English", "Chinese"))
    assert result == "你好"
    assert "English" in (fake.last_prompt or "")
    assert "Chinese" in (fake.last_prompt or "")
    assert "translated" in (fake.last_system_prompt or "").lower()


def test_format_entity_label_prefers_translation():
    label = format_entity_label("吉利博越", "Geely Boyue")
    assert label == "Geely Boyue (吉利博越)"


def test_format_entity_label_without_change():
    label = format_entity_label("Tesla", "Tesla")
    assert label == "Tesla"
