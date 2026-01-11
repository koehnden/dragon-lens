import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from services.brand_recognition.product_brand_mapping import (
    _lookup_in_knowledge_cache,
    _apply_knowledge_mapping,
    _load_knowledge_cache,
)


def test_lookup_in_knowledge_cache_finds_exact_match():
    cache = {"rav4": "Toyota", "model y": "Tesla"}
    result = _lookup_in_knowledge_cache("rav4", cache)
    assert result == "Toyota"


def test_lookup_in_knowledge_cache_case_insensitive():
    cache = {"rav4": "Toyota", "model y": "Tesla"}
    result = _lookup_in_knowledge_cache("RAV4", cache)
    assert result == "Toyota"


def test_lookup_in_knowledge_cache_returns_none_for_unknown():
    cache = {"rav4": "Toyota", "model y": "Tesla"}
    result = _lookup_in_knowledge_cache("unknown", cache)
    assert result is None


def test_lookup_in_knowledge_cache_empty_cache():
    result = _lookup_in_knowledge_cache("rav4", {})
    assert result is None


def test_lookup_in_knowledge_cache_none_cache():
    result = _lookup_in_knowledge_cache("rav4", None)
    assert result is None


def test_apply_knowledge_mapping_updates_product():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    product = MagicMock()
    product.id = 1
    product.brand_id = None
    product.display_name = "RAV4"

    result = _apply_knowledge_mapping(db, 10, product, "Toyota", 20)

    assert result == {"RAV4": "Toyota"}
    assert product.brand_id == 20


def test_apply_knowledge_mapping_preserves_existing_brand():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    product = MagicMock()
    product.id = 1
    product.brand_id = 15
    product.display_name = "RAV4"

    result = _apply_knowledge_mapping(db, 10, product, "Toyota", 20)

    assert result == {"RAV4": "Toyota"}
    assert product.brand_id == 15


@patch("services.knowledge_lookup.build_mapping_cache")
def test_load_knowledge_cache_returns_cache(mock_build):
    db = MagicMock()
    vertical = MagicMock()
    vertical.name = "SUV Cars"
    db.query.return_value.filter.return_value.first.return_value = vertical

    mock_build.return_value = {"rav4": "Toyota"}

    result = _load_knowledge_cache(db, 1)

    assert result == {"rav4": "Toyota"}
    mock_build.assert_called_once_with("SUV Cars")


def test_load_knowledge_cache_returns_empty_for_unknown_vertical():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    result = _load_knowledge_cache(db, 1)

    assert result == {}


@pytest.mark.asyncio
@patch("services.brand_recognition.product_brand_mapping._qwen_brand")
@patch("services.brand_recognition.product_brand_mapping._resolve_product")
async def test_map_single_product_falls_back_to_knowledge(
    mock_resolve_product, mock_qwen_brand
):
    from services.brand_recognition.product_brand_mapping import _map_single_product

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    input_data = MagicMock()
    input_data.vertical_id = 1
    input_data.answer_entities = []

    product_record = MagicMock()
    product_record.id = 10
    product_record.brand_id = None
    product_record.display_name = "ES6"
    mock_resolve_product.return_value = product_record

    mock_qwen_brand.return_value = None

    brand_lookup = {"nio": 20, "蔚来": 20}
    product_lookup = {"es6": product_record}
    knowledge_cache = {"es6": "NIO"}

    result = await _map_single_product(
        db, input_data, "ES6", {}, brand_lookup, product_lookup, [], knowledge_cache
    )

    assert result == {"ES6": "NIO"}
    assert product_record.brand_id == 20


@pytest.mark.asyncio
@patch("services.brand_recognition.product_brand_mapping._qwen_brand")
@patch("services.brand_recognition.product_brand_mapping._resolve_product")
async def test_map_single_product_prefers_proximity_over_knowledge(
    mock_resolve_product, mock_qwen_brand
):
    from services.brand_recognition.product_brand_mapping import _map_single_product

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    input_data = MagicMock()
    input_data.vertical_id = 1
    input_data.answer_entities = []

    product_record = MagicMock()
    product_record.id = 10
    product_record.brand_id = None
    product_record.display_name = "RAV4"
    mock_resolve_product.return_value = product_record

    brand_lookup = {"toyota": 5, "honda": 6}
    product_lookup = {"rav4": product_record}
    knowledge_cache = {"rav4": "Honda"}
    brand_counts = {"Toyota": 5, "Honda": 1}

    result = await _map_single_product(
        db, input_data, "RAV4", brand_counts, brand_lookup, product_lookup, [],
        knowledge_cache
    )

    assert result == {"RAV4": "Toyota"}
