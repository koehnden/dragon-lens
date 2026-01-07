from workers.tasks import (
    _collect_all_snippets,
    _get_translated_snippets,
)


def test_collect_all_snippets_empty():
    all_snippets, snippet_map = _collect_all_snippets([], [])
    assert all_snippets == []
    assert snippet_map == {}


def test_collect_all_snippets_brand_only():
    brand_mentions = [
        {"brand_index": 0, "mentioned": True, "snippets": ["snippet1", "snippet2"]},
        {"brand_index": 1, "mentioned": False, "snippets": ["ignored"]},
        {"brand_index": 2, "mentioned": True, "snippets": ["snippet3"]},
    ]
    all_snippets, snippet_map = _collect_all_snippets(brand_mentions, [])
    assert all_snippets == ["snippet1", "snippet2", "snippet3"]
    assert snippet_map[("brand", 0, 0)] == 0
    assert snippet_map[("brand", 0, 1)] == 1
    assert snippet_map[("brand", 2, 0)] == 2


def test_collect_all_snippets_product_only():
    product_mentions = [
        {"product_index": 0, "mentioned": True, "rank": 1, "snippets": ["p_snippet1"]},
        {"product_index": 1, "mentioned": True, "rank": None, "snippets": ["ignored"]},
        {"product_index": 2, "mentioned": True, "rank": 2, "snippets": ["p_snippet2"]},
    ]
    all_snippets, snippet_map = _collect_all_snippets([], product_mentions)
    assert all_snippets == ["p_snippet1", "p_snippet2"]
    assert snippet_map[("product", 0, 0)] == 0
    assert snippet_map[("product", 2, 0)] == 1


def test_collect_all_snippets_mixed():
    brand_mentions = [
        {"brand_index": 0, "mentioned": True, "snippets": ["b1"]},
    ]
    product_mentions = [
        {"product_index": 0, "mentioned": True, "rank": 1, "snippets": ["p1", "p2"]},
    ]
    all_snippets, snippet_map = _collect_all_snippets(brand_mentions, product_mentions)
    assert all_snippets == ["b1", "p1", "p2"]
    assert snippet_map[("brand", 0, 0)] == 0
    assert snippet_map[("product", 0, 0)] == 1
    assert snippet_map[("product", 0, 1)] == 2


def test_get_translated_snippets_basic():
    snippet_map = {
        ("brand", 0, 0): 0,
        ("brand", 0, 1): 1,
    }
    translated = ["Hello", "World"]
    zh_snippets = ["你好", "世界"]
    result = _get_translated_snippets("brand", 0, zh_snippets, snippet_map, translated)
    assert result == ["Hello", "World"]


def test_get_translated_snippets_missing_index_uses_original():
    snippet_map = {
        ("brand", 0, 0): 0,
    }
    translated = ["Hello"]
    zh_snippets = ["你好", "世界"]
    result = _get_translated_snippets("brand", 0, zh_snippets, snippet_map, translated)
    assert result[0] == "Hello"
    assert result[1] == "世界"


def test_get_translated_snippets_empty():
    snippet_map = {}
    translated = []
    zh_snippets = []
    result = _get_translated_snippets("brand", 0, zh_snippets, snippet_map, translated)
    assert result == []


def test_get_translated_snippets_out_of_bounds():
    snippet_map = {
        ("brand", 0, 0): 100,
    }
    translated = ["Hello"]
    zh_snippets = ["你好"]
    result = _get_translated_snippets("brand", 0, zh_snippets, snippet_map, translated)
    assert result == ["你好"]
