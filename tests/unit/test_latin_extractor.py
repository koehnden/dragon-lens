"""Tests for Latin-alphabet token extraction from Chinese text."""

from services.extraction.latin_extractor import extract_latin_tokens, is_cjk_dominant


def test_extracts_brand_from_chinese_text():
    text = "推荐 Nike 跑鞋，非常舒适"
    tokens = extract_latin_tokens(text)
    assert "Nike" in tokens


def test_extracts_multiple_brands():
    text = "对比 Adidas 和 Nike 的篮球鞋"
    tokens = extract_latin_tokens(text)
    assert "Adidas" in tokens
    assert "Nike" in tokens


def test_extracts_hyphenated_names():
    text = "选择 GORE-TEX 面料很重要"
    tokens = extract_latin_tokens(text)
    assert "GORE-TEX" in tokens


def test_ignores_stopwords():
    text = "推荐这款跑鞋非常好，the best for Nike 运动鞋系列"
    tokens = extract_latin_tokens(text)
    assert "the" not in tokens
    assert "for" not in tokens
    assert "Nike" in tokens


def test_ignores_size_codes():
    text = "尺码 XL 和 M 号"
    tokens = extract_latin_tokens(text)
    assert not any(t in ("XL", "M") for t in tokens)


def test_ignores_units():
    text = "重量 500ml 容量 2kg"
    tokens = extract_latin_tokens(text)
    assert not any(t in ("500ml", "2kg", "ml", "kg") for t in tokens)


def test_ignores_single_characters():
    text = "选项 A 和 B"
    tokens = extract_latin_tokens(text)
    assert "A" not in tokens
    assert "B" not in tokens


def test_deduplicates_case_insensitive():
    text = "Nike NIKE nike 都很好"
    tokens = extract_latin_tokens(text)
    assert len([t for t in tokens if t.lower() == "nike"]) == 1


def test_mixed_chinese_english_product_names():
    text = "1. 花王 Merries 纸尿裤 NB码 2. Pampers 帮宝适"
    tokens = extract_latin_tokens(text)
    assert "Merries" in tokens
    assert "Pampers" in tokens


def test_empty_string():
    assert extract_latin_tokens("") == []


def test_pure_chinese_text():
    text = "这是一个纯中文的句子，没有英文"
    assert extract_latin_tokens(text) == []


def test_multi_word_brand_extracts_individual_words():
    text = "推荐 North Face 冲锋衣"
    tokens = extract_latin_tokens(text)
    assert "North" in tokens
    assert "Face" in tokens


def test_alphanumeric_product_codes():
    text = "推荐 RAV4 和 CR-V 车型"
    tokens = extract_latin_tokens(text)
    assert "RAV4" in tokens
    assert "CR-V" in tokens


def test_skips_english_text():
    text = "This is a great product with excellent design and breathable materials"
    tokens = extract_latin_tokens(text)
    assert tokens == []


def test_skips_english_text_with_brands():
    text = "Nike and Adidas are great brands for running shoes with good value"
    tokens = extract_latin_tokens(text)
    assert tokens == []


def test_cjk_dominant_mixed_text():
    assert is_cjk_dominant("推荐 Nike 跑鞋") is True
    assert is_cjk_dominant("This is English text") is False
    assert is_cjk_dominant("这是纯中文") is True
    assert is_cjk_dominant("") is False
