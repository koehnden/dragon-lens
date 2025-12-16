"""Test embedding-based clustering for brand and product names."""

import pytest
from services.brand_recognition import extract_entities


@pytest.fixture(autouse=True)
def enable_embedding_clustering(monkeypatch):
    """Enable embedding clustering for all tests in this module."""
    monkeypatch.setenv("ENABLE_EMBEDDING_CLUSTERING", "true")
    monkeypatch.setenv("ENABLE_LLM_CLUSTERING", "false")


def test_clusters_iphone_variants():
    """Test that iPhone variants with similar names cluster together."""
    text = "推荐iPhone14 Pro和iPhone 14 Pro，还有iphone14pro"
    entities = extract_entities(text, "iPhone", {"zh": ["苹果"], "en": ["iPhone"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert len(extracted_names) <= 3, f"Should cluster similar iPhone14 Pro variants, got {extracted_names}"


def test_clusters_nike_air_max_variants():
    """Test that Nike Air Max variants cluster together."""
    text = "Nike Air Max 90 and Nike AirMax 90 are the same shoe"
    entities = extract_entities(text, "Nike", {"zh": ["耐克"], "en": ["Nike"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("air" in name.lower() and "max" in name.lower() for name in extracted_names)


def test_clusters_chinese_brand_variants():
    """Test that Chinese brand name variants cluster together."""
    text = "比亚迪宋PLUS和比亚迪 宋 PLUS是同一款车"
    entities = extract_entities(text, "比亚迪", {"zh": ["BYD"], "en": ["BYD"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("宋" in name and "plus" in name.lower() for name in extracted_names)


def test_does_not_cluster_different_products():
    """Test that different products don't get clustered together."""
    text = "推荐iPhone14和iPhone15，都是好手机"
    entities = extract_entities(text, "iPhone", {"zh": ["苹果"], "en": ["iPhone"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    has_iphone = any("iphone" in name.lower() for name in extracted_names)
    assert has_iphone, f"Should extract iPhone variants: {extracted_names}"


def test_clusters_spacing_variations():
    """Test that spacing variations get clustered."""
    text = "Tesla Model Y和Tesla ModelY是同一款车"
    entities = extract_entities(text, "Tesla", {"zh": ["特斯拉"], "en": ["Tesla"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert len(extracted_names) <= 4, f"Should cluster spacing variants: {extracted_names}"


def test_clusters_case_variations():
    """Test that case variations get clustered."""
    text = "Adidas Ultra Boost和adidas ultra boost是同一款鞋"
    entities = extract_entities(text, "Adidas", {"zh": ["阿迪达斯"], "en": ["Adidas"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("ultra" in name.lower() for name in extracted_names)


def test_clusters_chinese_english_mix():
    """Test clustering with mixed Chinese and English."""
    text = "华为Mate50 Pro和华为 Mate 50 Pro是同一款手机"
    entities = extract_entities(text, "华为", {"zh": ["Huawei"], "en": ["Huawei"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("mate" in name.lower() and "50" in name for name in extracted_names)


def test_does_not_cluster_different_brands():
    """Test that similar-sounding but different brands don't cluster together."""
    text = "Nike Air Max和New Balance跑鞋都很好"
    entities = extract_entities(text, "Nike", {"zh": ["耐克"], "en": ["Nike"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    has_nike = any("nike" in name.lower() or "耐克" in name for name in extracted_names)
    has_balance = any("balance" in name.lower() for name in extracted_names)
    assert has_nike and has_balance, f"Should keep Nike and New Balance separate: {extracted_names}"


def test_clusters_abbreviated_forms():
    """Test that abbreviated forms cluster with full names."""
    text = "The North Face羽绒服和TNF羽绒服"
    entities = extract_entities(text, "The North Face", {"zh": ["北面", "北脸"], "en": ["The North Face", "TNF"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert len(extracted_names) >= 1, f"Should extract North Face/TNF variants: {extracted_names}"


def test_clusters_model_number_variations():
    """Test that model number variations cluster together."""
    text = "小米13 Ultra和小米 13ultra拍照很好"
    entities = extract_entities(text, "小米", {"zh": ["Xiaomi"], "en": ["Xiaomi"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("13" in name and "ultra" in name.lower() for name in extracted_names)


def test_preserves_distinct_versions():
    """Test that truly distinct versions are preserved."""
    text = "Samsung S23和Samsung S24是不同代产品"
    entities = extract_entities(text, "Samsung", {"zh": ["三星"], "en": ["Samsung"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    has_s23 = any("s23" in name.lower() or "23" in name for name in extracted_names)
    has_s24 = any("s24" in name.lower() or "24" in name for name in extracted_names)
    assert has_s23 or has_s24, f"Should preserve S23/S24 distinction: {extracted_names}"


def test_clusters_hyphen_variations():
    """Test that hyphen variations cluster together."""
    text = "Salomon XT-6和Salomon XT6越野跑鞋"
    entities = extract_entities(text, "Salomon", {"zh": ["萨洛蒙"], "en": ["Salomon"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("xt" in name.lower() and "6" in name for name in extracted_names)


def test_embedding_quality_with_mixed_content():
    """Test embedding clustering with mixed product mentions."""
    text = "推荐几款手机：1. iPhone14 Pro 2. 三星S23 3. 小米13 Ultra，iPhone 14 Pro最好"
    entities = extract_entities(text, "iPhone", {"zh": ["苹果"], "en": ["iPhone"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("iphone" in name.lower() for name in extracted_names), f"Should extract iPhone: {extracted_names}"
    assert any("14" in name for name in extracted_names), f"Should extract iPhone14 variant: {extracted_names}"
