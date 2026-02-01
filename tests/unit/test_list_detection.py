"""Test list/bullet point detection in LLM responses."""

import pytest

from services.brand_recognition import is_list_format, split_into_list_items


class TestIsListFormat:

    def test_detects_numbered_list_with_period(self):
        text = """1. Honda CRV is great
2. Toyota RAV4 is reliable
3. VW Tiguan is spacious"""
        assert is_list_format(text) is True

    def test_detects_numbered_list_with_fullwidth_period(self):
        text = """１． Honda CRV is great
２． Toyota RAV4 is reliable
３． VW Tiguan is spacious"""
        assert is_list_format(text) is True

    def test_detects_numbered_list_with_fullwidth_parenthesis(self):
        text = """1） Nike Air Max
2） Adidas Ultraboost
3） New Balance 990"""
        assert is_list_format(text) is True

    def test_detects_numbered_list_with_parenthesis(self):
        text = """1) Nike Air Max
2) Adidas Ultraboost
3) New Balance 990"""
        assert is_list_format(text) is True

    def test_detects_dash_bullet_list(self):
        text = """- iPhone 15 Pro
- Samsung Galaxy S24
- Google Pixel 8"""
        assert is_list_format(text) is True

    def test_detects_asterisk_bullet_list(self):
        text = """* Loreal Paris
* Maybelline
* Estee Lauder"""
        assert is_list_format(text) is True

    def test_detects_chinese_numbered_list(self):
        text = """1、比亚迪宋PLUS
2、大众途观L
3、丰田RAV4"""
        assert is_list_format(text) is True

    def test_detects_chinese_bullet_list(self):
        text = """・理想L7
・蔚来ES6
・小鹏G9"""
        assert is_list_format(text) is True

    def test_detects_mixed_format_list(self):
        text = """Here are the top SUVs:
1. Honda CRV - great family car
2. Toyota RAV4 - reliable choice
3. VW Tiguan - good value"""
        assert is_list_format(text) is True

    def test_rejects_plain_paragraph(self):
        text = """Honda makes great cars. Toyota is also reliable.
Many families choose SUVs for their versatility."""
        assert is_list_format(text) is False

    def test_rejects_single_item(self):
        text = """1. Honda CRV is the best choice for families."""
        assert is_list_format(text) is False

    def test_detects_list_with_minimum_two_items(self):
        text = """1. Honda CRV
2. Toyota RAV4"""
        assert is_list_format(text) is True

    def test_detects_circle_bullet_list(self):
        text = """○ Royal Canin
○ Hill's Science Diet
○ Blue Buffalo"""
        assert is_list_format(text) is True

    def test_detects_arrow_bullet_list(self):
        text = """→ Dyson V15
→ Shark Navigator
→ Roomba i7"""
        assert is_list_format(text) is True


class TestSplitIntoListItems:

    def test_splits_numbered_list_with_period(self):
        text = """1. Honda CRV is great
2. Toyota RAV4 is reliable
3. VW Tiguan is spacious"""
        items = split_into_list_items(text)
        assert len(items) == 3
        assert "Honda CRV" in items[0]
        assert "Toyota RAV4" in items[1]
        assert "VW Tiguan" in items[2]

    def test_splits_numbered_list_with_fullwidth_period(self):
        text = """１． Honda CRV is great
２． Toyota RAV4 is reliable
３． VW Tiguan is spacious"""
        items = split_into_list_items(text)
        assert len(items) == 3
        assert "Honda CRV" in items[0]
        assert "Toyota RAV4" in items[1]
        assert "VW Tiguan" in items[2]

    def test_splits_numbered_list_with_fullwidth_parenthesis(self):
        text = """1） Nike Air Max
2） Adidas Ultraboost
3） New Balance 990"""
        items = split_into_list_items(text)
        assert len(items) == 3
        assert "Nike Air Max" in items[0]
        assert "Adidas Ultraboost" in items[1]
        assert "New Balance 990" in items[2]

    def test_splits_dash_bullet_list(self):
        text = """- iPhone 15 Pro is the flagship
- Samsung Galaxy S24 offers great value
- Google Pixel 8 has best camera"""
        items = split_into_list_items(text)
        assert len(items) == 3
        assert "iPhone 15 Pro" in items[0]
        assert "Samsung Galaxy S24" in items[1]
        assert "Google Pixel 8" in items[2]

    def test_splits_chinese_numbered_list(self):
        text = """1、比亚迪宋PLUS是首选
2、大众途观L性价比高
3、丰田RAV4可靠耐用"""
        items = split_into_list_items(text)
        assert len(items) == 3
        assert "比亚迪宋PLUS" in items[0]
        assert "大众途观L" in items[1]
        assert "丰田RAV4" in items[2]

    def test_preserves_content_with_intro_paragraph(self):
        text = """Here are the top recommendations:
1. Honda CRV - family favorite
2. Toyota RAV4 - reliable"""
        items = split_into_list_items(text)
        assert len(items) == 2
        assert "Honda CRV" in items[0]

    def test_splits_asterisk_list(self):
        text = """* Nike Air Max 90
* Adidas Ultraboost 22
* New Balance 990v5"""
        items = split_into_list_items(text)
        assert len(items) == 3

    def test_returns_empty_for_non_list(self):
        text = """This is just a regular paragraph about cars."""
        items = split_into_list_items(text)
        assert items == []

    def test_splits_multiline_list_items(self):
        text = """1. Honda CRV - This is a great SUV
  	   with excellent fuel economy.
2. Toyota RAV4 - Known for
  	   reliability and longevity."""
        items = split_into_list_items(text)
        assert len(items) == 2
        assert "fuel economy" in items[0]
        assert "reliability" in items[1]

    def test_does_not_collapse_top_level_numbered_items_with_indent_jitter(self):
        text = """1. Alpha
  2. Beta
   3. Gamma"""
        items = split_into_list_items(text)
        assert len(items) == 3
        assert "Alpha" in items[0]
        assert "Beta" in items[1]
        assert "Gamma" in items[2]

    def test_handles_chinese_list_markers(self):
        text = """・Royal Canin成猫粮
・Hill's Science Diet
・蓝氏Blue Buffalo"""
        items = split_into_list_items(text)
        assert len(items) == 3
