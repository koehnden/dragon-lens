import pytest
from unittest.mock import patch, MagicMock
import json

from services.brand_recognition import extract_entities, ExtractionResult


def create_mock_ollama(brands: list, products: list):
    mock_service = MagicMock()
    mock_service.ner_model = "qwen2.5:7b"

    response = json.dumps({"brands": brands, "products": products})

    async def mock_call(*args, **kwargs):
        return response

    mock_service._call_ollama = mock_call
    return mock_service


class TestExtractEntitiesAutomotiveVertical:

    def test_toyota_rav4_brand_product_separation(self):
        text = """丰田RAV4荣放是一款非常受欢迎的紧凑型SUV，它的混动版本油耗低，空间大。
        与本田CR-V相比，RAV4的后排空间略占优势。如果预算充足，可以考虑雷克萨斯NX。"""

        mock_ollama = create_mock_ollama(
            brands=["丰田", "本田", "雷克萨斯"],
            products=["RAV4荣放", "CR-V", "NX"]
        )

        with patch("services.ollama.OllamaService", return_value=mock_ollama):
            result = extract_entities(
                text=text,
                primary_brand="",
                aliases={},
                vertical="SUV cars automotive",
                vertical_description="Compact and mid-size SUV recommendations"
            )

        assert isinstance(result, ExtractionResult)

        brand_names = set(result.brands.keys())
        product_names = set(result.products.keys())

        expected_brands = {"丰田", "本田", "雷克萨斯"}

        brands_found = sum(1 for brand in expected_brands if brand in brand_names)
        assert brands_found >= 2, f"At least 2 brands should be extracted, got {brand_names}"

        product_like_found = [name for name in product_names
                             if "RAV4" in name or "CR-V" in name]
        assert len(product_like_found) >= 1, f"At least one product should be extracted, got {product_names}"

        assert "RAV4荣放" not in brand_names, "RAV4荣放 should be in products, not brands"
        assert "CR-V" not in brand_names, "CR-V should be in products, not brands"

    def test_byd_models_brand_product_separation(self):
        text = """比亚迪在新能源SUV市场表现出色。唐DM-i是插电混动的标杆，
        宋PLUS DM-i则主打性价比。元PLUS是纯电小型SUV的热门选择。
        与特斯拉Model Y相比，比亚迪的售后网络更完善。"""

        mock_ollama = create_mock_ollama(
            brands=["比亚迪", "特斯拉"],
            products=["唐DM-i", "宋PLUS DM-i", "元PLUS", "Model Y"]
        )

        with patch("services.ollama.OllamaService", return_value=mock_ollama):
            result = extract_entities(
                text=text,
                primary_brand="",
                aliases={},
                vertical="electric vehicles SUV",
                vertical_description="New energy SUV market analysis"
            )

        assert isinstance(result, ExtractionResult)

        brand_names = set(result.brands.keys())
        product_names = set(result.products.keys())

        brands_in_result = [name for name in brand_names
                           if name in {"比亚迪", "特斯拉"}]
        products_in_result = [name for name in product_names
                             if any(p in name for p in ["唐", "宋", "元", "Model"])]

        assert len(brands_in_result) >= 1, "At least one brand should be extracted"
        assert len(products_in_result) >= 1, "At least one product should be extracted"

        assert "唐DM-i" not in brand_names, "唐DM-i is a product, not a brand"
        assert "Model Y" not in brand_names, "Model Y is a product, not a brand"


class TestExtractEntitiesBeautyVertical:

    def test_skincare_brand_product_separation(self):
        text = """2025年抗老精华推荐：
        1. 雅诗兰黛小棕瓶 - 经典维稳修护
        2. 兰蔻小黑瓶 - 肌底液促进吸收
        3. 资生堂红腰子 - 强韧肌底，适合敏感肌
        4. 欧莱雅黑精华 - 性价比之选"""

        mock_ollama = create_mock_ollama(
            brands=["雅诗兰黛", "兰蔻", "资生堂", "欧莱雅"],
            products=["小棕瓶", "小黑瓶", "红腰子", "黑精华"]
        )

        with patch("services.ollama.OllamaService", return_value=mock_ollama):
            result = extract_entities(
                text=text,
                primary_brand="",
                aliases={},
                vertical="beauty cosmetics skincare",
                vertical_description="Anti-aging skincare product recommendations"
            )

        assert isinstance(result, ExtractionResult)

        brand_names = set(result.brands.keys())
        product_names = set(result.products.keys())

        expected_brands = {"雅诗兰黛", "兰蔻", "资生堂", "欧莱雅"}

        brands_found = sum(1 for brand in expected_brands if brand in brand_names)
        assert brands_found >= 3, f"At least 3 brands should be extracted, got {brand_names}"

        product_names_set = {"小棕瓶", "小黑瓶", "红腰子", "黑精华"}
        products_misclassified_as_brands = product_names_set.intersection(brand_names)
        assert len(products_misclassified_as_brands) == 0, \
            f"Products should not be in brand set: {products_misclassified_as_brands}"


