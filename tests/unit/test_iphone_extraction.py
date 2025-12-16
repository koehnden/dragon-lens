from services.brand_recognition import generate_candidates, _regex_candidates, _list_table_candidates


def test_iphone14_extraction():
    text = "1. iPhone14 Pro - 拍照效果优秀"

    regex_hits = _regex_candidates(text)
    print(f"Regex hits: {regex_hits}")

    list_hits = _list_table_candidates(text)
    print(f"List hits: {list_hits}")

    candidates = generate_candidates(text, "iPhone", {"zh": ["苹果"], "en": ["iPhone"]})
    candidate_names = {c.name for c in candidates}
    print(f"All candidates: {candidate_names}")

    assert any("iphone14" in name.lower() for name in candidate_names), f"Expected iPhone14 in {candidate_names}"
