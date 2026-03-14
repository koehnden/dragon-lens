"""Tests for Markdown table support in list detection and extraction."""

import pytest

from services.brand_recognition import is_list_format, split_into_list_items


@pytest.fixture(autouse=True)
def _disable_qwen_extraction(monkeypatch):
    from services.brand_recognition import config

    monkeypatch.setattr(config, "ENABLE_QWEN_EXTRACTION", False)


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

