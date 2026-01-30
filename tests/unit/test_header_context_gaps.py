"""Failing tests capturing header handling gaps (non-list headers)."""

import pytest

from services.brand_recognition import extract_entities, split_into_list_items


@pytest.fixture(autouse=True)
def _disable_qwen_extraction(monkeypatch):
    from services.brand_recognition import config, orchestrator

    monkeypatch.setattr(config, "ENABLE_QWEN_EXTRACTION", False)
    monkeypatch.setattr(orchestrator, "ENABLE_QWEN_EXTRACTION", False)


def test_markdown_heading_between_items_does_not_bleed_into_parent_item():
    text = """1. Honda CRV - great choice
### Toyota Recommended Picks
2. VW Tiguan - spacious interior
"""
    items = split_into_list_items(text)
    assert len(items) == 2
    assert "Honda CRV" in items[0]
    assert "Toyota Recommended Picks" not in items[0]


def test_emoji_heading_between_items_does_not_bleed_into_parent_item():
    text = """1. Honda CRV - great choice
🥾 Toyota Recommended Picks
2. VW Tiguan - spacious interior
"""
    items = split_into_list_items(text)
    assert len(items) == 2
    assert "Honda CRV" in items[0]
    assert "Toyota Recommended Picks" not in items[0]


def test_brand_in_non_list_header_is_still_allowed_during_list_filtering():
    text = """1. Honda CRV - great choice
### Toyota Recommended Picks
2. VW Tiguan - spacious interior
"""
    entities = extract_entities(text, "Honda", {"zh": ["本田"], "en": ["Honda"]})
    extracted_names = {name.lower() for name in entities.all_entities().keys()}

    # Desired behavior: header brands are treated as global context, not dropped.
    assert any("toyota" in name for name in extracted_names)

