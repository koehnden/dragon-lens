"""Test entity type classification for brands vs products."""

import pytest

from models.domain import EntityType
from services.brand_discovery import classify_entity_type


class TestEntityTypeClassification:

    def test_classifies_standalone_brand_name(self):
        assert classify_entity_type("Honda") == EntityType.BRAND
        assert classify_entity_type("Toyota") == EntityType.BRAND
        assert classify_entity_type("Nike") == EntityType.BRAND
        assert classify_entity_type("Adidas") == EntityType.BRAND

    def test_classifies_chinese_brand_name(self):
        assert classify_entity_type("比亚迪") == EntityType.BRAND
        assert classify_entity_type("大众") == EntityType.BRAND
        assert classify_entity_type("丰田") == EntityType.BRAND
        assert classify_entity_type("宝马") == EntityType.BRAND

    def test_classifies_product_with_model_number(self):
        assert classify_entity_type("RAV4") == EntityType.PRODUCT
        assert classify_entity_type("Model Y") == EntityType.PRODUCT
        assert classify_entity_type("iPhone 15") == EntityType.PRODUCT
        assert classify_entity_type("X5") == EntityType.PRODUCT

    def test_classifies_product_with_variant_suffix(self):
        assert classify_entity_type("宋PLUS") == EntityType.PRODUCT
        assert classify_entity_type("iPhone Pro Max") == EntityType.PRODUCT
        assert classify_entity_type("Galaxy S24 Ultra") == EntityType.PRODUCT

    def test_classifies_combined_brand_product(self):
        assert classify_entity_type("Toyota RAV4") == EntityType.PRODUCT
        assert classify_entity_type("比亚迪宋PLUS") == EntityType.PRODUCT
        assert classify_entity_type("BMW X5") == EntityType.PRODUCT

    def test_classifies_single_letters_numbers_as_unknown(self):
        assert classify_entity_type("X") == EntityType.UNKNOWN
        assert classify_entity_type("1") == EntityType.UNKNOWN
        assert classify_entity_type("suv1") == EntityType.UNKNOWN

    def test_classifies_generic_terms_as_unknown(self):
        assert classify_entity_type("SUV") == EntityType.UNKNOWN
        assert classify_entity_type("car") == EntityType.UNKNOWN
        assert classify_entity_type("轿车") == EntityType.UNKNOWN

    def test_classifies_feature_descriptors_as_unknown(self):
        assert classify_entity_type("安全性") == EntityType.UNKNOWN
        assert classify_entity_type("性价比") == EntityType.UNKNOWN
        assert classify_entity_type("配置丰富") == EntityType.UNKNOWN
