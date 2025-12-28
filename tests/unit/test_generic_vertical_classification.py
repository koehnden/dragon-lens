import pytest
from unittest.mock import patch, MagicMock
import json

from services.brand_recognition import (
    is_likely_brand,
    is_likely_product,
    _has_product_model_patterns,
    _has_product_suffix,
    _has_brand_patterns,
    _has_product_patterns,
    _calculate_brand_confidence,
    _calculate_product_confidence,
    extract_entities,
    ExtractionResult,
)


class TestPatternBasedBrandDetection:

    def test_proper_noun_brand_pattern(self):
        assert is_likely_brand("Acme") is True
        assert is_likely_brand("Globex") is True
        assert is_likely_brand("Initech") is True

    def test_uppercase_acronym_brand_pattern(self):
        assert is_likely_brand("ABC") is True
        assert is_likely_brand("XYZ") is True
        assert is_likely_brand("ACME") is True

    def test_chinese_brand_pattern(self):
        assert is_likely_brand("新品牌") is True
        assert is_likely_brand("未知公司") is True
        assert is_likely_brand("测试") is True

    def test_product_patterns_not_brands(self):
        assert is_likely_brand("X100") is False
        assert is_likely_brand("Model5") is False
        assert is_likely_brand("产品Pro") is False

    def test_generic_terms_not_brands(self):
        assert is_likely_brand("suv") is False
        assert is_likely_brand("sedan") is False
        assert is_likely_brand("hybrid") is False


class TestPatternBasedProductDetection:

    def test_alphanumeric_product_pattern(self):
        assert is_likely_product("X100") is True
        assert is_likely_product("A5") is True
        assert is_likely_product("Pro2000") is True

    def test_model_prefix_product_pattern(self):
        assert is_likely_product("Model X") is True
        assert is_likely_product("Model 5") is True
        assert is_likely_product("ID.4") is True

    def test_product_suffix_pattern(self):
        assert is_likely_product("星际Plus") is True
        assert is_likely_product("新款Pro") is True
        assert is_likely_product("旗舰Max") is True
        assert is_likely_product("电动版EV") is True

    def test_brand_patterns_not_products(self):
        assert is_likely_product("Acme") is False
        assert is_likely_product("新品牌") is False

    def test_generic_terms_not_products(self):
        assert is_likely_product("suv") is False
        assert is_likely_product("electric") is False


class TestProductModelPatterns:

    def test_letter_number_combo(self):
        assert _has_product_model_patterns("X5") is True
        assert _has_product_model_patterns("A4") is True
        assert _has_product_model_patterns("Q7") is True
        assert _has_product_model_patterns("S300") is True

    def test_number_letter_combo(self):
        assert _has_product_model_patterns("3Series") is True
        assert _has_product_model_patterns("5Pro") is True

    def test_model_prefix(self):
        assert _has_product_model_patterns("Model Y") is True
        assert _has_product_model_patterns("model 3") is True

    def test_id_prefix(self):
        assert _has_product_model_patterns("ID.4") is True
        assert _has_product_model_patterns("ID.6") is True

    def test_no_pattern(self):
        assert _has_product_model_patterns("Acme") is False
        assert _has_product_model_patterns("新品牌") is False


class TestProductSuffixPatterns:

    def test_plus_suffix(self):
        assert _has_product_suffix("宋PLUS") is True
        assert _has_product_suffix("元Plus") is True
        assert _has_product_suffix("产品 Plus") is True

    def test_pro_suffix(self):
        assert _has_product_suffix("iPhone Pro") is True
        assert _has_product_suffix("旗舰PRO") is True

    def test_max_suffix(self):
        assert _has_product_suffix("产品Max") is True
        assert _has_product_suffix("新款 MAX") is True

    def test_ev_suffix(self):
        assert _has_product_suffix("汉EV") is True
        assert _has_product_suffix("新车ev") is True

    def test_dm_suffix(self):
        assert _has_product_suffix("唐DM") is True
        assert _has_product_suffix("宋DM-i") is True
        assert _has_product_suffix("元DM-p") is True

    def test_no_suffix(self):
        assert _has_product_suffix("Toyota") is False
        assert _has_product_suffix("新品牌") is False


class TestGenericVerticalConfidence:

    def test_unknown_brand_gets_medium_confidence(self):
        confidence = _calculate_brand_confidence("UnknownBrand", "unknownbrand", "pet food")
        assert 0.5 <= confidence <= 0.8

    def test_unknown_product_with_pattern_gets_high_confidence(self):
        confidence = _calculate_product_confidence("PetFood Pro", "petfood pro", "pet food")
        assert confidence >= 0.7

    def test_alphanumeric_product_gets_high_confidence(self):
        confidence = _calculate_product_confidence("PF2000", "pf2000", "pet food")
        assert confidence >= 0.8

    def test_generic_term_gets_low_confidence(self):
        brand_conf = _calculate_brand_confidence("hybrid", "hybrid", "cars")
        product_conf = _calculate_product_confidence("hybrid", "hybrid", "cars")
        assert brand_conf <= 0.3
        assert product_conf <= 0.3


