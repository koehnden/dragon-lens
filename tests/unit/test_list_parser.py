from services.brand_recognition import _list_table_candidates


def test_list_parser_numbered_items():
    text = """
    1. Loreal复颜系列 - 保湿效果好
    2. Shiseido红腰子 - 美白成分丰富
    3. 珀莱雅红宝石 - 性价比高
    """

    candidates = _list_table_candidates(text)
    print(f"Extracted: {candidates}")

    assert any("loreal" in c.lower() for c in candidates), f"Expected Loreal in {candidates}"
    assert any("shiseido" in c.lower() for c in candidates), f"Expected Shiseido in {candidates}"
    assert any("珀莱雅" in c for c in candidates), f"Expected 珀莱雅 in {candidates}"


def test_list_parser_with_standalone_brands():
    text = """
    1. Dyson V15 - 吸力强劲
    2. Roomba扫地机 - 智能路径规划
    3. 科沃斯X1 - 拖地功能好
    """

    candidates = _list_table_candidates(text)
    print(f"Extracted: {candidates}")

    assert any("dyson" in c.lower() for c in candidates), f"Expected Dyson in {candidates}"
    assert any("roomba" in c.lower() for c in candidates), f"Expected Roomba in {candidates}"
    assert any("科沃斯" in c for c in candidates), f"Expected 科沃斯 in {candidates}"


def test_list_parser_pet_food():
    text = """
    1. RoyalCanin处方粮 - 营养成分均衡
    2. Purina猫粮 - 毛发光泽度提升明显
    3. 渴望六种鱼 - 蛋白质含量高
    """

    candidates = _list_table_candidates(text)
    print(f"Extracted: {candidates}")

    assert any("royal" in c.lower() or "canin" in c.lower() for c in candidates), f"Expected RoyalCanin in {candidates}"
    assert any("purina" in c.lower() for c in candidates), f"Expected Purina in {candidates}"
