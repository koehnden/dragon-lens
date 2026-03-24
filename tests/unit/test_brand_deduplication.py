import pytest

from services.brand_discovery import (
    _canonicalize_brand_name,
    _find_brand_by_alias,
    _get_canonical_lookup_name,
)
from models import Brand, Vertical


class TestCanonicalizeBrandName:

    def test_uppercase_acronyms_preserved(self):
        result = _canonicalize_brand_name("BMW")
        assert result == "BMW"

    def test_byd_acronym_preserved(self):
        result = _canonicalize_brand_name("BYD")
        assert result == "BYD"

    def test_lowercase_brands_get_titled(self):
        result = _canonicalize_brand_name("unknownbrand")
        assert result == "Unknownbrand"

    def test_strips_whitespace(self):
        result = _canonicalize_brand_name("  BMW  ")
        assert result == "BMW"

    def test_empty_string_returns_empty(self):
        assert _canonicalize_brand_name("") == ""
        assert _canonicalize_brand_name("   ") == ""

    def test_unknown_brand_preserves_original(self):
        assert _canonicalize_brand_name("UnknownBrand123") == "UnknownBrand123"


class TestGetCanonicalLookupName:

    def test_unknown_name_returns_stripped(self):
        assert _get_canonical_lookup_name("NewBrand") == "NewBrand"
        assert _get_canonical_lookup_name("  NewBrand  ") == "NewBrand"


class TestFindBrandByAlias:

    def test_finds_brand_by_english_alias(self, db_session):
        vertical = Vertical(name="SUV cars", description="SUV cars")
        db_session.add(vertical)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="VW",
            original_name="VW",
            aliases={"en": ["Volkswagen", "VW"], "zh": ["大众"]},
        )
        db_session.add(brand)
        db_session.flush()

        result = _find_brand_by_alias(db_session, vertical.id, "Volkswagen")

        assert result is not None
        assert result.id == brand.id

    def test_finds_brand_by_chinese_alias(self, db_session):
        vertical = Vertical(name="SUV cars", description="SUV cars")
        db_session.add(vertical)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="VW",
            original_name="VW",
            aliases={"en": ["Volkswagen"], "zh": ["大众", "福斯"]},
        )
        db_session.add(brand)
        db_session.flush()

        result = _find_brand_by_alias(db_session, vertical.id, "大众")

        assert result is not None
        assert result.id == brand.id

    def test_case_insensitive_alias_match(self, db_session):
        vertical = Vertical(name="SUV cars", description="SUV cars")
        db_session.add(vertical)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="VW",
            original_name="VW",
            aliases={"en": ["Volkswagen"], "zh": []},
        )
        db_session.add(brand)
        db_session.flush()

        result = _find_brand_by_alias(db_session, vertical.id, "volkswagen")

        assert result is not None
        assert result.id == brand.id

    def test_returns_none_when_no_match(self, db_session):
        vertical = Vertical(name="SUV cars", description="SUV cars")
        db_session.add(vertical)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="VW",
            original_name="VW",
            aliases={"en": ["Volkswagen"], "zh": ["大众"]},
        )
        db_session.add(brand)
        db_session.flush()

        result = _find_brand_by_alias(db_session, vertical.id, "Toyota")

        assert result is None

    def test_only_matches_within_same_vertical(self, db_session):
        vertical1 = Vertical(name="SUV cars", description="SUV cars")
        vertical2 = Vertical(name="Phones", description="Mobile phones")
        db_session.add(vertical1)
        db_session.add(vertical2)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical1.id,
            display_name="VW",
            original_name="VW",
            aliases={"en": ["Volkswagen"], "zh": []},
        )
        db_session.add(brand)
        db_session.flush()

        result = _find_brand_by_alias(db_session, vertical2.id, "Volkswagen")

        assert result is None

    def test_normalized_match_ignores_apostrophe(self, db_session):
        vertical = Vertical(name="SUV cars", description="SUV cars")
        db_session.add(vertical)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="Changan (长安)",
            original_name="Changan",
            aliases={"en": ["Changan"], "zh": ["长安"]},
        )
        db_session.add(brand)
        db_session.flush()

        result = _find_brand_by_alias(db_session, vertical.id, "Chang'an")

        assert result is not None
        assert result.id == brand.id

    def test_chinese_substring_match(self, db_session):
        vertical = Vertical(name="SUV cars", description="SUV cars")
        db_session.add(vertical)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="Changan (长安)",
            original_name="长安",
            aliases={"en": [], "zh": ["长安"]},
        )
        db_session.add(brand)
        db_session.flush()

        result = _find_brand_by_alias(db_session, vertical.id, "长安汽车")

        assert result is not None
        assert result.id == brand.id

    def test_english_substring_match_with_suffix(self, db_session):
        vertical = Vertical(name="SUV cars", description="SUV cars")
        db_session.add(vertical)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="GAC (广汽)",
            original_name="GAC",
            aliases={"en": ["GAC"], "zh": ["广汽"]},
        )
        db_session.add(brand)
        db_session.flush()

        result = _find_brand_by_alias(db_session, vertical.id, "GAC Motors")

        assert result is not None
        assert result.id == brand.id

    def test_matches_display_name_not_just_aliases(self, db_session):
        vertical = Vertical(name="SUV cars", description="SUV cars")
        db_session.add(vertical)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="Liauto (理想)",
            original_name="理想",
            aliases={"en": [], "zh": []},
        )
        db_session.add(brand)
        db_session.flush()

        result = _find_brand_by_alias(db_session, vertical.id, "理想汽车")

        assert result is not None
        assert result.id == brand.id

    def test_no_false_positive_on_short_substrings(self, db_session):
        vertical = Vertical(name="SUV cars", description="SUV cars")
        db_session.add(vertical)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="BYD (比亚迪)",
            original_name="BYD",
            aliases={"en": ["BYD"], "zh": ["比亚迪"]},
        )
        db_session.add(brand)
        db_session.flush()

        result = _find_brand_by_alias(db_session, vertical.id, "BY")

        assert result is None
