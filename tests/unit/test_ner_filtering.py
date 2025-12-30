"""Test NER filtering to ensure only brands/products are extracted."""

import pytest

from services.brand_recognition import extract_entities


def test_filters_feature_descriptions_keeps_brands():
    """Test that feature descriptions are filtered while brand names are kept."""
    response = """
    在中国市场，家庭用SUV首选推荐如下TOP10：

    1. 比亚迪宋PLUS - 配置丰富度高，全液晶仪表盘等高端配置齐全，智能座舱体验优秀
    2. 大众途观L - 空间表现出色，安全性能可靠，保值率高
    3. 丰田RAV4 - 可靠性优秀，油耗经济，操控性好
    4. 本田CR-V - 后排舒适度佳，后备箱空间大
    5. 理想L7 - 智能驾驶辅助系统先进
    """

    entities = extract_entities(response, "比亚迪", {"zh": ["BYD"], "en": ["BYD"]})
    extracted_names = set(entities.all_entities().keys())

    # Should keep brands and products
    assert any("比亚迪" in name.lower() for name in extracted_names), f"Expected BYD brand in {extracted_names}"
    assert any("宋" in name and "plus" in name.lower() for name in extracted_names), f"Expected Song PLUS in {extracted_names}"
    assert any("丰田" in name.lower() or "toyota" in name.lower() for name in extracted_names), f"Expected Toyota in {extracted_names}"
    assert any("rav" in name.lower() and "4" in name for name in extracted_names), f"Expected RAV4 in {extracted_names}"
    assert any("理想" in name.lower() or ("l" in name.lower() and "7" in name) for name in extracted_names), f"Expected Li Auto/L7 in {extracted_names}"

    # Should NOT keep feature descriptions
    assert not any("配置丰富" in name for name in extracted_names), f"Should filter '配置丰富' but found in {extracted_names}"
    assert not any("液晶仪表盘" in name for name in extracted_names), f"Should filter '液晶仪表盘' but found in {extracted_names}"
    assert not any("高端配置" in name for name in extracted_names), f"Should filter '高端配置' but found in {extracted_names}"
    assert not any("智能座舱" in name for name in extracted_names), f"Should filter '智能座舱' but found in {extracted_names}"
    assert not any("安全性" in name for name in extracted_names), f"Should filter '安全性' but found in {extracted_names}"
    assert not any("保值率" in name for name in extracted_names), f"Should filter '保值率' but found in {extracted_names}"
    assert not any("可靠性" in name for name in extracted_names), f"Should filter '可靠性' but found in {extracted_names}"
    assert not any("操控性" in name for name in extracted_names), f"Should filter '操控性' but found in {extracted_names}"
    assert not any("后排舒适" in name for name in extracted_names), f"Should filter '后排舒适' but found in {extracted_names}"
    assert not any("后备箱空间" in name for name in extracted_names), f"Should filter '后备箱空间' but found in {extracted_names}"


def test_extracts_volkswagen_variants():
    """Test that different VW brand variations are extracted correctly."""
    response = """
    大众(Volkswagen)在中国市场的主流SUV包括：
    1. 上汽大众途观L - 中型SUV标杆
    2. 一汽-大众探岳 - 性价比高
    3. VW ID.4 - 纯电SUV新选择

    这些车型的配置丰富度、动力系统、智能驾驶辅助等方面都有不错表现。
    """

    entities = extract_entities(response, "大众", {"zh": ["大众汽车", "上汽大众", "一汽大众"], "en": ["VW", "Volkswagen"]})
    extracted_names = set(entities.all_entities().keys())

    # Should keep VW brand variants
    assert any("大众" in name.lower() or "volkswagen" in name.lower() or "vw" in name.lower() for name in extracted_names), f"Expected VW in {extracted_names}"
    assert any("id" in name.lower() and "4" in name for name in extracted_names), f"Expected ID.4 in {extracted_names}"

    # Should NOT keep features
    assert not any("配置丰富" in name for name in extracted_names), f"Should filter '配置丰富' but found in {extracted_names}"
    assert not any("动力系统" in name for name in extracted_names), f"Should filter '动力系统' but found in {extracted_names}"
    assert not any("智能驾驶" in name for name in extracted_names), f"Should filter '智能驾驶' but found in {extracted_names}"


