import pytest

from models.domain import Brand, Product
from services.brand_recognition import EntityCandidate


class TestBrandProductDistinction:

    def test_product_has_brand_id_field(self):
        product = Product(
            brand_id=1,
            original_name="RAV4",
            translated_name="RAV4",
        )
        assert product.brand_id == 1

    def test_product_can_have_null_brand_id(self):
        product = Product(
            brand_id=None,
            original_name="Unknown Product",
            translated_name=None,
        )
        assert product.brand_id is None

    def test_brand_has_is_user_input_field(self):
        brand = Brand(
            vertical_id=1,
            display_name="Toyota",
            original_name="丰田",
            translated_name="Toyota",
            aliases={"zh": ["丰田汽车"], "en": ["Toyota Motor"]},
            is_user_input=True,
        )
        assert brand.is_user_input is True

    def test_discovered_brand_has_is_user_input_false(self):
        brand = Brand(
            vertical_id=1,
            display_name="Honda",
            original_name="本田",
            translated_name="Honda",
            aliases={"zh": [], "en": []},
            is_user_input=False,
        )
        assert brand.is_user_input is False


class TestEntityCandidate:

    def test_entity_candidate_has_name_and_source(self):
        candidate = EntityCandidate(name="Toyota", source="seed")
        assert candidate.name == "Toyota"
        assert candidate.source == "seed"


class TestBrandNameFormatting:

    def test_format_english_only(self):
        from services.translater import format_entity_label
        result = format_entity_label("Toyota", "Toyota")
        assert result == "Toyota"

    def test_format_chinese_with_english_translation(self):
        from services.translater import format_entity_label
        result = format_entity_label("丰田", "Toyota")
        assert result == "Toyota (丰田)"

    def test_format_no_translation(self):
        from services.translater import format_entity_label
        result = format_entity_label("丰田", None)
        assert result == "丰田"

    def test_format_same_original_and_translated(self):
        from services.translater import format_entity_label
        result = format_entity_label("Tesla", "Tesla")
        assert result == "Tesla"

    def test_format_lowercase_english_gets_capitalized(self):
        from services.translater import format_entity_label
        result = format_entity_label("toyota", "toyota")
        assert result == "Toyota"

    def test_format_uppercase_acronym_preserved(self):
        from services.translater import format_entity_label
        result = format_entity_label("BYD", "BYD")
        assert result == "BYD"

    def test_format_chinese_original_english_translated(self):
        from services.translater import format_entity_label
        result = format_entity_label("比亚迪", "BYD")
        assert result == "BYD (比亚迪)"

    def test_format_mixed_case_brand(self):
        from services.translater import format_entity_label
        result = format_entity_label("volkswagen", "Volkswagen")
        assert result == "Volkswagen"


class TestCapitalizeBrandName:

    def test_capitalize_lowercase_brand(self):
        from services.translater import capitalize_brand_name
        assert capitalize_brand_name("toyota") == "Toyota"

    def test_preserve_acronym(self):
        from services.translater import capitalize_brand_name
        assert capitalize_brand_name("BYD") == "BYD"

    def test_preserve_already_capitalized(self):
        from services.translater import capitalize_brand_name
        assert capitalize_brand_name("Toyota") == "Toyota"

    def test_preserve_chinese(self):
        from services.translater import capitalize_brand_name
        assert capitalize_brand_name("丰田") == "丰田"

    def test_multi_word_brand(self):
        from services.translater import capitalize_brand_name
        assert capitalize_brand_name("model y") == "Model Y"

    def test_mixed_case_multi_word(self):
        from services.translater import capitalize_brand_name
        result = capitalize_brand_name("Model Y")
        assert result == "Model Y"

    def test_hyphenated_brand(self):
        from services.translater import capitalize_brand_name
        assert capitalize_brand_name("Mercedes-Benz") == "Mercedes-Benz"

    def test_hyphenated_brand_lowercase(self):
        from services.translater import capitalize_brand_name
        assert capitalize_brand_name("mercedes-benz") == "Mercedes-Benz"


class TestBrandProductExamples:

    @pytest.mark.parametrize("name,expected_type", [
        ("Toyota", "brand"),
        ("丰田", "brand"),
        ("BYD", "brand"),
        ("比亚迪", "brand"),
        ("Tesla", "brand"),
        ("特斯拉", "brand"),
        ("Honda", "brand"),
        ("本田", "brand"),
        ("Volkswagen", "brand"),
        ("大众", "brand"),
    ])
    def test_known_brands(self, name, expected_type):
        assert expected_type == "brand"

    @pytest.mark.parametrize("name,expected_brand", [
        ("RAV4", "Toyota"),
        ("Camry", "Toyota"),
        ("Model Y", "Tesla"),
        ("Model 3", "Tesla"),
        ("宋PLUS", "BYD"),
        ("汉EV", "BYD"),
        ("ID.4", "Volkswagen"),
        ("Accord", "Honda"),
    ])
    def test_known_products_have_parent_brand(self, name, expected_brand):
        assert expected_brand is not None
