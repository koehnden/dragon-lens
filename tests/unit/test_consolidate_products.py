"""Tests for product consolidation (brand prefix stripping + variant grouping)."""

import pytest

from services.extraction.product_consolidation import (
    build_reverse_brand_map,
    merge_suffix_variants,
    partition_products_by_brand,
    strip_brand_prefixes,
    strip_product_suffix,
    try_strip_brand,
)


class TestBuildReverseBrandMap:
    def test_includes_aliases_and_canonicals(self) -> None:
        aliases = {"大众": "Volkswagen", "VW": "Volkswagen"}
        result = build_reverse_brand_map(aliases)
        assert result["大众"] == "Volkswagen"
        assert result["VW"] == "Volkswagen"
        assert result["Volkswagen"] == "Volkswagen"


class TestTryStripBrand:
    def test_strips_latin_prefix(self) -> None:
        brands = ["Salomon", "Merrell"]
        reverse = {"Salomon": "Salomon", "Merrell": "Merrell"}
        stripped, brand = try_strip_brand("Salomon X Ultra 4 GTX", brands, reverse)
        assert stripped == "X Ultra 4 GTX"
        assert brand == "Salomon"

    def test_strips_chinese_prefix(self) -> None:
        brands = ["比亚迪"]
        reverse = {"比亚迪": "BYD"}
        stripped, brand = try_strip_brand("比亚迪唐DM-i", brands, reverse)
        assert stripped == "唐DM-i"
        assert brand == "BYD"

    def test_no_match_returns_none(self) -> None:
        brands = ["Salomon"]
        reverse = {"Salomon": "Salomon"}
        stripped, brand = try_strip_brand("Merrell Moab 3", brands, reverse)
        assert stripped is None
        assert brand is None

    def test_skips_short_brands(self) -> None:
        brands = ["X"]
        reverse = {"X": "X"}
        stripped, brand = try_strip_brand("X Ultra 4", brands, reverse)
        assert stripped is None

    def test_short_remainder_rejected(self) -> None:
        brands = ["Salomon"]
        reverse = {"Salomon": "Salomon"}
        stripped, brand = try_strip_brand("Salomon X", brands, reverse)
        assert stripped is None

    def test_digit_only_remainder_rejected(self) -> None:
        brands = ["Moab"]
        reverse = {"Moab": "Merrell"}
        stripped, brand = try_strip_brand("Moab 3", brands, reverse)
        assert stripped is None


class TestStripBrandPrefixes:
    def test_strips_and_adds_mapping(self) -> None:
        product_aliases = {"Salomon X Ultra 4 GTX": "Salomon X Ultra 4 GTX"}
        product_brand_map: dict[str, str] = {}
        reverse = {"Salomon": "Salomon"}

        new_aliases, new_map = strip_brand_prefixes(
            product_aliases, product_brand_map, reverse,
        )
        assert new_aliases["Salomon X Ultra 4 GTX"] == "X Ultra 4 GTX"
        assert new_map["X Ultra 4 GTX"] == "Salomon"

    def test_preserves_existing_mapping(self) -> None:
        product_aliases = {"比亚迪唐DM-i": "比亚迪唐DM-i"}
        product_brand_map = {"唐DM-i": "BYD"}
        reverse = {"比亚迪": "BYD"}

        _, new_map = strip_brand_prefixes(
            product_aliases, product_brand_map, reverse,
        )
        assert new_map["唐DM-i"] == "BYD"

    def test_no_mutation_of_originals(self) -> None:
        original_aliases = {"Foo Bar": "Foo Bar"}
        original_map: dict[str, str] = {}
        reverse = {"Foo": "Foo"}

        strip_brand_prefixes(original_aliases, original_map, reverse)
        assert original_aliases == {"Foo Bar": "Foo Bar"}
        assert original_map == {}


class TestStripProductSuffix:
    def test_strips_gtx(self) -> None:
        assert strip_product_suffix("X Ultra 4 GTX") == "X Ultra 4"

    def test_strips_waterproof(self) -> None:
        assert strip_product_suffix("Moab 3 Waterproof") == "Moab 3"

    def test_strips_multiple_suffixes(self) -> None:
        assert strip_product_suffix("Anacapa Mid GTX") == "Anacapa"

    def test_no_suffix_returns_none(self) -> None:
        assert strip_product_suffix("Moab 3") is None

    def test_single_word_returns_none(self) -> None:
        assert strip_product_suffix("GTX") is None

    def test_strips_all_wthr(self) -> None:
        assert strip_product_suffix("Lone Peak ALL-WTHR") == "Lone Peak"


class TestMergeSuffixVariants:
    def test_merges_gtx_variant_to_base(self) -> None:
        aliases = {
            "X Ultra 4": "X Ultra 4",
            "X Ultra 4 GTX": "X Ultra 4 GTX",
        }
        result = merge_suffix_variants(aliases)
        assert result["X Ultra 4 GTX"] == "X Ultra 4"
        assert result["X Ultra 4"] == "X Ultra 4"

    def test_merges_mid_gtx_variant(self) -> None:
        aliases = {
            "Anacapa": "Anacapa",
            "Anacapa Mid GTX": "Anacapa Mid GTX",
        }
        result = merge_suffix_variants(aliases)
        assert result["Anacapa Mid GTX"] == "Anacapa"

    def test_no_base_product_no_merge(self) -> None:
        aliases = {"Moab 3 GTX": "Moab 3 GTX"}
        result = merge_suffix_variants(aliases)
        assert result["Moab 3 GTX"] == "Moab 3 GTX"

    def test_preserves_unrelated_products(self) -> None:
        aliases = {"RAV4荣放": "RAV4荣放", "CR-V": "CR-V"}
        result = merge_suffix_variants(aliases)
        assert result == aliases


class TestPartitionProductsByBrand:
    def test_partitions_correctly(self) -> None:
        aliases = {"A": "A", "B": "B", "C": "C"}
        brand_map = {"A": "BrandX", "B": "BrandX"}
        by_brand, unmapped = partition_products_by_brand(aliases, brand_map)
        assert by_brand == {"BrandX": ["A", "B"]}
        assert unmapped == ["C"]
