"""Test hard merge constraints that prevent parent-variant merging."""

from services.brand_recognition import _has_variant_signals, _match_substring_alias


def test_has_variant_signals_with_digits():
    assert _has_variant_signals("iPhone14")
    assert _has_variant_signals("ID.4")
    assert _has_variant_signals("L7")
    assert _has_variant_signals("Mate50")
    assert _has_variant_signals("小米13")


def test_has_variant_signals_with_trim_markers():
    assert _has_variant_signals("宋PLUS")
    assert _has_variant_signals("iPhone Pro")
    assert _has_variant_signals("Model Y Max")
    assert _has_variant_signals("汉DM-i")
    assert _has_variant_signals("唐EV")
    assert _has_variant_signals("Model Y Long Range")


def test_has_variant_signals_with_capacity():
    assert _has_variant_signals("128GB")
    assert _has_variant_signals("65英寸")
    assert _has_variant_signals("1.5T")
    assert _has_variant_signals("5000mAh")


def test_has_variant_signals_no_signals():
    assert not _has_variant_signals("iPhone")
    assert not _has_variant_signals("Tesla")
    assert not _has_variant_signals("比亚迪")
    assert not _has_variant_signals("大众")
    assert not _has_variant_signals("Model")


def test_has_variant_signals_edge_cases():
    assert not _has_variant_signals("")
    assert not _has_variant_signals("X")
    assert not _has_variant_signals(None)


def test_match_substring_prevents_parent_variant_merge():
    lookup = {"iphone": "iphone"}

    result = _match_substring_alias("iphone14", lookup)
    assert result is None, "Should not merge iphone14 -> iphone"

    result = _match_substring_alias("iphone", lookup)
    assert result == "iphone", "Exact match should still work"


def test_match_substring_prevents_chinese_variant_merge():
    lookup = {"宋": "宋"}

    result = _match_substring_alias("宋plus", lookup)
    assert result is None, "Should not merge 宋plus -> 宋"

    result = _match_substring_alias("宋", lookup)
    assert result == "宋", "Exact match should still work"


def test_match_substring_prevents_model_variant_merge():
    lookup = {"modely": "modely"}

    result = _match_substring_alias("modelylongrange", lookup)
    assert result is None, "Should not merge model y long range -> model y"

    result = _match_substring_alias("modely", lookup)
    assert result == "modely", "Exact match should still work"


def test_match_substring_allows_alias_merge():
    lookup = {"tesla": "tesla", "特斯拉": "tesla"}

    result = _match_substring_alias("tesla", lookup)
    assert result == "tesla"

    result = _match_substring_alias("特斯拉", lookup)
    assert result == "tesla"


def test_match_substring_variant_to_variant_prevented():
    lookup = {"iphone14": "iphone14", "modely": "modely"}

    result = _match_substring_alias("iphone14pro", lookup)
    assert result is None, "Should not merge iphone14pro -> iphone14 (additional variant signal 'pro')"

    result = _match_substring_alias("modelylongrange", lookup)
    assert result is None, "Should not merge model y long range -> model y"


def test_match_substring_complex_cases():
    lookup = {"比亚迪": "比亚迪", "byd": "比亚迪"}

    result = _match_substring_alias("比亚迪宋plus", lookup)
    assert result is None, "Should not merge 比亚迪宋plus -> 比亚迪"

    result = _match_substring_alias("byd宋plus", lookup)
    assert result is None, "Should not merge byd宋plus -> 比亚迪"


def test_match_substring_preserves_product_variants():
    lookup = {
        "iphone": "iphone",
        "samsung": "samsung",
        "xiaomi": "xiaomi"
    }

    assert _match_substring_alias("iphone14", lookup) is None
    assert _match_substring_alias("iphone14pro", lookup) is None
    assert _match_substring_alias("samsungs23", lookup) is None
    assert _match_substring_alias("xiaomi13ultra", lookup) is None


def test_match_substring_digit_variants():
    lookup = {"mate": "mate"}

    assert _match_substring_alias("mate50", lookup) is None
    assert _match_substring_alias("mate50pro", lookup) is None
    assert _match_substring_alias("mate", lookup) == "mate"


def test_match_substring_capacity_variants():
    lookup = {"iphone": "iphone"}

    assert _match_substring_alias("iphone128gb", lookup) is None
    assert _match_substring_alias("iphone1tb", lookup) is None
