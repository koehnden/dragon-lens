import pytest

from services.brand_discovery import (
    _canonicalize_brand_name,
    _find_brand_by_alias,
    _get_canonical_lookup_name,
    _is_substring_match,
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

    def test_does_not_cross_match_unrelated_same_length_brands(self, db_session):
        vertical = Vertical(name="SUV cars", description="SUV cars")
        db_session.add(vertical)
        db_session.flush()

        toyota = Brand(
            vertical_id=vertical.id,
            display_name="Toyota",
            original_name="Toyota",
            aliases={"en": ["Toyota"], "zh": ["丰田"]},
        )
        honda = Brand(
            vertical_id=vertical.id,
            display_name="Honda",
            original_name="Honda",
            aliases={"en": ["Honda"], "zh": ["本田"]},
        )
        li_auto = Brand(
            vertical_id=vertical.id,
            display_name="Li Auto",
            original_name="Li Auto",
            aliases={"en": ["Li Auto"], "zh": ["理想"]},
        )
        db_session.add_all([toyota, honda, li_auto])
        db_session.flush()

        assert _find_brand_by_alias(db_session, vertical.id, "Toyota").id == toyota.id
        assert _find_brand_by_alias(db_session, vertical.id, "丰田").id == toyota.id
        assert _find_brand_by_alias(db_session, vertical.id, "Honda").id == honda.id
        assert _find_brand_by_alias(db_session, vertical.id, "本田").id == honda.id
        assert _find_brand_by_alias(db_session, vertical.id, "Li Auto").id == li_auto.id
        assert _find_brand_by_alias(db_session, vertical.id, "理想").id == li_auto.id

        assert _find_brand_by_alias(db_session, vertical.id, "Lexus") is None
        assert _find_brand_by_alias(db_session, vertical.id, "Tesla") is None
        assert _find_brand_by_alias(db_session, vertical.id, "Mazda") is None


class TestSubstringMatch:

    @pytest.mark.parametrize(
        ("name1", "name2"),
        [
            ("toyota", "liauto"),
            ("lexus", "honda"),
            ("tesla", "honda"),
            ("ford", "oxford"),
            ("mini", "minimax"),
        ],
    )
    def test_rejects_false_positive_latin_matches(self, name1, name2):
        assert _is_substring_match(name1, name2) is False

    @pytest.mark.parametrize(
        ("name1", "name2"),
        [
            ("GAC", "GAC Motors"),
            ("长安", "长安汽车"),
            ("理想", "理想汽车"),
            ("大众", "上汽大众"),
        ],
    )
    def test_allows_expected_brand_expansions(self, name1, name2):
        assert _is_substring_match(name1, name2) is True