class TestGenericVerticalExtraction:

    def create_mock_ollama(self, brands: list, products: list):
        mock_service = MagicMock()
        mock_service.ner_model = "qwen2.5:7b"

        response = json.dumps({"brands": brands, "products": products})

        async def mock_call(*args, **kwargs):
            return response

        mock_service._call_ollama = mock_call
        return mock_service

    def test_pet_food_vertical_extraction(self):
        text = """2025年猫粮推荐：
        1. 皇家猫粮 - 专业配方，营养均衡
        2. 渴望六种鱼 - 高蛋白，适合活泼猫咪
        3. 爱肯拿草原盛宴 - 无谷配方"""

        mock_ollama = self.create_mock_ollama(
            brands=["皇家", "渴望", "爱肯拿"],
            products=["猫粮", "六种鱼", "草原盛宴"]
        )

        with patch("services.ollama.OllamaService", return_value=mock_ollama):
            result = extract_entities(
                text=text,
                primary_brand="",
                aliases={},
                vertical="pet food cat food",
                vertical_description="Cat food recommendations"
            )

        assert isinstance(result, ExtractionResult)
        assert len(result.brands) >= 1 or len(result.products) >= 1

    def test_furniture_vertical_extraction(self):
        text = """办公椅推荐：
        1. 西昊M18 - 人体工学设计
        2. 永艺蝴蝶椅 - 高性价比
        3. 赫曼米勒Aeron - 顶级办公椅"""

        mock_ollama = self.create_mock_ollama(
            brands=["西昊", "永艺", "赫曼米勒"],
            products=["M18", "蝴蝶椅", "Aeron"]
        )

        with patch("services.ollama.OllamaService", return_value=mock_ollama):
            result = extract_entities(
                text=text,
                primary_brand="",
                aliases={},
                vertical="office furniture chairs",
                vertical_description="Office chair recommendations"
            )

        assert isinstance(result, ExtractionResult)
        brand_names = set(result.brands.keys())
        product_names = set(result.products.keys())

        assert "M18" not in brand_names or "M18" in product_names

    def test_kitchen_appliance_vertical_extraction(self):
        text = """咖啡机推荐：
        1. 德龙EC680 - 半自动意式咖啡机
        2. 飞利浦EP3146 - 全自动咖啡机
        3. 雀巢Nespresso - 胶囊咖啡机"""

        mock_ollama = self.create_mock_ollama(
            brands=["德龙", "飞利浦", "雀巢"],
            products=["EC680", "EP3146", "Nespresso"]
        )

        with patch("services.ollama.OllamaService", return_value=mock_ollama):
            result = extract_entities(
                text=text,
                primary_brand="",
                aliases={},
                vertical="kitchen appliances coffee machines",
                vertical_description="Coffee machine recommendations"
            )

        assert isinstance(result, ExtractionResult)
        product_names = set(result.products.keys())

        ec680_in_products = any("EC680" in p for p in product_names)
        ep3146_in_products = any("EP3146" in p for p in product_names)
        assert ec680_in_products or ep3146_in_products


class TestBrandPatternDetection:

    def test_company_suffix_detection(self):
        assert _has_brand_patterns("Acme Inc") is True
        assert _has_brand_patterns("Globex Corp") is True
        assert _has_brand_patterns("Test Ltd") is True
        assert _has_brand_patterns("新品牌公司") is True
        assert _has_brand_patterns("测试集团") is True

    def test_proper_noun_detection(self):
        assert _has_brand_patterns("Acme") is True
        assert _has_brand_patterns("Globex") is True

    def test_product_patterns_excluded(self):
        assert _has_brand_patterns("X100") is False
        assert _has_brand_patterns("Model5") is False
        assert _has_brand_patterns("产品Pro") is False


class TestProductPatternDetection:

    def test_model_patterns_detected(self):
        assert _has_product_patterns("X100") is True
        assert _has_product_patterns("A5") is True
        assert _has_product_patterns("Model Y") is True

    def test_suffix_patterns_detected(self):
        assert _has_product_patterns("旗舰Pro") is True
        assert _has_product_patterns("新款Plus") is True
        assert _has_product_patterns("电动EV") is True

    def test_brand_patterns_not_detected(self):
        assert _has_product_patterns("Acme") is False
        assert _has_product_patterns("新品牌") is False
