"""Test entity label formatting for display."""

import pytest

from services.translater import format_entity_label


class TestFormatEntityLabel:

    def test_english_only_capitalized(self):
        result = format_entity_label("honda", None)
        assert result == "Honda"

    def test_english_with_chinese_in_brackets(self):
        result = format_entity_label("比亚迪", "BYD")
        assert result == "BYD (比亚迪)"

    def test_chinese_only_unchanged(self):
        result = format_entity_label("比亚迪", None)
        assert result == "比亚迪"

    def test_english_already_capitalized(self):
        result = format_entity_label("Toyota", None)
        assert result == "Toyota"

    def test_mixed_case_product(self):
        result = format_entity_label("iphone 15 pro", None)
        assert result == "Iphone 15 Pro"

    def test_chinese_with_english_translation(self):
        result = format_entity_label("大众", "Volkswagen")
        assert result == "Volkswagen (大众)"

    def test_brand_product_combination(self):
        result = format_entity_label("本田crv", "Honda CRV")
        assert result == "Honda CRV (本田crv)"

    def test_same_original_and_translated(self):
        result = format_entity_label("Nike", "Nike")
        assert result == "Nike"

    def test_empty_translation_uses_original(self):
        result = format_entity_label("Adidas", "")
        assert result == "Adidas"

    def test_whitespace_handling(self):
        result = format_entity_label("  honda  ", "  Honda  ")
        assert result == "Honda"

    def test_model_number_preserved(self):
        result = format_entity_label("model y", "Model Y")
        assert result == "Model Y"

    def test_acronym_preserved(self):
        result = format_entity_label("宝马", "BMW")
        assert result == "BMW (宝马)"
