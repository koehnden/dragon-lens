import pytest

from services.brand_recognition import _extract_evidence, _parse_json_response


def test_extract_evidence_finds_simple_match():
    text = "我喜欢比亚迪的车"
    evidence = _extract_evidence("比亚迪", text)

    assert evidence is not None
    assert evidence["mention"] == "比亚迪"
    assert "比亚迪" in evidence["snippet"]
    assert evidence["start"] == 3
    assert evidence["end"] == 6


def test_extract_evidence_finds_case_insensitive():
    text = "I love Tesla Model Y"
    evidence = _extract_evidence("tesla", text)

    assert evidence is not None
    assert evidence["mention"] == "Tesla"
    assert "Tesla" in evidence["snippet"]


def test_extract_evidence_adds_context():
    text = "今天天气很好，我去比亚迪4S店看了宋PLUS，感觉不错"
    evidence = _extract_evidence("宋PLUS", text, context_chars=10)

    assert evidence is not None
    assert "..." in evidence["snippet"]
    assert "宋PLUS" in evidence["snippet"]


def test_extract_evidence_returns_none_when_not_found():
    text = "我喜欢大众的车"
    evidence = _extract_evidence("特斯拉", text)

    assert evidence is None


def test_parse_json_response_handles_plain_json():
    response = '{"type": "brand", "confidence": 0.9, "why": "car company"}'
    result = _parse_json_response(response)

    assert result is not None
    assert result["type"] == "brand"
    assert result["confidence"] == 0.9
    assert result["why"] == "car company"


def test_parse_json_response_handles_markdown_json():
    response = '''```json
{"type": "product", "confidence": 0.85, "why": "model name"}
```'''
    result = _parse_json_response(response)

    assert result is not None
    assert result["type"] == "product"


def test_parse_json_response_handles_code_block():
    response = '''```
{"type": "other", "confidence": 0.7, "why": "feature descriptor"}
```'''
    result = _parse_json_response(response)

    assert result is not None
    assert result["type"] == "other"


def test_parse_json_response_extracts_json_from_text():
    response = 'Sure! Here is the result: {"type": "brand", "confidence": 0.95, "why": "known brand"} Hope this helps!'
    result = _parse_json_response(response)

    assert result is not None
    assert result["type"] == "brand"


def test_parse_json_response_returns_none_for_invalid():
    response = "This is not JSON at all"
    result = _parse_json_response(response)

    assert result is None


def test_parse_json_response_handles_optional_canonical():
    response = '{"type": "brand", "canonical_guess": "BYD", "confidence": 0.9, "why": "brand name"}'
    result = _parse_json_response(response)

    assert result is not None
    assert result["canonical_guess"] == "BYD"


@pytest.mark.asyncio
async def test_verify_entity_with_qwen_brand():
    from unittest.mock import AsyncMock, Mock
    from services.brand_recognition import _verify_entity_with_qwen

    ollama = Mock()
    ollama.ner_model = "qwen"
    ollama._call_ollama = AsyncMock(return_value='{"type": "brand", "confidence": 0.9, "why": "car manufacturer"}')

    text = "我最喜欢比亚迪的车"
    result = await _verify_entity_with_qwen(ollama, "比亚迪", text)

    assert result is not None
    assert result["type"] == "brand"
    assert result["confidence"] == 0.9
    assert "why" in result


@pytest.mark.asyncio
async def test_verify_entity_with_qwen_product():
    from unittest.mock import AsyncMock, Mock
    from services.brand_recognition import _verify_entity_with_qwen

    ollama = Mock()
    ollama.ner_model = "qwen"
    ollama._call_ollama = AsyncMock(return_value='{"type": "product", "confidence": 0.85, "why": "model name"}')

    text = "宋PLUS很受欢迎"
    result = await _verify_entity_with_qwen(ollama, "宋PLUS", text)

    assert result is not None
    assert result["type"] == "product"


@pytest.mark.asyncio
async def test_verify_entity_with_qwen_other():
    from unittest.mock import AsyncMock, Mock
    from services.brand_recognition import _verify_entity_with_qwen

    ollama = Mock()
    ollama.ner_model = "qwen"
    ollama._call_ollama = AsyncMock(return_value='{"type": "other", "confidence": 0.95, "why": "feature descriptor"}')

    text = "这车的保湿效果很好"
    result = await _verify_entity_with_qwen(ollama, "保湿效果", text)

    assert result is not None
    assert result["type"] == "other"


@pytest.mark.asyncio
async def test_verify_entity_with_qwen_not_found():
    from unittest.mock import Mock
    from services.brand_recognition import _verify_entity_with_qwen

    ollama = Mock()
    text = "这是一段没有品牌的文字"
    result = await _verify_entity_with_qwen(ollama, "特斯拉", text)

    assert result is None


@pytest.mark.asyncio
async def test_verify_entity_with_qwen_invalid_response():
    from unittest.mock import AsyncMock, Mock
    from services.brand_recognition import _verify_entity_with_qwen

    ollama = Mock()
    ollama.ner_model = "qwen"
    ollama._call_ollama = AsyncMock(return_value='This is not valid JSON')

    text = "比亚迪很好"
    result = await _verify_entity_with_qwen(ollama, "比亚迪", text)

    assert result is None


@pytest.mark.asyncio
async def test_verify_entity_with_qwen_missing_fields():
    from unittest.mock import AsyncMock, Mock
    from services.brand_recognition import _verify_entity_with_qwen

    ollama = Mock()
    ollama.ner_model = "qwen"
    ollama._call_ollama = AsyncMock(return_value='{"type": "brand"}')

    text = "比亚迪很好"
    result = await _verify_entity_with_qwen(ollama, "比亚迪", text)

    assert result is None
