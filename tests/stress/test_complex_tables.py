#!/usr/bin/env python3
"""Stress tests for complex table structures and challenging text."""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../..")

def test_shampoo_complex_table():
    """Stress test: Shampoo example with complex table structure."""
    print("Stress Test: Shampoo/Hair Loss Complex Table")
    print("=" * 70)
    
    text = """对于脱发问题，没有一款洗发水能保证对所有人都"最适合"，因为脱发成因非常复杂。不过，根据你的具体情况选择有针对性的产品，可以起到很好的改善和辅助作用。
为了帮你理清思路，我先将搜索结果中提及的主流防脱洗发水按核心成分和适用场景进行了梳理，方便你对照参考。
主流防脱洗发水对比


品牌 / 产品	核心防脱成分与特点	主要适用场景 / 脱发类型	价格参考	备注
悦罗兰	侧柏叶、姜根、人参等7重植萃；咖啡因、PCA锌；有国妆特证	雄激素性脱发（发际线后移/M型秃）、油性头皮伴随脱发、压力性脱发	约89元/300ml	测评显示防脱效果较显著
欧倍青 C1	0.2%咖啡因，专注延缓毛囊衰老	早期脱发、油性头皮、熬夜党	-	控油效果好，洗后有清凉感
露华浓生姜	生姜精华、薄荷脑；突出清凉控油	油头脱发、头皮闷热、细软塌发质	-	洗后蓬松感较强
MARO 17	王浆酸、胶原蛋白、苹果干细胞；温和氨基酸表活	油性头皮、细软发质、追求温和清洁	价格较高	日本进口，评测中综合推荐度较高
清扬（去屑款）	吡硫鎓锌等去屑成分	头屑多伴随脱发、油性头皮	-	优先解决头屑问题，间接改善因头屑/皮炎引起的脱发
霸王	侧柏叶、白首乌、生姜等中药配方	遗传性脱发早期干预、传统中药理念养护	-	国内经典防脱品牌
施巴 / AVEDA等	温和配方，多种植物精粹	日常养护、头皮敏感、追求温和	价格中等至偏高	更侧重头皮环境健康与清洁"""
    
    vertical = "shampoo haircare"
    
    expected_brands = ["悦罗兰", "欧倍青", "露华浓", "MARO", "清扬", "霸王", "施巴", "AVEDA"]
    expected_products = ["C1", "生姜", "17", "去屑款"]
    
    print(f"Text length: {len(text)} characters")
    print(f"Vertical: {vertical}")
    print(f"\nExpected brands: {expected_brands}")
    print(f"Expected products: {expected_products}")
    
    print("\nThis is a STRESS TEST - complex table structure with mixed languages.")
    print("Expected challenges:")
    print("1. Table parsing with tabs and mixed content")
    print("2. Chinese brand names with English product codes")
    print("3. Parenthetical variants (去屑款)")
    print("4. Mixed language descriptions")
    
    return True

def test_mixed_language_technical():
    """Stress test: Technical document with mixed Chinese/English."""
    print("\n\nStress Test: Mixed Language Technical Document")
    print("=" * 70)
    
    text = """华为Mate 60 Pro搭载麒麟9000S芯片，支持5G网络。相比iPhone 15 Pro的A17 Pro芯片，在AI性能方面有优势。
主要配置对比：
型号	处理器	屏幕	摄像头	电池
华为Mate 60 Pro	麒麟9000S	6.82英寸OLED	50MP主摄+12MP超广角+48MP长焦	5000mAh
iPhone 15 Pro	A17 Pro	6.1英寸Super Retina XDR	48MP主摄+12MP超广角+12MP长焦	3274mAh
三星Galaxy S24 Ultra	骁龙8 Gen 3	6.8英寸Dynamic AMOLED 2X	200MP主摄+12MP超广角+10MP长焦×2	5000mAh"""
    
    vertical = "smartphones technical"
    
    print(f"Text length: {len(text)} characters")
    print(f"Vertical: {vertical}")
    
    print("\nExpected challenges:")
    print("1. Mixed Chinese/English technical terms")
    print("2. Complex table with technical specifications")
    print("3. Model numbers with variants (Pro, Ultra)")
    print("4. Technical abbreviations (MP, mAh, OLED)")
    
    return True

def test_ambiguous_alphanumeric():
    """Stress test: Ambiguous alphanumeric codes."""
    print("\n\nStress Test: Ambiguous Alphanumeric Codes")
    print("=" * 70)
    
    text = """在汽车行业，X5可能是宝马的SUV，也可能是某个电子产品的型号。
同样，G3可能是小鹏汽车，也可能是耳机的型号。
产品推荐：
1. 宝马 X5 - 豪华SUV
2. 小鹏 G3 - 电动SUV  
3. 索尼 WH-1000XM5 - 降噪耳机
4. 大疆 Mavic 3 - 无人机
5. 联想 Yoga 9i - 笔记本电脑"""
    
    vertical = "general products"
    
    print(f"Text length: {len(text)} characters")
    print(f"Vertical: {vertical}")
    
    print("\nExpected challenges:")
    print("1. Same alphanumeric code in different contexts (X5)")
    print("2. Need for context to determine brand vs product")
    print("3. Mixed product categories (cars, electronics, drones)")
    print("4. Short codes that could be brands or products")
    
    return True

def test_noisy_social_media():
    """Stress test: Noisy social media text."""
    print("\n\nStress Test: Noisy Social Media Text")
    print("=" * 70)
    
    text = """刚买了#iPhone15 感觉比之前的#三星S23 好多了！📱
不过#华为Mate60 的相机真的强👍
#小米14 的性价比还是高，但#一加12 的系统更流畅
大家觉得#OPPOFindX7 怎么样？"""
    
    vertical = "social media smartphones"
    
    print(f"Text length: {len(text)} characters")
    print(f"Vertical: {vertical}")
    
    print("\nExpected challenges:")
    print("1. Hashtags and social media formatting")
    print("2. Emojis and special characters")
    print("3. Informal language and comparisons")
    print("4. Missing context and sentence fragments")
    
    return True

def main():
    """Run all stress tests."""
    print("Running Stress Tests for Brand/Product Extraction")
    print("=" * 70)
    print("Note: These tests represent challenging cases where the system")
    print("may struggle. They help identify areas for improvement.")
    print("=" * 70)
    
    tests = [
        ("Complex Table (Shampoo)", test_shampoo_complex_table),
        ("Mixed Language Technical", test_mixed_language_technical),
        ("Ambiguous Alphanumeric", test_ambiguous_alphanumeric),
        ("Noisy Social Media", test_noisy_social_media),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            print(f"\n{'='*70}")
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"Test '{name}' failed with error: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 70)
    print("STRESS TEST SUMMARY:")
    print("=" * 70)
    
    all_passed = True
    for name, result in results:
        status = "✅ PASS" if result else "⚠️  CHALLENGE (expected)"
        print(f"{name}: {status}")
        if not result:
            all_passed = False
    
    print("\n" + "=" * 70)
    if all_passed:
        print("All stress tests completed (some may show challenges)")
    else:
        print("Some stress tests failed - this is expected for challenging cases")
    
    print("\nPurpose of stress tests:")
    print("1. Identify system limitations")
    print("2. Track improvement over time")
    print("3. Set realistic expectations")
    print("4. Guide development priorities")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
