import json
import pytest
from unittest.mock import MagicMock, patch

from src.constants.wikidata_industries import (
    PREDEFINED_INDUSTRIES,
    find_industry_by_keyword,
    get_all_industry_keys,
    get_industry_keywords,
)


class TestWikidataIndustries:
    def test_predefined_industries_has_required_fields(self):
        for key, config in PREDEFINED_INDUSTRIES.items():
            assert "wikidata_id" in config
            assert "name_en" in config
            assert "name_zh" in config
            assert "keywords" in config
            assert config["wikidata_id"].startswith("Q")

    def test_find_industry_by_keyword_automotive(self):
        assert find_industry_by_keyword("SUV cars") == "automotive"
        assert find_industry_by_keyword("auto industry") == "automotive"
        assert find_industry_by_keyword("vehicle market") == "automotive"

    def test_find_industry_by_keyword_electronics(self):
        assert find_industry_by_keyword("smartphone market") == "consumer_electronics"
        assert find_industry_by_keyword("laptop review") == "consumer_electronics"

    def test_find_industry_by_keyword_cosmetics(self):
        assert find_industry_by_keyword("cosmetics industry") == "cosmetics"
        assert find_industry_by_keyword("beauty brands") == "cosmetics"
        assert find_industry_by_keyword("makeup products") == "cosmetics"

    def test_find_industry_by_keyword_unknown(self):
        assert find_industry_by_keyword("random unknown") is None

    def test_get_all_industry_keys(self):
        keys = get_all_industry_keys()
        assert "automotive" in keys
        assert "consumer_electronics" in keys
        assert "cosmetics" in keys
        assert len(keys) == len(PREDEFINED_INDUSTRIES)

    def test_get_industry_keywords(self):
        keywords = get_industry_keywords("automotive")
        assert "car" in keywords
        assert "suv" in keywords

    def test_get_industry_keywords_unknown(self):
        keywords = get_industry_keywords("nonexistent")
        assert keywords == []


class TestWikidataLookup:
    @patch("src.services.wikidata_lookup.get_wikidata_session")
    def test_get_cache_available_returns_false_when_empty(self, mock_session):
        from src.services.wikidata_lookup import get_cache_available

        mock_query = MagicMock()
        mock_query.limit.return_value.count.return_value = 0
        mock_session.return_value.query.return_value = mock_query
        mock_session.return_value.close = MagicMock()

        result = get_cache_available()
        assert result is False

    @patch("src.services.wikidata_lookup.get_wikidata_session")
    def test_get_cache_available_returns_true_when_has_data(self, mock_session):
        from src.services.wikidata_lookup import get_cache_available

        mock_query = MagicMock()
        mock_query.limit.return_value.count.return_value = 10
        mock_session.return_value.query.return_value = mock_query
        mock_session.return_value.close = MagicMock()

        result = get_cache_available()
        assert result is True

    @patch("src.services.wikidata_lookup.get_wikidata_session")
    def test_get_entities_for_vertical_returns_empty_when_no_match(self, mock_session):
        from src.services.wikidata_lookup import get_entities_for_vertical

        result = get_entities_for_vertical("unknown vertical")
        assert result == {"brands": [], "products": []}

    def test_is_known_brand_without_cache(self):
        from src.services.wikidata_lookup import is_known_brand

        result = is_known_brand("Toyota", "automotive")
        assert result is False

    def test_is_known_product_without_cache(self):
        from src.services.wikidata_lookup import is_known_product

        result = is_known_product("RAV4", "automotive")
        assert result is False


class TestWikidataSparql:
    def test_parse_brand_results(self):
        from src.services.wikidata_sparql import _parse_brand_results

        mock_results = [
            {
                "brand": {"value": "http://www.wikidata.org/entity/Q1234"},
                "brandLabel": {"value": "Toyota"},
                "brandLabelZh": {"value": "丰田"},
                "aliasesEn": {"value": "Toyota Motor|TM"},
                "aliasesZh": {"value": "丰田汽车"},
            }
        ]

        brands = _parse_brand_results(mock_results)
        assert len(brands) == 1
        assert brands[0]["wikidata_id"] == "Q1234"
        assert brands[0]["name_en"] == "Toyota"
        assert brands[0]["name_zh"] == "丰田"
        assert "Toyota Motor" in brands[0]["aliases_en"]
        assert brands[0]["entity_type"] == "brand"

    def test_parse_product_results(self):
        from src.services.wikidata_sparql import _parse_product_results

        mock_results = [
            {
                "model": {"value": "http://www.wikidata.org/entity/Q5678"},
                "modelLabel": {"value": "RAV4"},
                "modelLabelZh": {"value": "荣放"},
                "manufacturer": {"value": "http://www.wikidata.org/entity/Q1234"},
            }
        ]

        products = _parse_product_results(mock_results)
        assert len(products) == 1
        assert products[0]["wikidata_id"] == "Q5678"
        assert products[0]["name_en"] == "RAV4"
        assert products[0]["parent_brand_wikidata_id"] == "Q1234"
        assert products[0]["entity_type"] == "product"


class TestWikidataCacheModels:
    def test_wikidata_industry_model(self):
        from src.models.wikidata_cache import WikidataIndustry

        industry = WikidataIndustry(
            wikidata_id="Q1420",
            name_en="Automotive",
            name_zh="汽车",
            keywords="car,suv,auto",
        )

        assert industry.wikidata_id == "Q1420"
        assert industry.name_en == "Automotive"

    def test_wikidata_entity_model(self):
        from src.models.wikidata_cache import WikidataEntity

        entity = WikidataEntity(
            wikidata_id="Q1234",
            entity_type="brand",
            industry_id=1,
            name_en="Toyota",
            name_zh="丰田",
            aliases_en='["Toyota Motor"]',
            aliases_zh='["丰田汽车"]',
        )

        assert entity.wikidata_id == "Q1234"
        assert entity.entity_type == "brand"
        assert json.loads(entity.aliases_en) == ["Toyota Motor"]


class TestBrandRecognitionWikidataIntegration:
    @patch("src.services.brand_recognition.wikidata_cache_available")
    @patch("src.services.brand_recognition.wikidata_is_known_brand")
    def test_check_wikidata_brand_boosts_confidence(
        self, mock_is_known, mock_cache_available
    ):
        from src.services.brand_recognition import _check_wikidata_brand

        mock_cache_available.return_value = True
        mock_is_known.return_value = True

        result = _check_wikidata_brand("Toyota", "automotive")
        assert result is True

    @patch("src.services.brand_recognition.wikidata_cache_available")
    def test_check_wikidata_brand_returns_false_when_cache_unavailable(
        self, mock_cache_available
    ):
        from src.services.brand_recognition import _check_wikidata_brand

        mock_cache_available.return_value = False

        result = _check_wikidata_brand("Toyota", "automotive")
        assert result is False

    @patch("src.services.brand_recognition.wikidata_cache_available")
    @patch("src.services.brand_recognition.wikidata_is_known_product")
    def test_check_wikidata_product_boosts_confidence(
        self, mock_is_known, mock_cache_available
    ):
        from src.services.brand_recognition import _check_wikidata_product

        mock_cache_available.return_value = True
        mock_is_known.return_value = True

        result = _check_wikidata_product("RAV4", "automotive")
        assert result is True
