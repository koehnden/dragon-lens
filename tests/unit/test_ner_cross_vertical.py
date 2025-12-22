"""Test NER filtering across different verticals to ensure generalizability."""

import pytest

from services.brand_recognition import extract_entities


def test_beauty_skincare_vertical():
    """Test NER filtering generalizes to beauty/skincare vertical."""
    response = """
    敏感肌保湿推荐TOP 5：

    1. Loreal复颜系列 - 保湿效果好，质地轻薄，吸收速度快
    2. Shiseido红腰子 - 美白成分丰富，肤感舒适
    3. 珀莱雅红宝石 - 性价比高，温和性好，适合敏感肌

    这些产品的成分配置、使用体验、吸收效果都值得关注。
    """

    entities = extract_entities(response, "Loreal", {"zh": ["欧莱雅"], "en": ["Loreal"]})
    extracted_names = set(entities.keys())

    assert any("loreal" in name.lower() or "欧莱雅" in name.lower() for name in extracted_names), f"Expected Loreal in {extracted_names}"
    assert any("shiseido" in name.lower() for name in extracted_names), f"Expected Shiseido in {extracted_names}"
    assert any("珀莱雅" in name.lower() for name in extracted_names), f"Expected 珀莱雅 in {extracted_names}"

    assert not any("保湿效果" in name for name in extracted_names), f"Should filter '保湿效果' but found in {extracted_names}"
    assert not any("质地" in name for name in extracted_names), f"Should filter '质地' but found in {extracted_names}"
    assert not any("速度" in name for name in extracted_names), f"Should filter '速度' but found in {extracted_names}"
    assert not any("功能" in name for name in extracted_names), f"Should filter '功能' but found in {extracted_names}"
    assert not any("效果" in name for name in extracted_names), f"Should filter '效果' but found in {extracted_names}"
    assert not any("温和性" in name for name in extracted_names), f"Should filter '温和性' but found in {extracted_names}"
    assert not any("成分" in name for name in extracted_names), f"Should filter '成分' but found in {extracted_names}"
    assert not any("体验" in name for name in extracted_names), f"Should filter '体验' but found in {extracted_names}"


def test_smartphones_electronics_vertical():
    """Test NER filtering generalizes to smartphones/electronics vertical."""
    response = """
    2024中国最佳拍照手机排行：

    1. iPhone14 Pro - 拍照效果优秀，系统流畅度高，续航时间长
    2. 华为Mate50 Pro - 处理器性能强劲，屏幕分辨率高
    3. 小米13 Ultra - 性价比出色，充电速度快
    4. Samsung S23 - 显示效果好，色彩表现优秀

    这些手机的电池容量、屏幕质量、拍摄功能都很重要。
    """

    entities = extract_entities(response, "iPhone", {"zh": ["苹果"], "en": ["iPhone", "Apple"]})
    extracted_names = set(entities.keys())

    assert any("iphone" in name.lower() for name in extracted_names), f"Expected iPhone in {extracted_names}"
    assert any("14" in name and "pro" in name.lower() for name in extracted_names), f"Expected 14 Pro in {extracted_names}"
    assert any("mate" in name.lower() or ("50" in name and "pro" in name.lower()) for name in extracted_names), f"Expected Mate50 Pro in {extracted_names}"
    assert any("ultra" in name.lower() for name in extracted_names), f"Expected Ultra variant in {extracted_names}"
    assert any("s23" in name.lower() for name in extracted_names), f"Expected S23 in {extracted_names}"

    assert not any("效果" in name for name in extracted_names), f"Should filter '效果' but found in {extracted_names}"
    assert not any("流畅" in name for name in extracted_names), f"Should filter '流畅' but found in {extracted_names}"
    assert not any("时间" in name for name in extracted_names), f"Should filter '时间' but found in {extracted_names}"
    assert not any("性能" in name for name in extracted_names), f"Should filter '性能' but found in {extracted_names}"
    assert not any("速度" in name for name in extracted_names), f"Should filter '速度' but found in {extracted_names}"
    assert not any("容量" in name for name in extracted_names), f"Should filter '容量' but found in {extracted_names}"
    assert not any("功能" in name for name in extracted_names), f"Should filter '功能' but found in {extracted_names}"


