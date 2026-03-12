"""Failing tests capturing header handling gaps (non-list headers)."""

import pytest

from services.brand_recognition import split_into_list_items


@pytest.fixture(autouse=True)
def _disable_qwen_extraction(monkeypatch):
    from services.brand_recognition import config

    monkeypatch.setattr(config, "ENABLE_QWEN_EXTRACTION", False)


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
