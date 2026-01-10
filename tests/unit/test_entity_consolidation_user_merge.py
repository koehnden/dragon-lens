from unittest.mock import patch

import pytest

from models import Brand
from services.entity_consolidation import (
    _find_matching_user_brand,
    _merge_groups_with_user_brands,
)


@pytest.fixture
def user_brand_vw():
    return Brand(
        id=1,
        vertical_id=1,
        display_name="VW",
        original_name="VW",
        translated_name=None,
        aliases={"zh": [], "en": []},
        is_user_input=True,
    )


@pytest.fixture
def user_brand_honda():
    return Brand(
        id=2,
        vertical_id=1,
        display_name="Honda",
        original_name="Honda",
        translated_name=None,
        aliases={"zh": [], "en": []},
        is_user_input=True,
    )


@pytest.fixture
def discovered_brand_volkswagen():
    return Brand(
        id=3,
        vertical_id=1,
        display_name="Volkswagen (大众)",
        original_name="大众",
        translated_name="Volkswagen",
        aliases={"zh": [], "en": []},
        is_user_input=False,
    )


@pytest.fixture
def discovered_brand_dongfeng_honda():
    return Brand(
        id=4,
        vertical_id=1,
        display_name="Honda (东风本田)",
        original_name="东风本田",
        translated_name="Dongfeng Honda",
        aliases={"zh": [], "en": []},
        is_user_input=False,
    )


class TestFindMatchingUserBrand:
    def test_direct_match_returns_user_brand(self, user_brand_vw):
        with patch("src.services.wikidata_lookup.lookup_brand", return_value=None):
            result = _find_matching_user_brand("VW", [user_brand_vw])
        assert result == "VW"

    def test_case_insensitive_match(self, user_brand_vw):
        with patch("src.services.wikidata_lookup.lookup_brand", return_value=None):
            result = _find_matching_user_brand("vw", [user_brand_vw])
        assert result == "VW"

    def test_qwen_key_contains_user_brand(self, user_brand_honda):
        with patch("src.services.wikidata_lookup.lookup_brand", return_value=None):
            result = _find_matching_user_brand("Dongfeng Honda", [user_brand_honda])
        assert result == "Honda"

    def test_qwen_key_volkswagen_maps_to_vw_via_wikidata(self, user_brand_vw):
        wikidata_result = {
            "name_en": "Volkswagen",
            "name_zh": "大众",
            "aliases_en": ["VW", "Volkswagen AG"],
            "aliases_zh": ["大众汽车"],
        }
        with patch("src.services.wikidata_lookup.lookup_brand", return_value=wikidata_result):
            result = _find_matching_user_brand("Volkswagen", [user_brand_vw])
        assert result == "VW"

    def test_no_match_returns_none(self, user_brand_vw):
        with patch("src.services.wikidata_lookup.lookup_brand", return_value=None):
            result = _find_matching_user_brand("Toyota", [user_brand_vw])
        assert result is None

    def test_qwen_key_substring_of_user_alias(self):
        user_brand = Brand(
            id=1,
            vertical_id=1,
            display_name="VW",
            original_name="VW",
            translated_name=None,
            aliases={"zh": ["大众汽车", "一汽-大众"], "en": ["Volkswagen"]},
            is_user_input=True,
        )
        with patch("src.services.wikidata_lookup.lookup_brand", return_value=None):
            result = _find_matching_user_brand("大众", [user_brand])
        assert result == "VW"


class TestMergeGroupsWithUserBrands:
    def test_group_already_has_user_brand_key(self, user_brand_vw):
        groups = {"VW": [user_brand_vw]}
        with patch("src.services.wikidata_lookup.lookup_brand", return_value=None):
            result = _merge_groups_with_user_brands(groups, [user_brand_vw])
        assert "VW" in result
        assert len(result["VW"]) == 1

    def test_merge_volkswagen_group_with_vw_via_wikidata(
        self, user_brand_vw, discovered_brand_volkswagen
    ):
        groups = {
            "VW": [user_brand_vw],
            "Volkswagen": [discovered_brand_volkswagen],
        }
        wikidata_result = {
            "name_en": "Volkswagen",
            "name_zh": "大众",
            "aliases_en": ["VW", "Volkswagen AG"],
            "aliases_zh": ["大众汽车"],
        }
        with patch("src.services.wikidata_lookup.lookup_brand", return_value=wikidata_result):
            result = _merge_groups_with_user_brands(groups, [user_brand_vw])
        assert "VW" in result
        assert "Volkswagen" not in result
        assert len(result["VW"]) == 2

    def test_merge_dongfeng_honda_with_honda(
        self, user_brand_honda, discovered_brand_dongfeng_honda
    ):
        groups = {
            "Honda": [user_brand_honda],
            "Dongfeng Honda": [discovered_brand_dongfeng_honda],
        }
        with patch("src.services.wikidata_lookup.lookup_brand", return_value=None):
            result = _merge_groups_with_user_brands(groups, [user_brand_honda])
        assert "Honda" in result
        assert "Dongfeng Honda" not in result
        assert len(result["Honda"]) == 2

    def test_unrelated_group_stays_separate(
        self, user_brand_vw, discovered_brand_dongfeng_honda
    ):
        groups = {
            "VW": [user_brand_vw],
            "Toyota": [discovered_brand_dongfeng_honda],
        }
        with patch("src.services.wikidata_lookup.lookup_brand", return_value=None):
            result = _merge_groups_with_user_brands(groups, [user_brand_vw])
        assert "VW" in result
        assert "Toyota" in result
        assert len(result) == 2
