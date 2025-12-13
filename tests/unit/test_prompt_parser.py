from ui.prompt_parser import parse_prompt_entries


def test_parse_prompt_entries_handles_chinese_lines():
    raw_prompts = "推荐几款SUV\n想了解新能源车\n\n请介绍大众车型"
    prompts = parse_prompt_entries(raw_prompts, "zh")
    assert len(prompts) == 3
    assert prompts[0] == {
        "text_zh": "推荐几款SUV",
        "text_en": None,
        "language_original": "zh",
    }
    assert prompts[1]["text_zh"] == "想了解新能源车"
    assert prompts[2]["text_zh"] == "请介绍大众车型"


def test_parse_prompt_entries_handles_english_lines():
    raw_prompts = "Recommend EVs worth buying\n\nCompare Model Y and iX3"
    prompts = parse_prompt_entries(raw_prompts, "en")
    assert len(prompts) == 2
    assert prompts[0] == {
        "text_zh": None,
        "text_en": "Recommend EVs worth buying",
        "language_original": "en",
    }
    assert prompts[1]["text_en"] == "Compare Model Y and iX3"
