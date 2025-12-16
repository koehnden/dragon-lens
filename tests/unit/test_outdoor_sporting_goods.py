"""Test NER extraction for Outdoor & Sporting Goods vertical."""

from services.brand_recognition import extract_entities


def test_nike_products_extracted():
    text = "推荐Nike Air Max 90和Nike Dunk Low，都是经典款"
    entities = extract_entities(text, "Nike", {"zh": ["耐克"], "en": ["Nike"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("nike" in name.lower() for name in extracted_names), f"Expected Nike in {extracted_names}"
    assert any("air" in name.lower() or "max" in name.lower() for name in extracted_names), \
        f"Expected Air Max product in {extracted_names}"


def test_adidas_products_extracted():
    text = "Adidas Ultra Boost跑鞋很舒适，Adidas Superstar也不错"
    entities = extract_entities(text, "Adidas", {"zh": ["阿迪达斯"], "en": ["Adidas"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("adidas" in name.lower() for name in extracted_names), f"Expected Adidas in {extracted_names}"
    assert any("boost" in name.lower() or "ultra" in name.lower() for name in extracted_names), \
        f"Expected Ultra Boost product in {extracted_names}"


def test_arcteryx_with_apostrophe():
    text = "Arc'teryx Alpha SV是专业户外装备，Arc'teryx Beta LT也很好"
    entities = extract_entities(text, "Arc'teryx", {"zh": ["始祖鸟"], "en": ["Arc'teryx", "Arcteryx"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("arc" in name.lower() or "始祖鸟" in name for name in extracted_names), \
        f"Expected Arc'teryx in {extracted_names}"


def test_salomon_products():
    text = "Salomon Speedcross 5越野跑鞋，Salomon XT-6复古款"
    entities = extract_entities(text, "Salomon", {"zh": ["萨洛蒙"], "en": ["Salomon"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("salomon" in name.lower() for name in extracted_names), f"Expected Salomon in {extracted_names}"
    assert any("xt" in name.lower() or "speedcross" in name.lower() for name in extracted_names), \
        f"Expected Salomon product in {extracted_names}"


def test_the_north_face_multiword_brand():
    text = "The North Face羽绒服很保暖，北面1996 Retro Nuptse经典款"
    entities = extract_entities(text, "The North Face", {"zh": ["北面", "北脸"], "en": ["The North Face", "TNF"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("north" in name.lower() or "face" in name.lower() or "北面" in name for name in extracted_names), \
        f"Expected The North Face/北面 in {extracted_names}"


def test_chinese_brand_names_outdoor():
    text = "耐克Air Jordan 1很火，阿迪达斯Yeezy也很受欢迎"
    entities = extract_entities(text, "Nike", {"zh": ["耐克"], "en": ["Nike"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("耐克" in name or "nike" in name.lower() for name in extracted_names), \
        f"Expected 耐克/Nike in {extracted_names}"
    assert any("jordan" in name.lower() or "air" in name.lower() for name in extracted_names), \
        f"Expected Air Jordan product in {extracted_names}"


def test_product_numbers_preserved():
    text = "Nike Air Force 1很经典，Jordan 4也很好看"
    entities = extract_entities(text, "Nike", {"zh": ["耐克"], "en": ["Nike"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("1" in name or "force" in name.lower() for name in extracted_names), \
        f"Expected Air Force 1 in {extracted_names}"


def test_hyphenated_products():
    text = "Salomon XT-6和New Balance 990v5都是好鞋"
    entities = extract_entities(text, "Salomon", {"zh": ["萨洛蒙"], "en": ["Salomon"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("xt" in name.lower() or "6" in name for name in extracted_names), \
        f"Expected XT-6 product in {extracted_names}"


def test_multiple_brands_in_comparison():
    text = "户外品牌对比：1. Nike跑鞋适合日常 2. Salomon适合越野 3. The North Face适合登山"
    entities = extract_entities(text, "Nike", {"zh": ["耐克"], "en": ["Nike"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("nike" in name.lower() for name in extracted_names), f"Expected Nike in {extracted_names}"
    assert any("salomon" in name.lower() for name in extracted_names), f"Expected Salomon in {extracted_names}"


def test_product_variant_not_merged_to_brand():
    text = "Nike Air Max 90比Nike Air Max 97更舒适"
    entities = extract_entities(text, "Nike", {"zh": ["耐克"], "en": ["Nike"]})
    extracted_names = set(entities.keys())

    print(f"Extracted: {extracted_names}")
    assert any("90" in name or "97" in name for name in extracted_names), \
        f"Expected Air Max 90/97 variants preserved in {extracted_names}"
