from services.comparison_prompts.text_parser import parse_text_zh_list_from_text


def test_parse_text_zh_list_from_text_extracts_dict_items():
    raw = '[{"text_zh":"对比A和B的油耗"},{"text_zh":"  "},{"x":1}]'
    assert parse_text_zh_list_from_text(raw) == ["对比A和B的油耗"]


def test_parse_text_zh_list_from_text_accepts_string_items():
    raw = '["A","B"]'
    assert parse_text_zh_list_from_text(raw) == ["A", "B"]

