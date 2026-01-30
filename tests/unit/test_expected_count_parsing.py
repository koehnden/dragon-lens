"""Test expected count parsing from text phrases like 'TOP 10' or '推荐10款'."""

import pytest

from services.brand_recognition.list_processor import (
    parse_expected_count,
    get_list_item_count,
)


class TestParseExpectedCount:
    """Tests for parse_expected_count function."""

    # English patterns
    def test_top_10_uppercase(self):
        text = "TOP 10 Best SUVs for 2025"
        assert parse_expected_count(text) == 10

    def test_top_5_lowercase(self):
        text = "Here are the top 5 smartphones to buy"
        assert parse_expected_count(text) == 5

    def test_top10_no_space(self):
        text = "Top10 brands in skincare"
        assert parse_expected_count(text) == 10

    def test_top_dash_10(self):
        text = "The top-10 electric vehicles"
        assert parse_expected_count(text) == 10

    def test_best_10(self):
        text = "The best 10 laptops for professionals"
        assert parse_expected_count(text) == 10

    def test_10_best(self):
        text = "10 best headphones under $200"
        assert parse_expected_count(text) == 10

    def test_10_top(self):
        text = "10 top rated TVs"
        assert parse_expected_count(text) == 10

    # Chinese numeric patterns
    def test_chinese_tuijian_10_kuan(self):
        text = "推荐10款值得购买的SUV"
        assert parse_expected_count(text) == 10

    def test_chinese_10_da_tuijian(self):
        text = "10大推荐护肤品牌"
        assert parse_expected_count(text) == 10

    def test_chinese_qian_10_ming(self):
        text = "前10名最受欢迎的手机品牌"
        assert parse_expected_count(text) == 10

    def test_chinese_top_10(self):
        text = "2025年TOP10最佳电动汽车"
        assert parse_expected_count(text) == 10

    def test_chinese_10_kuan_tuijian(self):
        text = "10款推荐的高性价比手机"
        assert parse_expected_count(text) == 10

    def test_chinese_10_ge_tuijian(self):
        text = "10个推荐的护肤产品"
        assert parse_expected_count(text) == 10

    def test_chinese_paiming_qian_10(self):
        text = "排名前10的国产汽车品牌"
        assert parse_expected_count(text) == 10

    def test_chinese_10_qiang(self):
        text = "国产手机品牌10强排行榜"
        assert parse_expected_count(text) == 10

    # Chinese number word patterns
    def test_chinese_shi_da_pinpai(self):
        text = "十大品牌推荐"
        assert parse_expected_count(text) == 10

    def test_chinese_wu_da_pinpai(self):
        text = "五大品牌对比"
        assert parse_expected_count(text) == 5

    def test_chinese_shi_da_tuijian(self):
        text = "十大推荐SUV车型"
        assert parse_expected_count(text) == 10

    def test_chinese_shi_kuan_tuijian(self):
        text = "十款推荐护肤品"
        assert parse_expected_count(text) == 10

    # Edge cases
    def test_no_pattern_returns_none(self):
        text = "Here are some recommended products for you"
        assert parse_expected_count(text) is None

    def test_pattern_after_500_chars_not_matched(self):
        text = "A" * 500 + " TOP 10 products"
        assert parse_expected_count(text) is None

    def test_pattern_within_500_chars_matched(self):
        text = "A" * 400 + " TOP 10 products"
        assert parse_expected_count(text) == 10

    def test_first_pattern_wins(self):
        text = "TOP 5 best products out of TOP 10 reviewed"
        assert parse_expected_count(text) == 5

    def test_empty_text(self):
        assert parse_expected_count("") is None

    def test_mixed_english_chinese_prefers_first(self):
        text = "TOP 5 推荐10款产品"
        assert parse_expected_count(text) == 5


class TestGetListItemCount:
    """Tests for get_list_item_count function."""

    def test_numbered_list(self):
        text = """
        1. First item
        2. Second item
        3. Third item
        """
        assert get_list_item_count(text) == 3

    def test_bullet_list(self):
        text = """
        - First item
        - Second item
        - Third item
        - Fourth item
        """
        assert get_list_item_count(text) == 4

    def test_chinese_numbered_list(self):
        text = """
        1、比亚迪
        2、蔚来
        3、小鹏
        """
        assert get_list_item_count(text) == 3

    def test_not_a_list(self):
        text = "This is just a regular paragraph with no list items."
        assert get_list_item_count(text) == 0

    def test_empty_text(self):
        assert get_list_item_count("") == 0

    def test_single_item_not_a_list(self):
        text = "1. Single item"
        # Need at least 2 items to be considered a list
        assert get_list_item_count(text) == 0

    def test_mixed_list_formats(self):
        text = """
        1. First numbered
        2. Second numbered
        - Bullet item
        - Another bullet
        """
        # Should detect the numbered list pattern (2 items meet threshold)
        count = get_list_item_count(text)
        assert count >= 2
