import pytest
from unittest.mock import MagicMock, patch

from services.knowledge_lookup import (
    _add_product_to_cache,
    _build_cache_for_vertical,
    _find_product_by_key,
    _lookup_brand_for_product,
)


def test_add_product_to_cache_includes_canonical_and_display():
    cache = {}
    product = MagicMock()
    product.canonical_name = "rav4"
    product.display_name = "RAV4"
    product.aliases = []

    _add_product_to_cache(cache, product, "Toyota")

    assert cache["rav4"] == "Toyota"
    assert cache["rav4"] == "Toyota"


def test_add_product_to_cache_includes_aliases():
    cache = {}
    product = MagicMock()
    product.canonical_name = "rav4"
    product.display_name = "RAV4"

    alias1 = MagicMock()
    alias1.alias = "RAV-4"
    alias2 = MagicMock()
    alias2.alias = "丰田RAV4"
    product.aliases = [alias1, alias2]

    _add_product_to_cache(cache, product, "Toyota")

    assert cache["rav-4"] == "Toyota"
    assert cache["丰田rav4"] == "Toyota"


def test_build_cache_for_vertical_empty_when_no_mappings():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    cache = _build_cache_for_vertical(db, 1)

    assert cache == {}


def test_build_cache_for_vertical_includes_mappings():
    db = MagicMock()

    brand = MagicMock()
    brand.display_name = "Toyota"

    product = MagicMock()
    product.canonical_name = "rav4"
    product.display_name = "RAV4"
    product.aliases = []

    mapping = MagicMock()
    mapping.brand = brand
    mapping.product = product

    db.query.return_value.filter.return_value.all.return_value = [mapping]

    cache = _build_cache_for_vertical(db, 1)

    assert cache["rav4"] == "Toyota"


def test_lookup_brand_for_product_returns_none_when_not_found():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.join.return_value.filter.return_value.first.return_value = None

    result = _lookup_brand_for_product(db, 1, "UnknownProduct")

    assert result is None


def test_find_product_by_key_finds_by_canonical_name():
    db = MagicMock()
    product = MagicMock()
    product.id = 1

    db.query.return_value.filter.return_value.first.return_value = product

    result = _find_product_by_key(db, 1, "rav4")

    assert result == product


def test_find_product_by_key_finds_by_alias():
    db = MagicMock()

    db.query.return_value.filter.return_value.first.return_value = None

    alias = MagicMock()
    alias.product = MagicMock()
    alias.product.id = 1
    db.query.return_value.join.return_value.filter.return_value.first.return_value = alias

    result = _find_product_by_key(db, 1, "丰田rav4")

    assert result == alias.product
