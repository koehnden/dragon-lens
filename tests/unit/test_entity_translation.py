import asyncio

from services.translater import (
    TranslaterService,
    format_entity_label,
    has_latin_letters,
    _clean_entity_translation,
    MAX_ENTITY_TRANSLATION_LENGTH,
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
    assert "rules" in (fake.last_system_prompt or "").lower()
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


def test_format_entity_label_chinese_original_english_translated():
    label = format_entity_label("大众", "Volkswagen")
    assert label == "Volkswagen (大众)"


def test_format_entity_label_english_original_chinese_translated():
    label = format_entity_label("Ford", "福特")
    assert label == "Ford (福特)"


def test_format_entity_label_mixed_text_extracts_parts():
    label = format_entity_label("比亚迪BYD", None)
    assert label == "BYD (比亚迪)"


def test_format_entity_label_english_only():
    label = format_entity_label("Tesla", None)
    assert label == "Tesla"


def test_format_entity_label_both_english():
    label = format_entity_label("VW", "Volkswagen")
    assert label == "VW"


def test_format_entity_label_jv_with_translation():
    label = format_entity_label("一汽大众", "FAW-VW")
    assert label == "FAW-VW (一汽大众)"


def test_clean_entity_translation_removes_note():
    result = _clean_entity_translation(
        "Ecar (Note: This is a direct translation of which means Easy Car)",
        "易车"
    )
    assert result == "Ecar"


def test_clean_entity_translation_removes_note_variant():
    result = _clean_entity_translation(
        "Chang'an Ford (note: This is likely a misspelling)",
        "长安福特"
    )
    assert result == "Chang'an Ford"


def test_clean_entity_translation_removes_this_means():
    result = _clean_entity_translation(
        "Great Wall (This means the brand Great Wall Motors)",
        "长城"
    )
    assert result == "Great Wall"


def test_clean_entity_translation_removes_translation_comment():
    result = _clean_entity_translation(
        "Haval (direct translation from Chinese)",
        "哈弗"
    )
    assert result == "Haval"


def test_clean_entity_translation_removes_misspelling_comment():
    result = _clean_entity_translation(
        "Changan (possible misspelling of Chang'an)",
        "长安"
    )
    assert result == "Changan"


def test_clean_entity_translation_max_length_returns_original():
    long_text = "A" * (MAX_ENTITY_TRANSLATION_LENGTH + 10)
    result = _clean_entity_translation(long_text, "original")
    assert result == "original"


def test_clean_entity_translation_preserves_good_input():
    result = _clean_entity_translation("BMW", "宝马")
    assert result == "BMW"


def test_clean_entity_translation_empty_returns_original():
    result = _clean_entity_translation("", "original")
    assert result == "original"


def test_clean_entity_translation_none_returns_original():
    result = _clean_entity_translation(None, "original")
    assert result == "original"


def test_translate_entity_cleans_noisy_response():
    fake = FakeOllama("Geely (Note: This is a Chinese automaker)")
    translator = TranslaterService(fake)
    result = asyncio.run(translator.translate_entity("吉利"))
    assert result == "Geely"
    assert fake.called
