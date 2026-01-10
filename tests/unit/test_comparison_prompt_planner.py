from services.comparison_prompts import (
    base_generation_count,
    competitor_missing_counts,
    parse_comparison_prompts_from_text,
    total_generation_count,
)


def test_base_generation_count_when_user_has_less_than_target():
    assert base_generation_count(20, 5) == 15


def test_base_generation_count_when_user_exceeds_target():
    assert base_generation_count(20, 25) == 0


def test_competitor_missing_counts_enforces_minimum():
    missing = competitor_missing_counts(["A", "B"], {"A": 1}, 2)
    assert missing == {"A": 1, "B": 2}


def test_total_generation_count_exceeds_target_to_satisfy_competitor_minimums():
    missing = competitor_missing_counts(["A", "B", "C"], {}, 2)
    assert total_generation_count(20, 19, missing) == 6


def test_parse_comparison_prompts_from_text_extracts_json_array_and_filters():
    raw = "```json\n[{\"text_zh\":\"你好\",\"text_en\":\"Hello\"},{\"text_zh\":\"\",\"text_en\":\"x\"}]\n```"
    assert parse_comparison_prompts_from_text(raw) == [
        {
            "text_zh": "你好",
            "text_en": "Hello",
            "prompt_type": "brand_vs_brand",
            "primary_brand": "",
            "competitor_brand": "",
            "primary_product": "",
            "competitor_product": "",
            "aspects": [],
        }
    ]
