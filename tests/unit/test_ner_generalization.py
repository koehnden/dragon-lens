"""Test that NER filtering uses generalized linguistic patterns, not vertical-specific lists."""

import pytest

from services.brand_recognition import extract_entities


def test_filters_feature_suffixes_across_verticals():
    """Test that XX性, XX度, XX率, XX感, XX力 patterns filter correctly across verticals."""
    responses = [
        ("汽车", "比亚迪的安全性和可靠性都很好，舒适性也不错，保值率高。"),
        ("护肤", "这款面霜的保湿性很好，温和性不错，吸收效果度高，滋润感强。"),
        ("电子", "这款手机的流畅性出色，续航能力强，充电速度快。"),
    ]

    for vertical, response in responses:
        entities = extract_entities(response, "", {})
        extracted_names = set(entities.all_entities().keys())

        assert not any("性" in name and len(name) <= 4 for name in extracted_names), f"{vertical}: Should filter 'XX性' patterns but found in {extracted_names}"
        assert not any("度" in name and len(name) <= 4 for name in extracted_names), f"{vertical}: Should filter 'XX度' patterns but found in {extracted_names}"
        assert not any("率" in name and len(name) <= 4 for name in extracted_names), f"{vertical}: Should filter 'XX率' patterns but found in {extracted_names}"
        assert not any("感" in name and len(name) <= 4 for name in extracted_names), f"{vertical}: Should filter 'XX感' patterns but found in {extracted_names}"
        assert not any("力" in name and len(name) <= 4 for name in extracted_names), f"{vertical}: Should filter 'XX力' patterns but found in {extracted_names}"


def test_filters_feature_descriptor_words_across_verticals():
    """Test that 效果/功能/成分/配置/体验/表现/质地/口感 filter correctly."""
    responses = [
        ("汽车", "这款车的动力表现出色，油耗表现优秀，配置丰富。"),
        ("护肤", "这款面霜的保湿效果很好，质地轻薄，使用体验舒适。"),
        ("食品", "这款猫粮的营养成分均衡，适口性好，口感不错。"),
        ("电子", "这款手机的拍照效果优秀，系统体验流畅，续航表现好。"),
    ]

    for vertical, response in responses:
        entities = extract_entities(response, "", {})
        extracted_names = set(entities.all_entities().keys())

        assert not any("效果" in name for name in extracted_names), f"{vertical}: Should filter '效果' but found in {extracted_names}"
        assert not any("功能" in name for name in extracted_names), f"{vertical}: Should filter '功能' but found in {extracted_names}"
        assert not any("成分" in name for name in extracted_names), f"{vertical}: Should filter '成分' but found in {extracted_names}"
        assert not any("配置" in name for name in extracted_names), f"{vertical}: Should filter '配置' but found in {extracted_names}"
        assert not any("体验" in name for name in extracted_names), f"{vertical}: Should filter '体验' but found in {extracted_names}"
        assert not any("表现" in name for name in extracted_names), f"{vertical}: Should filter '表现' but found in {extracted_names}"
        assert not any("质地" in name for name in extracted_names), f"{vertical}: Should filter '质地' but found in {extracted_names}"
        assert not any("口感" in name for name in extracted_names), f"{vertical}: Should filter '口感' but found in {extracted_names}"


def test_keeps_brand_product_patterns_across_verticals():
    """Test that brand/product naming patterns (PLUS/Pro/Max + numbers) work across verticals."""
    test_cases = [
        ("汽车", "宋PLUS很受欢迎", ["plus"]),
        ("汽车", "理想L7都很受欢迎", ["l7"]),
        ("家电", "科沃斯X1清扫效果好", ["x1"]),
    ]

    for vertical, response, expected_patterns in test_cases:
        entities = extract_entities(response, "", {})
        extracted_names_lower = {name.lower().replace(" ", "") for name in entities.all_entities().keys()}

        for pattern in expected_patterns:
            assert any(pattern in name for name in extracted_names_lower), f"{vertical}: Expected to extract pattern '{pattern}' but got {extracted_names_lower}"


def test_filters_measurement_descriptor_words():
    """Test that 空间/时间/速度/距离/重量/容量/尺寸 filter correctly."""
    responses = [
        ("汽车", "后排空间大，加速时间短，刹车距离合理。"),
        ("电子", "电池容量大，充电速度快，屏幕尺寸合适，机身重量轻。"),
        ("家电", "储存容量大，运行速度快，占用空间小。"),
    ]

    for vertical, response in responses:
        entities = extract_entities(response, "", {})
        extracted_names = set(entities.all_entities().keys())

        assert not any("空间" in name for name in extracted_names), f"{vertical}: Should filter '空间' but found in {extracted_names}"
        assert not any("时间" in name for name in extracted_names), f"{vertical}: Should filter '时间' but found in {extracted_names}"
        assert not any("速度" in name for name in extracted_names), f"{vertical}: Should filter '速度' but found in {extracted_names}"
        assert not any("距离" in name for name in extracted_names), f"{vertical}: Should filter '距离' but found in {extracted_names}"
        assert not any("重量" in name for name in extracted_names), f"{vertical}: Should filter '重量' but found in {extracted_names}"
        assert not any("容量" in name for name in extracted_names), f"{vertical}: Should filter '容量' but found in {extracted_names}"
        assert not any("尺寸" in name for name in extracted_names), f"{vertical}: Should filter '尺寸' but found in {extracted_names}"


def test_filters_quality_adjectives():
    """Test that quality adjectives like 良好/优秀/出色/卓越/强劲 filter correctly."""
    responses = [
        ("汽车", "动力强劲，品质卓越，做工优秀。"),
        ("护肤", "效果出色，品质良好。"),
        ("电子", "性能强劲，表现优秀。"),
    ]

    for vertical, response in responses:
        entities = extract_entities(response, "", {})
        extracted_names = set(entities.all_entities().keys())

        assert not any("良好" in name for name in extracted_names), f"{vertical}: Should filter '良好' but found in {extracted_names}"
        assert not any("优秀" in name for name in extracted_names), f"{vertical}: Should filter '优秀' but found in {extracted_names}"
        assert not any("出色" in name for name in extracted_names), f"{vertical}: Should filter '出色' but found in {extracted_names}"
        assert not any("卓越" in name for name in extracted_names), f"{vertical}: Should filter '卓越' but found in {extracted_names}"
        assert not any("强劲" in name for name in extracted_names), f"{vertical}: Should filter '强劲' but found in {extracted_names}"
