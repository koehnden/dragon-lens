from services.brand_recognition.consolidation_service import _parse_normalization_response


def test_rejects_invented_english_meaning_translation():
    response = """
    {
      "brands": [{"canonical": "Curiosity", "chinese": "好奇", "original_forms": ["好奇"]}],
      "rejected": []
    }
    """
    result = _parse_normalization_response(response, ["好奇"], {"好奇"})
    assert result.normalized_brands["好奇"] == "好奇"


def test_allows_canonical_from_inputs_to_merge_bilingual_variants():
    response = """
    {
      "brands": [{"canonical": "Huggies", "chinese": "好奇", "original_forms": ["好奇", "Huggies"]}],
      "rejected": []
    }
    """
    allowed = {"好奇", "Huggies"}
    result = _parse_normalization_response(response, ["好奇", "Huggies"], allowed)
    assert result.normalized_brands["好奇"] == "Huggies"
    assert result.normalized_brands["Huggies"] == "Huggies"


def test_allows_chinese_substring_extraction_for_jv_normalization():
    response = """
    {
      "brands": [{"canonical": "大众", "chinese": "", "original_forms": ["一汽大众"]}],
      "rejected": []
    }
    """
    result = _parse_normalization_response(response, ["一汽大众"], {"一汽大众"})
    assert result.normalized_brands["一汽大众"] == "大众"


def test_rejects_invented_pinyin():
    response = """
    {
      "brands": [{"canonical": "Moyi Shu", "chinese": "妙而舒", "original_forms": ["妙而舒"]}],
      "rejected": []
    }
    """
    result = _parse_normalization_response(response, ["妙而舒"], {"妙而舒"})
    assert result.normalized_brands["妙而舒"] == "妙而舒"

