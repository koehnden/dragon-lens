import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import json


def test_qwen_extraction_parses_valid_json():
    from services.brand_recognition import _parse_extraction_response

    response = '{"brands": ["Toyota", "Honda"], "products": ["RAV4", "CR-V"]}'
    result = _parse_extraction_response(response)

    assert result["brands"] == ["Toyota", "Honda"]
    assert result["products"] == ["RAV4", "CR-V"]


def test_qwen_extraction_parses_markdown_json():
    from services.brand_recognition import _parse_extraction_response

    response = """```json
{"brands": ["比亚迪", "特斯拉"], "products": ["宋PLUS", "Model Y"]}
```"""
    result = _parse_extraction_response(response)

    assert "比亚迪" in result["brands"]
    assert "宋PLUS" in result["products"]


def test_qwen_extraction_handles_malformed_json():
    from services.brand_recognition import _parse_extraction_response

    response = "Here are the brands: Toyota and Honda"
    result = _parse_extraction_response(response)

    assert result["brands"] == []
    assert result["products"] == []


def test_qwen_extraction_extracts_embedded_json():
    from services.brand_recognition import _parse_extraction_response

    response = """Based on the text, here are the extracted entities:
{"brands": ["Apple", "Samsung"], "products": ["iPhone 15", "Galaxy S24"]}
These are the main entities found."""

    result = _parse_extraction_response(response)

    assert "Apple" in result["brands"]
    assert "iPhone 15" in result["products"]


def test_build_extraction_system_prompt_includes_vertical():
    from services.brand_recognition import _build_extraction_system_prompt

    prompt = _build_extraction_system_prompt("Skincare", "Facial care products")

    assert "Skincare" in prompt
    assert "Facial care products" in prompt
    assert "BRAND" in prompt
    assert "PRODUCT" in prompt
    assert "DO NOT EXTRACT" in prompt


def test_extraction_prompt_includes_rejected_brands():
    from services.brand_recognition import _build_extraction_system_prompt

    context = {"rejected_brands": [{"name": "BadBrand", "reason": "off_vertical"}]}
    prompt = _build_extraction_system_prompt("Cars", "", context)

    assert "BadBrand" in prompt


def test_build_extraction_prompt_truncates_long_text():
    from services.brand_recognition import _build_extraction_prompt

    long_text = "a" * 3000
    prompt = _build_extraction_prompt(long_text)

    assert len(prompt) < 2500


@pytest.mark.asyncio
async def test_extract_entities_with_qwen_returns_clusters():
    from services.brand_recognition import _extract_entities_with_qwen

    extraction_response = json.dumps({
        "brands": ["Toyota", "Honda"],
        "products": ["RAV4", "Civic"]
    })
    normalization_response = json.dumps({
        "brands": [
            {"canonical": "Toyota", "chinese": "丰田", "original_forms": ["Toyota"]},
            {"canonical": "Honda", "chinese": "本田", "original_forms": ["Honda"]}
        ],
        "rejected": []
    })
    product_validation_response = json.dumps({
        "valid": ["RAV4", "Civic"],
        "invalid": []
    })

    mock_ollama_instance = MagicMock()
    mock_ollama_instance._call_ollama = AsyncMock(side_effect=[
        extraction_response,
        normalization_response,
        product_validation_response,
    ])
    mock_ollama_instance.ner_model = "qwen2.5:7b"

    with patch('services.ollama.OllamaService', return_value=mock_ollama_instance):
        result = await _extract_entities_with_qwen(
            "Toyota RAV4 vs Honda Civic comparison",
            vertical="Cars",
            vertical_description="Automobiles"
        )

    all_entities = result.all_entities()
    assert "Toyota" in all_entities or "Honda" in all_entities
    assert len(all_entities) >= 1


@pytest.mark.asyncio
async def test_extract_entities_with_qwen_handles_error():
    from services.brand_recognition import _extract_entities_with_qwen

    mock_ollama_instance = MagicMock()
    mock_ollama_instance._call_ollama = AsyncMock(side_effect=Exception("API error"))
    mock_ollama_instance.ner_model = "qwen2.5:7b"

    with patch('services.ollama.OllamaService', return_value=mock_ollama_instance):
        result = await _extract_entities_with_qwen("Some text")

    assert result.brands == {}
    assert result.products == {}


def test_extraction_rejects_false_positives():
    from services.brand_recognition import _build_extraction_system_prompt

    prompt = _build_extraction_system_prompt("SUV Cars", "Sport utility vehicles")

    assert "产品质量" in prompt or "descriptive phrases" in prompt.lower()
    assert "先进" in prompt or "adjectives" in prompt.lower()
    assert "与宝马" in prompt or "preposition" in prompt.lower()
