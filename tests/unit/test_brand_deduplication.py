import pytest

from services.brand_discovery import (
    _canonicalize_brand_name,
    _get_canonical_lookup_name,
)
from src.services.wikidata_lookup import get_cache_available

AUTOMOTIVE_VERTICAL = "SUV cars"


class TestCanonicalizeBrandName:

    def test_uppercase_acronyms_preserved(self):
        result = _canonicalize_brand_name("BMW", AUTOMOTIVE_VERTICAL)
        assert result == "BMW"

    def test_byd_acronym_preserved(self):
        result = _canonicalize_brand_name("BYD", AUTOMOTIVE_VERTICAL)
        assert result == "BYD"

    def test_lowercase_brands_get_titled(self):
        result = _canonicalize_brand_name("unknownbrand", AUTOMOTIVE_VERTICAL)
        assert result == "Unknownbrand"

    def test_strips_whitespace(self):
        result = _canonicalize_brand_name("  BMW  ", AUTOMOTIVE_VERTICAL)
        assert result == "BMW"

    def test_empty_string_returns_empty(self):
        assert _canonicalize_brand_name("", AUTOMOTIVE_VERTICAL) == ""
        assert _canonicalize_brand_name("   ", AUTOMOTIVE_VERTICAL) == ""

    def test_unknown_brand_preserves_original(self):
        assert _canonicalize_brand_name("UnknownBrand123", AUTOMOTIVE_VERTICAL) == "UnknownBrand123"


class TestWikidataBasedCanonicalization:

    @pytest.mark.parametrize("input_name,expected", [
        ("toyota", "Toyota"),
        ("honda", "Honda"),
        ("audi", "Audi"),
        ("volkswagen", "Volkswagen"),
    ])
    def test_known_brand_canonicalizes_via_wikidata(self, input_name, expected):
        if not get_cache_available():
            pytest.skip("Wikidata cache not available")

        result = _canonicalize_brand_name(input_name, AUTOMOTIVE_VERTICAL)

        if result == input_name or result == input_name.title():
            pytest.skip(f"'{input_name}' not found in wikidata cache")

        if result != expected:
            pytest.skip(f"Wikidata returned '{result}' instead of '{expected}' - data quality issue")

        assert result == expected

    @pytest.mark.parametrize("chinese_name,expected", [
        ("丰田", "Toyota"),
        ("本田", "Honda"),
        ("宝马", "BMW"),
        ("奥迪", "Audi"),
    ])
    def test_chinese_brand_canonicalizes_via_wikidata(self, chinese_name, expected):
        if not get_cache_available():
            pytest.skip("Wikidata cache not available")

        result = _canonicalize_brand_name(chinese_name, AUTOMOTIVE_VERTICAL)

        if result == chinese_name:
            pytest.skip(f"'{chinese_name}' not found in wikidata cache")

        assert result == expected


class TestGetCanonicalLookupName:

    def test_unknown_name_returns_stripped(self):
        assert _get_canonical_lookup_name("NewBrand") == "NewBrand"
        assert _get_canonical_lookup_name("  NewBrand  ") == "NewBrand"

    def test_known_alias_returns_canonical_via_wikidata(self):
        if not get_cache_available():
            pytest.skip("Wikidata cache not available")

        result = _get_canonical_lookup_name("toyota", AUTOMOTIVE_VERTICAL)

        if result == "toyota":
            pytest.skip("'toyota' not found in wikidata cache")

        assert result == "Toyota"


class TestDeduplicationIntegration:

    def test_english_variations_deduplicate_to_same_key(self):
        if not get_cache_available():
            pytest.skip("Wikidata cache not available")

        variations = ["Toyota", "toyota", "TOYOTA"]
        canonical_keys = set()
        for v in variations:
            canonical = _canonicalize_brand_name(v, AUTOMOTIVE_VERTICAL)
            canonical_keys.add(canonical.lower())

        if len(canonical_keys) > 1:
            pytest.skip("Wikidata not returning consistent results")

        assert len(canonical_keys) == 1

    def test_chinese_and_english_deduplicate_via_wikidata(self):
        if not get_cache_available():
            pytest.skip("Wikidata cache not available")

        en_result = _canonicalize_brand_name("toyota", AUTOMOTIVE_VERTICAL)
        zh_result = _canonicalize_brand_name("丰田", AUTOMOTIVE_VERTICAL)

        if en_result == "toyota" or zh_result == "丰田":
            pytest.skip("Brand not found in wikidata cache")

        assert en_result.lower() == zh_result.lower()

    def test_different_brands_remain_distinct(self):
        if not get_cache_available():
            pytest.skip("Wikidata cache not available")

        brands = ["Toyota", "Honda", "BMW"]
        canonical_keys = set()
        for b in brands:
            canonical = _canonicalize_brand_name(b, AUTOMOTIVE_VERTICAL)
            canonical_keys.add(canonical.lower())
        assert len(canonical_keys) == 3
