"""Unit tests for snippet deduplication and capping in _collect_all_snippets."""

from workers.tasks import _collect_all_snippets, _get_translated_snippets


def test_deduplicates_identical_snippets(monkeypatch):
    monkeypatch.setattr("workers.tasks.settings.snippet_translation_cap_per_entity", 10)
    brand_mentions = [
        {"mentioned": True, "brand_index": 0, "snippets": ["snippet A", "snippet B"]},
        {"mentioned": True, "brand_index": 1, "snippets": ["snippet A", "snippet C"]},
    ]
    all_snippets, snippet_map = _collect_all_snippets(brand_mentions, [])

    assert len(all_snippets) == 3
    assert snippet_map[("brand", 0, 0)] == snippet_map[("brand", 1, 0)]


def test_caps_snippets_per_entity(monkeypatch):
    monkeypatch.setattr("workers.tasks.settings.snippet_translation_cap_per_entity", 2)
    brand_mentions = [
        {"mentioned": True, "brand_index": 0, "snippets": ["s1", "s2", "s3", "s4"]},
    ]
    all_snippets, snippet_map = _collect_all_snippets(brand_mentions, [])

    assert len(all_snippets) == 2
    assert ("brand", 0, 0) in snippet_map
    assert ("brand", 0, 1) in snippet_map
    assert ("brand", 0, 2) not in snippet_map
    assert ("brand", 0, 3) not in snippet_map


def test_cap_does_not_count_deduped(monkeypatch):
    monkeypatch.setattr("workers.tasks.settings.snippet_translation_cap_per_entity", 2)
    brand_mentions = [
        {"mentioned": True, "brand_index": 0, "snippets": ["dup", "s1", "s2"]},
        {"mentioned": True, "brand_index": 1, "snippets": ["dup", "s3"]},
    ]
    all_snippets, snippet_map = _collect_all_snippets(brand_mentions, [])

    assert ("brand", 1, 0) in snippet_map
    assert ("brand", 1, 1) in snippet_map
    assert snippet_map[("brand", 1, 0)] == snippet_map[("brand", 0, 0)]


def test_skips_not_mentioned():
    brand_mentions = [
        {"mentioned": False, "brand_index": 0, "snippets": ["s1"]},
        {"mentioned": True, "brand_index": 1, "snippets": ["s2"]},
    ]
    all_snippets, snippet_map = _collect_all_snippets(brand_mentions, [])

    assert len(all_snippets) == 1
    assert ("brand", 0, 0) not in snippet_map


def test_products_also_deduped(monkeypatch):
    monkeypatch.setattr("workers.tasks.settings.snippet_translation_cap_per_entity", 10)
    brand_mentions = [
        {"mentioned": True, "brand_index": 0, "snippets": ["shared"]},
    ]
    product_mentions = [
        {"mentioned": True, "product_index": 0, "rank": 1, "snippets": ["shared", "unique"]},
    ]
    all_snippets, snippet_map = _collect_all_snippets(brand_mentions, product_mentions)

    assert len(all_snippets) == 2
    assert snippet_map[("brand", 0, 0)] == snippet_map[("product", 0, 0)]


def test_get_translated_snippets_uses_map():
    snippet_map = {("brand", 0, 0): 0, ("brand", 0, 1): 1}
    translated = ["english A", "english B"]
    zh = ["chinese A", "chinese B", "chinese C"]

    result = _get_translated_snippets("brand", 0, zh, snippet_map, translated)
    assert result == ["english A", "english B", "chinese C"]
