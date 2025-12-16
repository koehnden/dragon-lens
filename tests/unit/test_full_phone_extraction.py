from services.brand_recognition import extract_entities


def test_full_smartphone_vertical():
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
    print(f"Extracted: {extracted_names}")

    assert any("iphone" in name.lower() and "14" in name for name in extracted_names), f"Expected iPhone14 in {extracted_names}"
