import pytest
from unittest.mock import MagicMock, patch

from services.brand_discovery import (
    _canonicalize_brand_name,
    _get_canonical_lookup_name,
    BRAND_ALIAS_MAP,
)


class TestCanonicalizeBrandName:

    def test_vw_canonicalizes_to_volkswagen(self):
        assert _canonicalize_brand_name("VW") == "Volkswagen"
        assert _canonicalize_brand_name("vw") == "Volkswagen"
        assert _canonicalize_brand_name("Vw") == "Volkswagen"

    def test_chinese_brand_canonicalizes(self):
        assert _canonicalize_brand_name("大众") == "Volkswagen"
        assert _canonicalize_brand_name("丰田") == "Toyota"
        assert _canonicalize_brand_name("本田") == "Honda"
        assert _canonicalize_brand_name("比亚迪") == "BYD"
        assert _canonicalize_brand_name("特斯拉") == "Tesla"

    def test_english_brand_canonicalizes(self):
        assert _canonicalize_brand_name("toyota") == "Toyota"
        assert _canonicalize_brand_name("TOYOTA") == "Toyota"
        assert _canonicalize_brand_name("Tesla") == "Tesla"

    def test_unknown_brand_preserves_original(self):
        assert _canonicalize_brand_name("UnknownBrand") == "UnknownBrand"
        assert _canonicalize_brand_name("新品牌") == "新品牌"

    def test_uppercase_acronyms_preserved(self):
        assert _canonicalize_brand_name("BMW") == "BMW"
        assert _canonicalize_brand_name("BYD") == "BYD"
        assert _canonicalize_brand_name("NIO") == "NIO"

    def test_lowercase_brands_get_titled(self):
        result = _canonicalize_brand_name("unknownbrand")
        assert result == "Unknownbrand"

    def test_strips_whitespace(self):
        assert _canonicalize_brand_name("  VW  ") == "Volkswagen"
        assert _canonicalize_brand_name(" Toyota ") == "Toyota"

    def test_empty_string_returns_empty(self):
        assert _canonicalize_brand_name("") == ""
        assert _canonicalize_brand_name("   ") == ""


class TestGetCanonicalLookupName:

    def test_known_alias_returns_canonical(self):
        assert _get_canonical_lookup_name("vw") == "Volkswagen"
        assert _get_canonical_lookup_name("大众") == "Volkswagen"

    def test_unknown_name_returns_stripped(self):
        assert _get_canonical_lookup_name("NewBrand") == "NewBrand"
        assert _get_canonical_lookup_name("  NewBrand  ") == "NewBrand"


class TestBrandAliasMap:

    def test_volkswagen_aliases_present(self):
        assert "vw" in BRAND_ALIAS_MAP
        assert "volkswagen" in BRAND_ALIAS_MAP
        assert "大众" in BRAND_ALIAS_MAP
        assert all(v == "Volkswagen" for k, v in BRAND_ALIAS_MAP.items()
                   if k in ["vw", "volkswagen", "大众"])

    def test_major_brands_have_chinese_aliases(self):
        chinese_brands = {
            "丰田": "Toyota",
            "本田": "Honda",
            "宝马": "BMW",
            "奔驰": "Mercedes-Benz",
            "奥迪": "Audi",
        }
        for chinese, english in chinese_brands.items():
            assert chinese in BRAND_ALIAS_MAP
            assert BRAND_ALIAS_MAP[chinese] == english

    def test_tech_brands_included(self):
        tech_brands = ["apple", "samsung", "huawei", "xiaomi"]
        for brand in tech_brands:
            assert brand in BRAND_ALIAS_MAP

    def test_beauty_brands_included(self):
        beauty_brands = ["loreal", "lancome", "shiseido"]
        for brand in beauty_brands:
            assert brand in BRAND_ALIAS_MAP

    def test_home_appliance_brands_included(self):
        appliance_brands = ["dyson", "irobot", "ecovacs", "roborock"]
        for brand in appliance_brands:
            assert brand in BRAND_ALIAS_MAP


class TestDeduplicationIntegration:

    def test_vw_variations_deduplicate_to_same_key(self):
        variations = ["VW", "vw", "Vw", "volkswagen", "Volkswagen", "大众"]
        canonical_keys = set()
        for v in variations:
            canonical = _canonicalize_brand_name(v)
            canonical_keys.add(canonical.lower())
        assert len(canonical_keys) == 1
        assert "volkswagen" in canonical_keys

    def test_toyota_variations_deduplicate_to_same_key(self):
        variations = ["Toyota", "toyota", "TOYOTA", "丰田"]
        canonical_keys = set()
        for v in variations:
            canonical = _canonicalize_brand_name(v)
            canonical_keys.add(canonical.lower())
        assert len(canonical_keys) == 1
        assert "toyota" in canonical_keys

    def test_different_brands_remain_distinct(self):
        brands = ["Toyota", "Honda", "BMW"]
        canonical_keys = set()
        for b in brands:
            canonical = _canonicalize_brand_name(b)
            canonical_keys.add(canonical.lower())
        assert len(canonical_keys) == 3
