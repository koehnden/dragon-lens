import pytest

from services.brand_recognition import (
    extract_primary_entities_from_list_item,
    is_list_format,
    split_into_list_items,
)


class TestListPrimaryExtraction:

    def test_extract_first_brand_and_product_only(self):
        item = "Honda CRV is a great SUV choice. Another great option from Honda is the Honda HR-V similar to Toyota RAV4."
        result = extract_primary_entities_from_list_item(item)
        assert result["primary_brand"] == "Honda"
        assert result["primary_product"] == "CRV"
        assert "Toyota" not in result.get("primary_brand", "")
        assert "RAV4" not in result.get("primary_product", "")

    def test_extract_brand_product_from_simple_item(self):
        item = "VW Tuareq"
        result = extract_primary_entities_from_list_item(item)
        assert result["primary_brand"] == "VW"
        assert result["primary_product"] == "Tuareq"

    def test_extract_chinese_brand_product(self):
        item = "比亚迪宋PLUS DM-i是非常好的选择，性价比高于特斯拉Model Y"
        result = extract_primary_entities_from_list_item(item)
        assert result["primary_brand"] == "比亚迪"
        assert "宋PLUS" in result["primary_product"]
        assert "特斯拉" not in result.get("primary_brand", "")

    def test_ignore_generic_terms(self):
        item = "SUV is a popular vehicle type. The Honda CRV is a top choice."
        result = extract_primary_entities_from_list_item(item)
        assert result.get("primary_brand") != "SUV"
        assert "SUV" not in result.get("primary_product", "")

    def test_ignore_single_word_non_brands(self):
        item = "One of the best options is the Toyota RAV4"
        result = extract_primary_entities_from_list_item(item)
        assert result.get("primary_brand") != "One"
        assert result["primary_brand"] == "Toyota"


class TestListItemExtraction:

    def test_numbered_list_extracts_items(self):
        text = """Here are my recommendations:
1. Honda CRV is a great SUV choice similar to Toyota RAV4.
2. VW Tuareq is another excellent option.
3. BMW X5 offers premium features."""
        assert is_list_format(text)
        items = split_into_list_items(text)
        assert len(items) == 3

    def test_bulleted_list_extracts_items(self):
        text = """Top SUV choices:
- Honda CRV with good fuel economy
- Toyota RAV4 with hybrid option
- VW Tuareq for European style"""
        assert is_list_format(text)
        items = split_into_list_items(text)
        assert len(items) == 3


class TestEntityClassification:

    @pytest.mark.parametrize("entity,expected_type", [
        ("Honda", "brand"),
        ("Toyota", "brand"),
        ("BYD", "brand"),
        ("比亚迪", "brand"),
        ("Volkswagen", "brand"),
        ("VW", "brand"),
        ("BMW", "brand"),
        ("Tesla", "brand"),
        ("CRV", "product"),
        ("RAV4", "product"),
        ("Model Y", "product"),
        ("宋PLUS", "product"),
        ("X5", "product"),
        ("ID.4", "product"),
        ("SUV", "other"),
        ("CarPlay", "other"),
        ("One", "other"),
    ])
    def test_entity_type_classification(self, entity, expected_type):
        from services.brand_recognition import classify_entity_type
        result = classify_entity_type(entity, vertical="SUV cars")
        assert result == expected_type


class TestBrandProductHeuristics:

    def test_known_brand_patterns(self):
        from services.brand_recognition import is_likely_brand
        assert is_likely_brand("Honda") is True
        assert is_likely_brand("Toyota") is True
        assert is_likely_brand("BYD") is True
        assert is_likely_brand("比亚迪") is True

    def test_product_patterns(self):
        from services.brand_recognition import is_likely_product
        assert is_likely_product("CRV") is True
        assert is_likely_product("RAV4") is True
        assert is_likely_product("Model Y") is True
        assert is_likely_product("宋PLUS") is True
        assert is_likely_product("X5") is True

    def test_generic_terms_not_brand_or_product(self):
        from services.brand_recognition import is_likely_brand, is_likely_product
        assert is_likely_brand("SUV") is False
        assert is_likely_product("SUV") is False
        assert is_likely_brand("One") is False
        assert is_likely_brand("CarPlay") is False
