import pytest
from services.brand_recognition.models import ExtractionResult, ExtractionDebugInfo
from services.brand_recognition.brand_extractor import _filter_relationships
from services.product_discovery import _lookup_relationship


def test_extraction_result_includes_relationships():
    result = ExtractionResult(
        brands={"BYD": ["BYD"]},
        products={"宋PLUS": ["宋PLUS"]},
        product_brand_relationships={"宋PLUS": "BYD"},
    )
    assert result.product_brand_relationships == {"宋PLUS": "BYD"}


def test_extraction_result_default_empty_relationships():
    result = ExtractionResult(
        brands={"BYD": ["BYD"]},
        products={"宋PLUS": ["宋PLUS"]},
    )
    assert result.product_brand_relationships == {}


def test_filter_relationships_keeps_valid():
    relationships = {"RAV4": "Toyota", "宋PLUS": "BYD"}
    valid_products = {"RAV4", "宋PLUS"}
    valid_brands = {"Toyota", "BYD"}

    filtered = _filter_relationships(relationships, valid_products, valid_brands)

    assert filtered == {"RAV4": "Toyota", "宋PLUS": "BYD"}


def test_filter_relationships_removes_invalid_product():
    relationships = {"RAV4": "Toyota", "InvalidProduct": "BYD"}
    valid_products = {"RAV4"}
    valid_brands = {"Toyota", "BYD"}

    filtered = _filter_relationships(relationships, valid_products, valid_brands)

    assert filtered == {"RAV4": "Toyota"}
    assert "InvalidProduct" not in filtered


def test_filter_relationships_removes_invalid_brand():
    relationships = {"RAV4": "Toyota", "宋PLUS": "InvalidBrand"}
    valid_products = {"RAV4", "宋PLUS"}
    valid_brands = {"Toyota"}

    filtered = _filter_relationships(relationships, valid_products, valid_brands)

    assert filtered == {"RAV4": "Toyota"}
    assert "宋PLUS" not in filtered


def test_filter_relationships_case_insensitive():
    relationships = {"rav4": "toyota", "Song Plus": "byd"}
    valid_products = {"RAV4", "Song Plus"}
    valid_brands = {"Toyota", "BYD"}

    filtered = _filter_relationships(relationships, valid_products, valid_brands)

    assert "rav4" in filtered
    assert "Song Plus" in filtered


def test_lookup_relationship_exact_match():
    relationships = {"RAV4": "Toyota", "宋PLUS": "BYD"}

    result = _lookup_relationship("RAV4", relationships)

    assert result == "Toyota"


def test_lookup_relationship_case_insensitive():
    relationships = {"RAV4": "Toyota", "宋PLUS": "BYD"}

    result = _lookup_relationship("rav4", relationships)

    assert result == "Toyota"


def test_lookup_relationship_not_found():
    relationships = {"RAV4": "Toyota"}

    result = _lookup_relationship("CR-V", relationships)

    assert result is None


def test_lookup_relationship_empty_dict():
    result = _lookup_relationship("RAV4", {})

    assert result is None