def test_extracts_tesla_model_variants():
    """Test that Tesla Model variants are extracted correctly."""
    response = """
    特斯拉(Tesla)在中国市场提供：
    - Model Y - 最受欢迎的家用SUV
    - Model 3 - 入门级轿车
    - Model X - 豪华SUV旗舰

    全景天窗、自动驾驶、全液晶仪表盘等配置都很齐全。
    """

    entities = extract_entities(response, "特斯拉", {"zh": ["特斯拉"], "en": ["Tesla"]})
    extracted_names = set(entities.all_entities().keys())

    # Should keep Tesla and models
    assert any("特斯拉" in name.lower() or "tesla" in name.lower() for name in extracted_names), f"Expected Tesla in {extracted_names}"
    assert any("model" in name.lower() for name in extracted_names), f"Expected Model variants in {extracted_names}"

    # Should NOT keep features
    assert not any("全景天窗" in name for name in extracted_names), f"Should filter '全景天窗' but found in {extracted_names}"
    assert not any("自动驾驶" in name for name in extracted_names), f"Should filter '自动驾驶' but found in {extracted_names}"
    assert not any("液晶仪表盘" in name for name in extracted_names), f"Should filter '液晶仪表盘' but found in {extracted_names}"
    assert not any("配置" in name for name in extracted_names), f"Should filter '配置' but found in {extracted_names}"


def test_filters_safety_and_reliability_descriptions():
    """Test that safety and reliability descriptions are filtered."""
    response = """
    从安全性维度来看，中国消费者最认可的SUV包括：

    1. 沃尔沃XC60 - 主动安全系统、被动安全配置都是顶级
    2. 丰田汉兰达 - 可靠性口碑好，故障率低，维修便利
    3. 大众途昂 - 车身刚性好，制动性能强

    这些车型在碰撞测试、刹车距离等方面表现优异。
    """

    entities = extract_entities(response, "大众", {"zh": ["大众"], "en": ["VW", "Volkswagen"]})
    extracted_names = set(entities.all_entities().keys())

    # Should keep brands and models
    assert any("大众" in name.lower() or "volkswagen" in name.lower() for name in extracted_names), f"Expected VW in {extracted_names}"
    assert any("丰田" in name.lower() or "toyota" in name.lower() for name in extracted_names), f"Expected Toyota in {extracted_names}"

    # Should NOT keep descriptions
    assert not any("安全性" in name for name in extracted_names), f"Should filter '安全性' but found in {extracted_names}"
    assert not any("主动安全" in name for name in extracted_names), f"Should filter '主动安全' but found in {extracted_names}"
    assert not any("被动安全" in name for name in extracted_names), f"Should filter '被动安全' but found in {extracted_names}"
    assert not any("可靠性" in name for name in extracted_names), f"Should filter '可靠性' but found in {extracted_names}"
    assert not any("故障率" in name for name in extracted_names), f"Should filter '故障率' but found in {extracted_names}"
    assert not any("维修便利" in name for name in extracted_names), f"Should filter '维修便利' but found in {extracted_names}"
    assert not any("制动性能" in name for name in extracted_names), f"Should filter '制动性能' but found in {extracted_names}"
    assert not any("刹车" in name for name in extracted_names), f"Should filter '刹车' but found in {extracted_names}"