def test_pet_care_vertical():
    """Test NER filtering generalizes to pet care vertical."""
    response = """
    敏感肠胃猫粮推荐：

    1. RoyalCanin处方粮 - 营养成分均衡，适口性好，消化吸收率高
    2. Purina猫粮 - 毛发光泽度提升明显，粪便质量改善
    3. 渴望六种鱼 - 蛋白质含量高，口感好

    选择猫粮时要关注成分配置、营养均衡性、消化率等指标。
    """

    entities = extract_entities(response, "RoyalCanin", {"zh": ["皇家"], "en": ["RoyalCanin"]})
    extracted_names = set(entities.keys())

    assert any("royal" in name.lower() or "canin" in name.lower() for name in extracted_names), f"Expected RoyalCanin in {extracted_names}"
    assert any("purina" in name.lower() for name in extracted_names), f"Expected Purina in {extracted_names}"

    assert not any("成分" in name for name in extracted_names), f"Should filter '成分' but found in {extracted_names}"
    assert not any("口感" in name for name in extracted_names), f"Should filter '口感' but found in {extracted_names}"
    assert not any("光泽" in name for name in extracted_names), f"Should filter '光泽' but found in {extracted_names}"
    assert not any("质量" in name for name in extracted_names), f"Should filter '质量' but found in {extracted_names}"
    assert not any("含量" in name for name in extracted_names), f"Should filter '含量' but found in {extracted_names}"
    assert not any("配置" in name for name in extracted_names), f"Should filter '配置' but found in {extracted_names}"
    assert not any("率" in name for name in extracted_names), f"Should filter 'XX率' but found in {extracted_names}"


def test_home_appliances_vertical():
    """Test NER filtering generalizes to home appliances vertical."""
    response = """
    扫地机器人推荐（适合养宠家庭）：

    1. Dyson V15 - 吸力强劲，续航时间长，噪音控制好
    2. Roomba扫地机 - 智能路径规划，清扫效果出色
    3. 科沃斯X1 - 拖地功能好，性价比高，操作便利性强

    选购时需要关注吸力大小、电池容量、噪音水平等因素。
    """

    entities = extract_entities(response, "Dyson", {"zh": ["戴森"], "en": ["Dyson"]})
    extracted_names = set(entities.keys())

    assert any("dyson" in name.lower() for name in extracted_names), f"Expected Dyson in {extracted_names}"
    assert any("v15" in name.lower() for name in extracted_names), f"Expected V15 in {extracted_names}"
    assert any("roomba" in name.lower() for name in extracted_names), f"Expected Roomba in {extracted_names}"
    assert any("科沃斯" in name for name in extracted_names), f"Expected 科沃斯 in {extracted_names}"
    assert any("x1" in name.lower() for name in extracted_names), f"Expected X1 in {extracted_names}"

    assert not any("吸力" in name for name in extracted_names), f"Should filter '吸力' but found in {extracted_names}"
    assert not any("时间" in name for name in extracted_names), f"Should filter '时间' but found in {extracted_names}"
    assert not any("控制" in name for name in extracted_names), f"Should filter '控制' but found in {extracted_names}"
    assert not any("效果" in name for name in extracted_names), f"Should filter '效果' but found in {extracted_names}"
    assert not any("功能" in name for name in extracted_names), f"Should filter '功能' but found in {extracted_names}"
    assert not any("容量" in name for name in extracted_names), f"Should filter '容量' but found in {extracted_names}"


def test_health_wellness_vertical():
    """Test NER filtering generalizes to health & wellness vertical."""
    response = """
    胶原蛋白补剂推荐：

    1. Swisse胶原蛋白 - 吸收效果好，口感不错，含量充足
    2. GNC补剂 - 成分纯度高，品质可靠性强
    3. 汤臣倍健 - 国产品牌，性价比优秀

    选择时要注意成分含量、吸收率、安全性等方面。
    """

    entities = extract_entities(response, "Swisse", {"zh": ["瑞思"], "en": ["Swisse"]})
    extracted_names = set(entities.keys())

    assert any("swisse" in name.lower() for name in extracted_names), f"Expected Swisse in {extracted_names}"
    assert any("gnc" in name.lower() for name in extracted_names), f"Expected GNC in {extracted_names}"
    assert any("汤臣倍健" in name.lower() for name in extracted_names), f"Expected 汤臣倍健 in {extracted_names}"

    assert not any("效果" in name for name in extracted_names), f"Should filter '效果' but found in {extracted_names}"
    assert not any("口感" in name for name in extracted_names), f"Should filter '口感' but found in {extracted_names}"
    assert not any("成分" in name for name in extracted_names), f"Should filter '成分' but found in {extracted_names}"
    assert not any("纯度" in name for name in extracted_names), f"Should filter '纯度' but found in {extracted_names}"
    assert not any("可靠性" in name for name in extracted_names), f"Should filter '可靠性' but found in {extracted_names}"
    assert not any("安全性" in name for name in extracted_names), f"Should filter '安全性' but found in {extracted_names}"
    assert not any("含量" in name for name in extracted_names), f"Should filter '含量' but found in {extracted_names}"
    assert not any("率" in name for name in extracted_names), f"Should filter 'XX率' but found in {extracted_names}"
