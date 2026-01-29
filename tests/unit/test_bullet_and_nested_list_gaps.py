"""Failing tests capturing bullet-marker inconsistencies and nested list splitting gaps."""

from services.brand_recognition import is_list_format, split_into_list_items, _list_table_candidates


def test_detects_bullet_list_with_bullet_dot():
    text = """• HOKA Kaha 2 Frost GTX
• SCARPA Mont Blanc Pro GTX
• Salomon Quest Arctic 2"""
    # Desired: treat common bullet dot "•" as list marker (currently not detected).
    assert is_list_format(text) is True


def test_splits_bullet_list_with_middle_dot():
    text = """· Oboz Bridger 10\"
· Danner Arctic 600
· Columbia Expeditionist Extreme"""
    # Desired: split "·" bullet lists into items (currently returns []).
    items = split_into_list_items(text)
    assert len(items) == 3
    assert "Oboz" in items[0]
    assert "Danner" in items[1]
    assert "Columbia" in items[2]


def test_list_candidate_extraction_supports_asterisk_bullets():
    text = """* HOKA Kaha 2 Frost GTX - warm and grippy
* SCARPA Mont Blanc Pro GTX - for extreme cold"""
    # Desired: list candidate regex should include "*" bullets consistently (currently omitted).
    candidates = _list_table_candidates(text)
    assert any("hoka" in c.lower() for c in candidates)


def test_nested_sublists_do_not_become_separate_items():
    text = """1. Scarpa Mont Blanc Pro GTX
    * 保暖/防滑兼顾：Vibram Arctic Grip大底
    * 适用：极端低温与技术性冰雪
2. Salomon Quest Arctic 2
    * 保暖/防滑兼顾：Contagrip Arctic Grip
    * 适用：冬季越野"""
    # Desired: only parent numbered items become list items; nested bullets stay attached
    # to their parent (not split into separate items).
    items = split_into_list_items(text)
    assert len(items) == 2
    assert "Scarpa Mont Blanc Pro GTX" in items[0]
    assert "保暖/防滑兼顾" in items[0]
    assert "Salomon Quest Arctic 2" in items[1]
    assert "Contagrip" in items[1]

