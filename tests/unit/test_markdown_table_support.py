"""Tests for Markdown table support in list detection and extraction."""

import pytest

from services.brand_recognition import extract_entities, is_list_format, split_into_list_items


@pytest.fixture(autouse=True)
def _disable_qwen_extraction(monkeypatch):
    from services.brand_recognition import config, orchestrator

    monkeypatch.setattr(config, "ENABLE_QWEN_EXTRACTION", False)
    monkeypatch.setattr(orchestrator, "ENABLE_QWEN_EXTRACTION", False)


def test_markdown_table_counts_as_list_format():
    text = """
| 排名 | 品牌型号 | 核心配置 |
| :-: | --- | --- |
| 1 | **Honda CRV** | similar to Toyota RAV4 |
| 2 | **VW ID.4** | comparable to BMW X5 |
"""
    assert is_list_format(text) is True


def test_markdown_table_splits_into_row_items():
    text = """
| Rank | Model | Notes |
| --- | --- | --- |
| 1 | **Honda CRV** | similar to Toyota RAV4 |
| 2 | **VW ID.4** | comparable to BMW X5 |
"""
    items = split_into_list_items(text)
    assert len(items) == 2
    assert "Honda CRV" in items[0]
    assert "VW ID.4" in items[1]


def test_markdown_table_triggers_list_filtering_in_extraction():
    text = """
| Rank | Model | Notes |
| --- | --- | --- |
| 1 | **Honda CRV** | similar to Toyota RAV4 |
| 2 | **VW ID.4** | comparable to BMW X5 |
"""
    entities = extract_entities(text, "Honda", {"zh": ["本田"], "en": ["Honda"]})
    extracted = {name.lower() for name in entities.all_entities().keys()}

    assert any("honda" in name for name in extracted)
    assert any("vw" == name or name.startswith("vw") for name in extracted)
    assert any("crv" in name or "cr-v" in name for name in extracted)
    assert any("id.4" in name for name in extracted)

    assert not any("toyota" in name for name in extracted)
    assert not any("rav4" in name for name in extracted)
    assert not any("bmw" in name for name in extracted)
    assert not any("x5" == name or name.endswith("x5") for name in extracted)

