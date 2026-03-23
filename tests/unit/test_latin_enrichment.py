"""Tests for Latin token enrichment in the extraction pipeline."""

from services.extraction.models import BrandProductPair, ItemExtractionResult, ResponseItem
from services.extraction.pipeline import _enrich_with_latin_tokens


def _make_result(text, pairs=None):
    item = ResponseItem(text=text, position=0)
    return ItemExtractionResult(item=item, pairs=pairs or [])


def test_adds_latin_token_when_qwen_found_nothing():
    results = [_make_result("推荐 Nike 跑鞋")]
    enriched = _enrich_with_latin_tokens(results)
    brands = [p.brand for p in enriched[0].pairs]
    assert "Nike" in brands


def test_skips_token_already_found_by_qwen():
    results = [_make_result(
        "推荐 Nike 跑鞋",
        pairs=[BrandProductPair(brand="Nike", product=None, brand_source="qwen")],
    )]
    enriched = _enrich_with_latin_tokens(results)
    assert len(enriched[0].pairs) == 1


def test_skips_substring_of_existing():
    results = [_make_result(
        "推荐 HOKA One 跑鞋",
        pairs=[BrandProductPair(brand="HOKA One One", product=None, brand_source="qwen")],
    )]
    enriched = _enrich_with_latin_tokens(results)
    hoka_pairs = [p for p in enriched[0].pairs if "HOKA" in (p.brand or "")]
    assert len(hoka_pairs) == 1


def test_adds_multiple_missing_tokens():
    results = [_make_result("对比 Adidas 和 Puma 的篮球鞋")]
    enriched = _enrich_with_latin_tokens(results)
    brands = [p.brand for p in enriched[0].pairs]
    assert "Adidas" in brands
    assert "Puma" in brands


def test_source_is_latin():
    results = [_make_result("推荐 Nike 跑鞋")]
    enriched = _enrich_with_latin_tokens(results)
    latin_pairs = [p for p in enriched[0].pairs if p.brand_source == "latin"]
    assert len(latin_pairs) == 1


def test_preserves_existing_pairs():
    existing = BrandProductPair(brand="花王", product="妙而舒", brand_source="kb", product_source="kb")
    results = [_make_result("花王 Merries 妙而舒", pairs=[existing])]
    enriched = _enrich_with_latin_tokens(results)
    assert enriched[0].pairs[0] == existing
    assert any(p.brand == "Merries" for p in enriched[0].pairs)
