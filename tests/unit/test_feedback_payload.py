from ui.feedback_payload import (
    build_brand_feedback,
    build_feedback_payload,
    build_mapping_feedback,
    build_product_feedback,
    build_translation_overrides,
)


def test_build_brand_feedback_valid():
    rows = [{"name": "Toyota", "action": "valid", "reason": ""}]
    assert build_brand_feedback(rows) == [
        {"action": "validate", "name": "Toyota", "reason": None}
    ]


def test_build_brand_feedback_replace():
    rows = [
        {"name": "Toyta", "action": "wrong", "correct_name": "Toyota", "reason": "typo"}
    ]
    assert build_brand_feedback(rows) == [
        {
            "action": "replace",
            "wrong_name": "Toyta",
            "correct_name": "Toyota",
            "reason": "typo",
        }
    ]


def test_build_product_feedback_skip_missing():
    rows = [{"name": "RAV4", "action": "wrong", "correct_name": ""}]
    assert build_product_feedback(rows) == []


def test_build_mapping_feedback():
    existing = [{"product_name": "RAV4", "brand_name": "Toyota", "action": "wrong"}]
    missing = [
        {
            "product_name": "CRV",
            "brand_name": "Honda",
            "action": "add",
            "reason": "missing",
        }
    ]
    assert build_mapping_feedback(existing, missing) == [
        {
            "action": "reject",
            "product_name": "RAV4",
            "brand_name": "Toyota",
            "reason": None,
        },
        {
            "action": "add",
            "product_name": "CRV",
            "brand_name": "Honda",
            "reason": "missing",
        },
    ]


def test_build_mapping_feedback_validate():
    existing = [
        {
            "product_name": "RAV4",
            "brand_name": "Toyota",
            "action": "valid",
            "reason": "ok",
        }
    ]
    missing: list[dict] = []
    assert build_mapping_feedback(existing, missing) == [
        {
            "action": "validate",
            "product_name": "RAV4",
            "brand_name": "Toyota",
            "reason": "ok",
        },
    ]


def test_build_translation_overrides():
    rows = [
        {
            "entity_type": "brand",
            "canonical_name": "丰田",
            "language": "en",
            "override_text": "Toyota",
        }
    ]
    assert build_translation_overrides(rows) == [
        {
            "entity_type": "brand",
            "canonical_name": "丰田",
            "language": "en",
            "override_text": "Toyota",
            "reason": None,
        }
    ]


def test_build_translation_overrides_valid_uses_current_translation():
    rows = [
        {
            "entity_type": "brand",
            "canonical_name": "丰田",
            "language": "en",
            "action": "valid",
            "current_translation_en": "Toyota",
            "override_text": "",
        }
    ]
    assert build_translation_overrides(rows) == [
        {
            "entity_type": "brand",
            "canonical_name": "丰田",
            "language": "en",
            "override_text": "Toyota",
            "reason": None,
        }
    ]


def test_build_feedback_payload():
    payload = build_feedback_payload(
        10,
        5,
        {"id": 3, "is_new": False},
        [{"name": "Toyota", "action": "valid"}],
        [],
        [],
        [],
        [],
    )
    assert payload["run_id"] == 10
    assert payload["vertical_id"] == 5
    assert payload["canonical_vertical"]["id"] == 3
    assert payload["brand_feedback"][0]["name"] == "Toyota"
