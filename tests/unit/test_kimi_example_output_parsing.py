"""Regression tests for complex LLM outputs (tables + lists)."""

import pytest

from services.brand_recognition import is_list_format, split_into_list_items


@pytest.fixture(autouse=True)
def _disable_qwen_extraction(monkeypatch):
    from services.brand_recognition import config, orchestrator

    monkeypatch.setattr(config, "ENABLE_QWEN_EXTRACTION", False)
    monkeypatch.setattr(orchestrator, "ENABLE_QWEN_EXTRACTION", False)


def test_kimi_example_multiple_markdown_tables_are_parsed_into_row_items():
    text = """
根据专业户外测评和实测数据，以下是针对北方冰雪路面的冬季徒步鞋TOP 10推荐，覆盖从轻度雪路到极地严寒的不同场景：

🥾 冬季徒步鞋 TOP 10 推荐
top tier：专业极地/严寒环境
|  排名 | 品牌型号                      | 核心配置                                                                    | 适用场景                      | 参考价格         |
| :-: | ------------------------- | ----------------------------------------------------------------------- | ------------------------- | ------------ |
|  1  | **HOKA Kaha 2 Frost GTX** | 400g Primaloft® Gold保暖层 / GORE-TEX®防水 / Vibram® Megagrip防滑大底 / 可抵御-32°C | 极寒长距离徒步、深雪环境              | ¥1,800-2,200 |
|  2  | **SCARPA 疾速极地版 GTX**      | GORE-TEX® Duratherm保暖防水 / 1.8mm绒面革 / -20°C实测保暖                          | 雪地穿越、高海拔冬季登山              | ¥2,000-2,500 |
|  3  | **Oboz Bridger 10\"**      | 200g/400g Thinsulate™可选 / B-DRY防水膜 / 宽适版型 / -20°F实战验证                   | 极寒攀冰、冬季46ers线路（美东北极寒标准测试） | ¥1,500-1,800 |

ice specialist：冰面特化
|  排名 | 品牌型号                               | 核心配置                                                     | 适用场景           | 参考价格       |
| :-: | ---------------------------------- | -------------------------------------------------------- | -------------- | ---------- |
|  4  | **Oboz Bangtail**                  | 200g保暖 / **Vibram® Arctic Grip™**&#x51B0;面专用配方 / 独立冰面齿纹  | 冰川徒步、结冰路面、冻雨环境 | ¥1,600     |
|  5  | **Danner Arctic 600**              | 200g Primaloft® / Vibram® Nisqually Arctic Grip™ / 侧拉链快穿 | 城市通勤+冰面徒步兼得    | ¥2,000+    |
|  6  | **Columbia Expeditionist Extreme** | 400g保暖 / **Omni-Grip™ Ice**冰面橡胶 / 高帮防雪                   | 东北严寒日常徒步       | ¥800-1,200 |

all-rounder：全能平衡
|  排名 | 品牌型号                               | 核心配置                                                 | 适用场景         | 参考价格         |
| :-: | ---------------------------------- | ---------------------------------------------------- | ------------ | ------------ |
|  7  | **The North Face Vectiv Fastpack** | 200g保暖 / DryVent防水 / Surface CTRL™ 4mm齿纹 / 轻量化(17oz) | 快速穿越、雪山轻装徒步  | ¥1,200-1,500 |
|  8  | **Salomon X Ultra Snowpilot**      | 70%再生纤维保暖 / ClimaSalomon防水膜 / 城市外观                   | 城市×山地跨界、周末徒步 | ¥1,200-1,400 |
|  9  | **Mammut Blackfin III Mid**        | 铝丝反射保暖层 / Vibram®全地形大底 / 1.3磅超轻                      | 三季兼容、高机动性徒步  | ¥1,400-1,700 |
|  10 | **Salewa Puez Winter Mid**         | Powertex防水 / 200g金标P棉 / 零磨合设计                        | 温带雪地、短途徒步    | ¥1,000-1,300 |

🔬 保暖 vs 防滑：如何兼顾？
一、保暖层级的科学选择
根据实测数据，保温棉填充量（g）与活动状态决定了保暖极限：

|    填充量    |      适用温度     |    适用场景    |      人体感受     |
| :-------: | :-----------: | :--------: | :-----------: |
|  **200g** |  0°C ~ -15°C  |   持续移动徒步   | 活跃状态下温暖，静止时微凉 |
|  **400g** | -15°C ~ -30°C | 深雪溯溪、冰攀、狩猎 |   静止30分钟无冷感   |
| **600g+** |    -30°C以下    | 极地探险、长时间静止 |   仅适合极寒，易出汗   |
"""
    assert is_list_format(text) is True

    items = split_into_list_items(text)
    # 3 + 3 + 4 + 3 rows across the 4 tables above.
    assert len(items) == 13
    joined = "\n".join(items)

    assert "HOKA Kaha 2 Frost GTX" in joined
    assert "Oboz Bangtail" in joined
    assert "Salewa Puez Winter Mid" in joined
    assert "600g+" in joined


def test_kimi_example_bullet_list_is_split_correctly():
    text = """
* Vibram® Arctic Grip™：专门针对湿冰（wet ice）研发的配方
* Vibram® Megagrip：全天候平衡，湿滑岩石+硬雪路面表现优异
* Omni-Grip™ Ice / KEEN.Polar Traction：各品牌自有冰面配方
"""
    assert is_list_format(text) is True
    items = split_into_list_items(text)
    assert len(items) == 3
    assert "Vibram" in items[0]
    assert "Megagrip" in items[1]
    assert "Omni-Grip" in items[2]
