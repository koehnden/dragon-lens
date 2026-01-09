import asyncio
import json

from services.translater import (
    TranslaterService,
    _parse_batch_translation_response,
)


class FakeOllama:
    def __init__(self, response: str = ""):
        self.response = response
        self.call_count = 0
        self.last_prompts = []
        self.translation_model = "test-model"

    async def _call_ollama(self, model: str, prompt: str, system_prompt: str = None, temperature: float = 0.7):
        self.call_count += 1
        self.last_prompts.append(prompt)
        return self.response


def test_batch_translation_empty_list():
    fake = FakeOllama()
    translator = TranslaterService(fake)
    result = asyncio.run(translator.translate_batch([], "Chinese", "English"))
    assert result == []
    assert fake.call_count == 0


def test_batch_translation_single_item_uses_regular_translate():
    fake = FakeOllama("Hello World")
    translator = TranslaterService(fake)
    result = asyncio.run(translator.translate_batch(["你好世界"], "Chinese", "English"))
    assert result == ["Hello World"]
    assert fake.call_count == 1


def test_batch_translation_multiple_items():
    fake = FakeOllama('["Hello", "World", "Test"]')
    translator = TranslaterService(fake)
    result = asyncio.run(translator.translate_batch(
        ["你好", "世界", "测试"],
        "Chinese",
        "English"
    ))
    assert result == ["Hello", "World", "Test"]
    assert fake.call_count == 1


def test_batch_translation_handles_empty_strings():
    fake = FakeOllama('["Hello", "World"]')
    translator = TranslaterService(fake)
    result = asyncio.run(translator.translate_batch(
        ["你好", "", "世界"],
        "Chinese",
        "English"
    ))
    assert result[0] == "Hello"
    assert result[1] == ""
    assert result[2] == "World"


def test_batch_translation_sync():
    fake = FakeOllama('["Hello", "World"]')
    translator = TranslaterService(fake)
    result = translator.translate_batch_sync(
        ["你好", "世界"],
        "Chinese",
        "English"
    )
    assert result == ["Hello", "World"]


def test_parse_batch_response_valid_json():
    response = '["Hello", "World", "Test"]'
    originals = ["你好", "世界", "测试"]
    result = _parse_batch_translation_response(response, originals)
    assert result == ["Hello", "World", "Test"]


def test_parse_batch_response_with_markdown():
    response = '```json\n["Hello", "World"]\n```'
    originals = ["你好", "世界"]
    result = _parse_batch_translation_response(response, originals)
    assert result == ["Hello", "World"]


def test_parse_batch_response_with_extra_text():
    response = 'Here are the translations:\n["Hello", "World"]'
    originals = ["你好", "世界"]
    result = _parse_batch_translation_response(response, originals)
    assert result == ["Hello", "World"]


def test_parse_batch_response_length_mismatch_returns_original():
    response = '["Hello"]'
    originals = ["你好", "世界"]
    result = _parse_batch_translation_response(response, originals)
    assert result == originals


def test_parse_batch_response_invalid_json_returns_original():
    response = 'not valid json'
    originals = ["你好", "世界"]
    result = _parse_batch_translation_response(response, originals)
    assert result == originals


def test_parse_batch_response_empty_returns_original():
    response = ''
    originals = ["你好", "世界"]
    result = _parse_batch_translation_response(response, originals)
    assert result == originals


def test_parse_batch_response_null_item_uses_original():
    response = '["Hello", null]'
    originals = ["你好", "世界"]
    result = _parse_batch_translation_response(response, originals)
    assert result[0] == "Hello"
    assert result[1] == "世界"


def test_parse_batch_response_empty_string_item_uses_original():
    response = '["Hello", ""]'
    originals = ["你好", "世界"]
    result = _parse_batch_translation_response(response, originals)
    assert result[0] == "Hello"
    assert result[1] == "世界"


def test_batch_translation_preserves_order():
    fake = FakeOllama('["One", "Two", "Three", "Four", "Five"]')
    translator = TranslaterService(fake)
    result = asyncio.run(translator.translate_batch(
        ["一", "二", "三", "四", "五"],
        "Chinese",
        "English"
    ))
    assert result == ["One", "Two", "Three", "Four", "Five"]


def test_batch_translation_with_only_empty_strings():
    fake = FakeOllama()
    translator = TranslaterService(fake)
    result = asyncio.run(translator.translate_batch(
        ["", "  ", ""],
        "Chinese",
        "English"
    ))
    assert result == ["", "", ""]
    assert fake.call_count == 0
