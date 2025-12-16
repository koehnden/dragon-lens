"""Test that product variants are preserved and not merged into parent brands."""

from services.brand_recognition import extract_entities


def test_iphone14_not_merged_to_iphone():
    text = "1. iPhone14 Pro - great phone"
    entities = extract_entities(text, "iPhone", {"zh": ["苹果"], "en": ["iPhone"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("14" in name for name in extracted_names), f"Expected iPhone14 variant in {extracted_names}"
    assert not (len(extracted_names) == 1 and "iphone" in str(extracted_names).lower() and "14" not in str(extracted_names)), \
        f"iPhone14 should not be merged into iphone: {extracted_names}"


def test_song_plus_not_merged_to_song():
    text = "1. 宋PLUS DM-i - 很好的车"
    entities = extract_entities(text, "比亚迪", {"zh": ["BYD"], "en": ["BYD"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("plus" in name.lower() for name in extracted_names), f"Expected 宋PLUS in {extracted_names}"


def test_mate50_not_merged_to_mate():
    text = "华为Mate50 Pro很受欢迎"
    entities = extract_entities(text, "华为", {"zh": ["Huawei"], "en": ["Huawei"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("50" in name for name in extracted_names), f"Expected Mate50 variant in {extracted_names}"


def test_model_y_long_range_not_merged():
    text = "Tesla Model Y Long Range is great"
    entities = extract_entities(text, "Tesla", {"zh": ["特斯拉"], "en": ["Tesla"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("long" in name.lower() or "range" in name.lower() for name in extracted_names), \
        f"Expected Model Y Long Range variant in {extracted_names}"


def test_s23_preserved():
    text = "Samsung S23 is excellent"
    entities = extract_entities(text, "Samsung", {"zh": ["三星"], "en": ["Samsung"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("s23" in name.lower() for name in extracted_names), f"Expected S23 in {extracted_names}"


def test_xiaomi13_ultra_preserved():
    text = "小米13 Ultra拍照很好"
    entities = extract_entities(text, "小米", {"zh": ["Xiaomi"], "en": ["Xiaomi"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("13" in name and "ultra" in name.lower() for name in extracted_names), \
        f"Expected 小米13 Ultra in {extracted_names}"
