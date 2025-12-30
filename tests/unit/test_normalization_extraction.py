"""Test that normalization improves brand/product extraction."""

from services.brand_recognition import extract_entities


def test_extracts_fullwidth_product_names():
    text = "推荐iPhone１４　Pro和Samsung　Ｓ２３"
    entities = extract_entities(text, "iPhone", {"zh": ["苹果"], "en": ["iPhone"]})
    extracted_names = set(entities.all_entities().keys())

    assert any("iphone" in name.lower() for name in extracted_names), f"Expected iPhone in {extracted_names}"
    assert any("s23" in name.lower() for name in extracted_names), f"Expected S23 in {extracted_names}"


def test_extracts_fullwidth_chinese_products():
    text = "宋ＰＬＵＳ　ＤＭ－ｉ很受欢迎"
    entities = extract_entities(text, "比亚迪", {"zh": ["BYD"], "en": ["BYD"]})
    extracted_names = set(entities.all_entities().keys())

    assert any("plus" in name.lower() for name in extracted_names), f"Expected PLUS in {extracted_names}"


def test_extracts_mixed_width_brands():
    text = "１。Ｔｅｓｌａ　Model　Y，２。比亚迪宋PLUS"
    entities = extract_entities(text, "Tesla", {"zh": ["特斯拉"], "en": ["Tesla"]})
    extracted_names = set(entities.all_entities().keys())

    assert any("tesla" in name.lower() or "特斯拉" in name for name in extracted_names), f"Expected Tesla/特斯拉 in {extracted_names}"
    assert any("modely" in name.lower() or ("model" in name.lower() and "y" in name.lower()) for name in extracted_names), f"Expected ModelY in {extracted_names}"
    assert any("plus" in name.lower() for name in extracted_names), f"Expected PLUS in {extracted_names}"


def test_chinese_punctuation_doesnt_break_extraction():
    text = "推荐品牌：Tesla、比亚迪、大众。都很好！"
    entities = extract_entities(text, "Tesla", {"zh": ["特斯拉"], "en": ["Tesla"]})
    extracted_names = set(entities.all_entities().keys())

    assert any("tesla" in name.lower() or "特斯拉" in name for name in extracted_names), f"Expected Tesla/特斯拉 in {extracted_names}"
    assert any("比亚迪" in name.lower() for name in extracted_names), f"Expected 比亚迪 in {extracted_names}"
    assert any("大众" in name.lower() for name in extracted_names), f"Expected 大众 in {extracted_names}"
    assert not any("都很好" in name for name in extracted_names), f"Should filter '都很好' but found in {extracted_names}"


def test_fullwidth_brackets_product_extraction():
    text = "热门产品【Tesla　Model　Y】和（比亚迪宋PLUS）"
    entities = extract_entities(text, "Tesla", {"zh": ["特斯拉"], "en": ["Tesla"]})
    extracted_names = set(entities.all_entities().keys())

    assert any("tesla" in name.lower() or "特斯拉" in name for name in extracted_names), f"Expected Tesla/特斯拉 in {extracted_names}"
    assert any("modely" in name.lower() or ("model" in name.lower() and "y" in name.lower()) for name in extracted_names), f"Expected ModelY in {extracted_names}"
    assert any("plus" in name.lower() for name in extracted_names), f"Expected PLUS in {extracted_names}"