class TestExtractEntitiesSmartphoneVertical:

    def test_phone_brand_model_separation(self):
        text = """2025年性价比手机推荐：
        小米14是旗舰级配置，搭载骁龙8 Gen 3处理器。
        OPPO Find X7则主打影像能力，与华为Mate 60 Pro竞争。
        三星Galaxy S24 Ultra是安卓机皇，但价格较高。
        苹果iPhone 15 Pro Max依然是iOS用户的首选。"""

        mock_ollama = create_mock_ollama(
            brands=["小米", "OPPO", "华为", "三星", "苹果"],
            products=["小米14", "Find X7", "Mate 60 Pro", "Galaxy S24 Ultra", "iPhone 15 Pro Max"]
        )

        with patch("services.ollama.OllamaService", return_value=mock_ollama):
            result = extract_entities(
                text=text,
                primary_brand="",
                aliases={},
                vertical="smartphones mobile phones",
                vertical_description="High-end smartphone comparison 2025"
            )

        assert isinstance(result, ExtractionResult)

        brand_names = set(result.brands.keys())
        product_names = set(result.products.keys())

        expected_brands = {"小米", "OPPO", "华为", "三星", "苹果"}
        product_indicators = ["14", "X7", "Mate", "Galaxy", "iPhone"]

        brands_found = sum(1 for brand in expected_brands if brand in brand_names)
        assert brands_found >= 3, f"At least 3 brands should be extracted, found {brands_found}"

        products_found = [name for name in product_names
                         if any(ind in name for ind in product_indicators)]
        assert len(products_found) >= 2, f"At least 2 products should be extracted, got {product_names}"

        assert "Galaxy S24 Ultra" not in brand_names, "Galaxy S24 Ultra is a product, not a brand"
        assert "iPhone 15 Pro Max" not in brand_names, "iPhone 15 Pro Max is a product, not a brand"


class TestExtractEntitiesHomeAppliancesVertical:

    def test_vacuum_cleaner_brand_product_separation(self):
        text = """2025年扫地机器人推荐：
        科沃斯X2 Pro是高端旗舰，避障能力强。
        石头T8 Pro主打性价比，清洁效果不输戴森V15。
        追觅S20 Pro是新锐选手，配置豪华。
        iRobot Roomba j9+是进口品牌代表，但价格偏高。"""

        mock_ollama = create_mock_ollama(
            brands=["科沃斯", "石头", "戴森", "追觅", "iRobot"],
            products=["X2 Pro", "T8 Pro", "V15", "S20 Pro", "Roomba j9+"]
        )

        with patch("services.ollama.OllamaService", return_value=mock_ollama):
            result = extract_entities(
                text=text,
                primary_brand="",
                aliases={},
                vertical="home appliances robot vacuum",
                vertical_description="Robot vacuum cleaner recommendations"
            )

        assert isinstance(result, ExtractionResult)

        brand_names = set(result.brands.keys())
        product_names = set(result.products.keys())

        expected_brands = {"科沃斯", "石头", "戴森", "追觅", "iRobot"}

        brands_found = [name for name in brand_names if name in expected_brands]
        assert len(brands_found) >= 3, f"At least 3 brands should be extracted, got {brands_found}"

        product_model_codes = {"X2 Pro", "T8 Pro", "V15", "S20 Pro", "Roomba j9+"}
        for product in product_model_codes:
            assert product not in brand_names, f"'{product}' is a product model, should not be in brands"


class TestExtractEntitiesReturnType:

    def test_extract_entities_returns_structured_result(self):
        text = """丰田RAV4荣放是热门SUV，本田CR-V也很受欢迎。"""

        mock_ollama = create_mock_ollama(
            brands=["丰田", "本田"],
            products=["RAV4荣放", "CR-V"]
        )

        with patch("services.ollama.OllamaService", return_value=mock_ollama):
            result = extract_entities(
                text=text,
                primary_brand="",
                aliases={},
                vertical="SUV automotive",
                vertical_description=""
            )

        assert hasattr(result, 'brands'), "Result should have 'brands' attribute"
        assert hasattr(result, 'products'), "Result should have 'products' attribute"

        assert "丰田" in result.brands, "Toyota should be in brands"
        assert "本田" in result.brands, "Honda should be in brands"

        rav4_found = any("RAV4" in p for p in result.products)
        crv_found = any("CR-V" in p for p in result.products)
        assert rav4_found, f"RAV4 should be in products, got {result.products}"
        assert crv_found, f"CR-V should be in products, got {result.products}"

        assert "RAV4荣放" not in result.brands, "RAV4荣放 should NOT be in brands"
        assert "CR-V" not in result.brands, "CR-V should NOT be in brands"


class TestExtractEntitiesMixedBrandProductPatterns:

    def test_german_car_alphanumeric_models(self):
        text = """德系豪华SUV对比：
        宝马X5是运动型SUV的标杆，操控一流。
        奔驰GLE则更注重舒适性，内饰豪华。
        奥迪Q7空间最大，适合家用。保时捷卡宴是性能与实用的结合。
        大众途锐是性价比之选，与奥迪Q7同平台。"""

        mock_ollama = create_mock_ollama(
            brands=["宝马", "奔驰", "奥迪", "保时捷", "大众"],
            products=["X5", "GLE", "Q7", "卡宴", "途锐"]
        )

        with patch("services.ollama.OllamaService", return_value=mock_ollama):
            result = extract_entities(
                text=text,
                primary_brand="",
                aliases={},
                vertical="luxury SUV automotive",
                vertical_description="German luxury SUV comparison"
            )

        assert isinstance(result, ExtractionResult)

        brand_names = set(result.brands.keys())
        product_names = set(result.products.keys())

        expected_brands = {"宝马", "奔驰", "奥迪", "保时捷", "大众"}
        alphanumeric_products = {"X5", "GLE", "Q7"}

        brands_found = sum(1 for brand in expected_brands if brand in brand_names)
        assert brands_found >= 4, f"At least 4 brands should be extracted, got {brand_names}"

        for product in alphanumeric_products:
            assert product not in brand_names, \
                f"'{product}' is a product model code, should not be in brands"