def test_filters_space_and_comfort_descriptions():
    """Test that space and comfort descriptions are filtered."""
    response = """
    从空间/后排舒适/后备箱角度，适合家庭出行的SUV推荐：

    1. 理想L8 - 六座布局，第二排座椅舒适，后备箱容积大
    2. 蔚来ES6 - 后排空间充裕，座椅加热通风功能齐全
    3. 小鹏G9 - 智能座舱体验好，车内静谧性优秀

    车机系统、娱乐配置、氛围灯等细节也都很到位。
    """

    entities = extract_entities(response, "理想", {"zh": ["理想汽车"], "en": ["Li Auto"]})
    extracted_names = set(entities.all_entities().keys())

    # Should keep brands and models
    assert any("理想" in name.lower() for name in extracted_names), f"Expected Li Auto in {extracted_names}"
    assert any(("l" in name.lower() and "8" in name) or ("es" in name.lower() and "6" in name) or ("g" in name.lower() and "9" in name) for name in extracted_names), f"Expected L8/ES6/G9 in {extracted_names}"

    # Should NOT keep space/comfort descriptions
    assert not any("后排空间" in name for name in extracted_names), f"Should filter '后排空间' but found in {extracted_names}"
    assert not any("后排舒适" in name for name in extracted_names), f"Should filter '后排舒适' but found in {extracted_names}"
    assert not any("后备箱" in name for name in extracted_names), f"Should filter '后备箱' but found in {extracted_names}"
    assert not any("智能座舱" in name for name in extracted_names), f"Should filter '智能座舱' but found in {extracted_names}"
    assert not any("车机系统" in name for name in extracted_names), f"Should filter '车机系统' but found in {extracted_names}"
    assert not any("娱乐配置" in name for name in extracted_names), f"Should filter '娱乐配置' but found in {extracted_names}"
    assert not any("氛围灯" in name for name in extracted_names), f"Should filter '氛围灯' but found in {extracted_names}"


def test_extracts_chinese_plus_pro_max_models():
    """Test that Chinese brand models with PLUS/Pro/Max suffixes are extracted."""
    response = """
    20万预算推荐：
    1. 比亚迪宋PLUS DM-i - 油电混动，经济省油
    2. 长城哈弗H6 Pro - 配置高，性价比好
    3. 吉利星越L - 动力强劲
    4. 奇瑞瑞虎8 Plus - 空间大

    发动机技术、变速箱匹配、油耗表现等都不错。
    """

    entities = extract_entities(response, "比亚迪", {"zh": ["BYD"], "en": ["BYD"]})
    extracted_names = set(entities.all_entities().keys())

    # Should keep brands with PLUS/Pro/Max
    assert any("比亚迪" in name.lower() for name in extracted_names), f"Expected BYD in {extracted_names}"
    assert any("宋" in name and "plus" in name.lower() for name in extracted_names), f"Expected Song PLUS in {extracted_names}"
    assert any(("h" in name.lower() and "6" in name) or "哈弗" in name.lower() for name in extracted_names), f"Expected H6/Haval in {extracted_names}"

    # Should NOT keep technical descriptions
    assert not any("发动机" in name for name in extracted_names), f"Should filter '发动机' but found in {extracted_names}"
    assert not any("变速箱" in name for name in extracted_names), f"Should filter '变速箱' but found in {extracted_names}"
    assert not any("油耗" in name for name in extracted_names), f"Should filter '油耗' but found in {extracted_names}"
    assert not any("性价比" in name for name in extracted_names), f"Should filter '性价比' but found in {extracted_names}"


def test_extracts_japanese_brands_correctly():
    """Test that Japanese brands (Toyota, Honda, Nissan, Mazda) are extracted."""
    response = """
    日系SUV推荐（丰田/本田/日产/马自达）：

    1. 丰田RAV4荣放 - Toyota品质可靠
    2. 本田CR-V - Honda技术先进
    3. 日产奇骏 - Nissan舒适性好
    4. 马自达CX-5 - Mazda操控优秀

    品牌口碑、后期维护成本等都值得考虑。
    """

    entities = extract_entities(response, "丰田", {"zh": ["丰田"], "en": ["Toyota"]})
    extracted_names = set(entities.all_entities().keys())

    # Should keep Japanese brands and models
    assert any("丰田" in name.lower() or "toyota" in name.lower() for name in extracted_names), f"Expected Toyota in {extracted_names}"
    assert any("rav" in name.lower() or "cr" in name.lower() or "cx" in name.lower() for name in extracted_names), f"Expected RAV4/CR-V/CX-5 in {extracted_names}"

    # Should NOT keep generic descriptions
    assert not any("品牌口碑" in name for name in extracted_names), f"Should filter '品牌口碑' but found in {extracted_names}"
    assert not any("维护成本" in name for name in extracted_names), f"Should filter '维护成本' but found in {extracted_names}"
    assert not any("舒适性" in name for name in extracted_names), f"Should filter '舒适性' but found in {extracted_names}"
    assert not any("操控" in name for name in extracted_names), f"Should filter '操控' but found in {extracted_names}"
