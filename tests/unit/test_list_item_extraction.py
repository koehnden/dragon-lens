"""Test first-entity-per-item extraction from list responses."""

import pytest

from services.brand_recognition import extract_entities


class TestListItemFirstEntityExtraction:

    def test_extracts_only_first_brand_per_list_item_suv(self):
        response = """
        1. Honda CRV is a great SUV choice. Another great option from Honda is the Honda HR-V similar to Toyota RAV4.
        2. VW Tiguan is spacious.
        """
        entities = extract_entities(response, "Honda", {"zh": ["本田"], "en": ["Honda"]})
        extracted_names = set(entities.keys())

        assert any("honda" in name.lower() for name in extracted_names)
        assert any("crv" in name.lower() or "cr-v" in name.lower() for name in extracted_names)
        assert any("vw" in name.lower() or "tiguan" in name.lower() for name in extracted_names)
        assert not any("rav4" in name.lower() for name in extracted_names)
        assert not any("hr-v" in name.lower() or "hrv" in name.lower() for name in extracted_names)

    def test_extracts_only_first_brand_per_list_item_smartphones(self):
        response = """
        - iPhone 15 Pro offers great performance, similar to Samsung Galaxy S24 and Google Pixel 8
        - Samsung Galaxy S24 Ultra has amazing display, comparable to iPhone 15 Pro Max
        """
        entities = extract_entities(response, "Apple", {"zh": ["苹果"], "en": ["iPhone", "Apple"]})
        extracted_names = set(entities.keys())

        assert any("iphone" in name.lower() or "pro" in name.lower() for name in extracted_names)
        assert any("samsung" in name.lower() or "s24" in name.lower() for name in extracted_names)
        assert not any("pixel" in name.lower() for name in extracted_names)
        assert not any("google" in name.lower() for name in extracted_names)

    def test_extracts_only_first_brand_per_list_item_pet_food(self):
        response = """
        1. Royal Canin is the top choice for cat food, better than Hill Science Diet and Purina
        2. Hill Science Diet is recommended by vets, similar quality to Blue Buffalo
        3. Purina Pro Plan offers good value
        """
        entities = extract_entities(response, "Royal Canin", {"zh": ["皇家"], "en": ["Royal Canin"]})
        extracted_names = set(entities.keys())

        assert any("royal" in name.lower() for name in extracted_names)
        assert any("hill" in name.lower() for name in extracted_names)
        assert any("purina" in name.lower() for name in extracted_names)
        assert not any("buffalo" in name.lower() for name in extracted_names)

    def test_extracts_only_first_brand_per_list_item_skincare(self):
        response = """
        * Loreal Paris offers affordable skincare, competing with Olay and Neutrogena
        * Estee Lauder is premium quality, similar to Lancome and Clinique
        * The Ordinary provides budget options
        """
        entities = extract_entities(response, "Loreal", {"zh": ["欧莱雅"], "en": ["Loreal", "L'Oreal"]})
        extracted_names = set(entities.keys())

        assert any("loreal" in name.lower() or "l'oreal" in name.lower() for name in extracted_names)
        assert any("estee" in name.lower() or "lauder" in name.lower() for name in extracted_names)
        assert any("ordinary" in name.lower() for name in extracted_names)
        assert not any("olay" in name.lower() for name in extracted_names)
        assert not any("neutrogena" in name.lower() for name in extracted_names)
        assert not any("lancome" in name.lower() for name in extracted_names)
        assert not any("clinique" in name.lower() for name in extracted_names)

    def test_extracts_only_first_brand_per_list_item_chinese_suv(self):
        response = """
        1、比亚迪宋PLUS是首选，比理想L7和蔚来ES6更实惠
        2、大众途观L性价比高，和丰田RAV4竞争
        3、理想L7空间大
        """
        entities = extract_entities(response, "比亚迪", {"zh": ["BYD"], "en": ["BYD"]})
        extracted_names = set(entities.keys())

        assert any("比亚迪" in name or "宋" in name for name in extracted_names)
        assert any("大众" in name or "途观" in name for name in extracted_names)
        assert any("理想" in name or "l7" in name.lower() for name in extracted_names)
        assert not any("蔚来" in name for name in extracted_names)
        assert not any("es6" in name.lower() for name in extracted_names)
        assert not any("rav4" in name.lower() for name in extracted_names)

    def test_extracts_only_first_product_per_list_item_laptops(self):
        response = """
        1. MacBook Pro 14 is excellent for professionals, outperforming Dell XPS 15 and ThinkPad X1
        2. Dell XPS 13 offers great portability, similar to MacBook Air and Surface Laptop
        3. ThinkPad X1 Carbon is best for business
        """
        entities = extract_entities(response, "Apple", {"zh": ["苹果"], "en": ["MacBook", "Apple"]})
        extracted_names = set(entities.keys())

        assert any("macbook" in name.lower() and "pro" in name.lower() for name in extracted_names)
        assert any("dell" in name.lower() or "xps" in name.lower() for name in extracted_names)
        assert any("thinkpad" in name.lower() for name in extracted_names)
        assert not any("surface" in name.lower() for name in extracted_names)
        assert not any("macbook air" in name.lower() for name in extracted_names)

    def test_extracts_first_entity_dash_list_home_appliances(self):
        response = """
        - Dyson V15 leads the market, ahead of Shark Navigator and Bissell CrossWave
        - Roomba i7 offers smart cleaning, competing with Ecovacs and Roborock
        - Shark Navigator is budget-friendly
        """
        entities = extract_entities(response, "Dyson", {"zh": ["戴森"], "en": ["Dyson"]})
        extracted_names = set(entities.keys())

        assert any("dyson" in name.lower() for name in extracted_names)
        assert any("roomba" in name.lower() for name in extracted_names)
        assert any("shark" in name.lower() for name in extracted_names)
        assert not any("bissell" in name.lower() for name in extracted_names)
        assert not any("ecovacs" in name.lower() for name in extracted_names)
        assert not any("roborock" in name.lower() for name in extracted_names)

    def test_normal_paragraph_extracts_all_brands(self):
        response = """
        Honda CRV is a great family SUV. Toyota RAV4 is known for reliability.
        VW Tiguan offers German engineering. Mazda CX-5 has sporty handling.
        """
        entities = extract_entities(response, "Honda", {"zh": ["本田"], "en": ["Honda"]})
        extracted_names = set(entities.keys())

        assert any("honda" in name.lower() for name in extracted_names)
        assert any("toyota" in name.lower() or "rav4" in name.lower() for name in extracted_names)
        assert any("vw" in name.lower() or "tiguan" in name.lower() for name in extracted_names)
        assert any("mazda" in name.lower() or "cx-5" in name.lower() for name in extracted_names)

    def test_extracts_first_entity_numbered_parenthesis_list(self):
        response = """
        1) Nike Air Max 90 is iconic, similar to Adidas Superstar and Puma Suede
        2) Adidas Ultraboost offers comfort, competing with Nike React and New Balance Fresh Foam
        """
        entities = extract_entities(response, "Nike", {"zh": ["耐克"], "en": ["Nike"]})
        extracted_names = set(entities.keys())

        assert any("nike" in name.lower() for name in extracted_names)
        assert any("max" in name.lower() for name in extracted_names)
        assert any("adidas" in name.lower() for name in extracted_names)
        assert not any("puma" in name.lower() for name in extracted_names)
        assert not any("newbalance" in name.lower() or "new balance" in name.lower() for name in extracted_names)

    def test_mixed_list_and_paragraph_extracts_appropriately(self):
        response = """
        Top SUV recommendations:
        1. Honda CRV - great choice, better than Toyota RAV4
        2. VW Tiguan - spacious interior
        """
        entities = extract_entities(response, "Honda", {"zh": ["本田"], "en": ["Honda"]})
        extracted_names = set(entities.keys())

        assert any("honda" in name.lower() for name in extracted_names)
        assert any("crv" in name.lower() or "cr-v" in name.lower() for name in extracted_names)
        assert any("vw" in name.lower() or "tiguan" in name.lower() for name in extracted_names)
        assert not any("rav4" in name.lower() for name in extracted_names)
