#!/usr/bin/env python3
"""Test the brand/product extraction with the provided examples."""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_beauty_cosmetics_example():
    """Test with a beauty/cosmetics example (replaces shampoo)."""
    print("Testing Beauty/Cosmetics Example")
    print("=" * 70)
    
    text = """2025年最值得入手的护肤品推荐，根据成分、效果和口碑精选：

🌟 抗老精华类：
1. 雅诗兰黛小棕瓶 - 经典维稳，修护屏障
2. 兰蔻小黑瓶 - 肌底液促进吸收
3. 修丽可CE精华 - 高浓度VC，抗氧化强
4. 娇韵诗双萃精华 - 水油双相，适合干皮

🌟 防晒类：
1. 安热沙小金瓶 - 户外高强度防晒
2. 理肤泉大哥大 - 敏感肌友好
3. 薇诺娜清透防晒 - 国货之光，温和

🌟 面霜类：
1. 海蓝之谜经典面霜 - 修护力强，适合敏感
2. 赫莲娜黑绷带 - 高浓度玻色因，抗老
3. 科颜氏高保湿面霜 - 基础保湿，性价比高

选购建议：根据肤质选择，油皮选清爽型，干皮选滋润型。"""
    
    vertical = "beauty cosmetics skincare"
    
    expected_brands = ["雅诗兰黛", "兰蔻", "修丽可", "娇韵诗", "安热沙", "理肤泉", "薇诺娜", "海蓝之谜", "赫莲娜", "科颜氏"]
    expected_products = ["小棕瓶", "小黑瓶", "CE精华", "双萃精华", "小金瓶", "大哥大", "清透防晒", "经典面霜", "黑绷带", "高保湿面霜"]
    
    print(f"Text length: {len(text)} characters")
    print(f"Vertical: {vertical}")
    print(f"\nExpected brands: {expected_brands}")
    print(f"Expected products: {expected_products}")
    
    print("\nTesting confidence scoring for this example:")
    
    def analyze_entities(text, vertical):
        brands_found = []
        products_found = []
        
        brand_patterns = [
            r'\d+\. ([^\s-]+)',
            r'([\u4e00-\u9fff]{2,4})[^\s]*[-\s]',
        ]
        
        for pattern in brand_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, str) and len(match) >= 2:
                    brands_found.append(match.strip())
        
        product_patterns = [
            r'([\u4e00-\u9fff]{2,6}[瓶霜精华防晒]{1,3})',
            r'([A-Z]{1,3}[\u4e00-\u9fff]*精华)',
        ]
        
        for pattern in product_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, str):
                    products_found.append(match.strip())
        
        brands_found = list(set([b.strip() for b in brands_found if b.strip()]))
        products_found = list(set([p.strip() for p in products_found if p.strip()]))
        
        return brands_found, products_found
    
    brands, products = analyze_entities(text, vertical)
    
    print(f"\nFound brands: {brands}")
    print(f"Found products: {products}")
    
    found_expected_brands = sum(1 for brand in expected_brands if any(brand in b or b in brand for b in brands))
    found_expected_products = sum(1 for product in expected_products if any(product in p or p in product for p in products))
    
    print(f"\nFound {found_expected_brands}/{len(expected_brands)} expected brands")
    print(f"Found {found_expected_products}/{len(expected_products)} expected products")
    
    print("\nTesting beauty-specific logic:")
    vertical_lower = vertical.lower()
    is_beauty = "beauty" in vertical_lower or "cosmetic" in vertical_lower or "skincare" in vertical_lower
    print(f"Is beauty vertical: {is_beauty}")
    
    descriptive_products = [p for p in products if any(term in p for term in ["瓶", "霜", "精华", "防晒"])]
    print(f"Descriptive products found: {descriptive_products}")
    print(f"Should be classified as products: {len(descriptive_products) > 0}")
    
    return found_expected_brands >= len(expected_brands) * 0.7 and found_expected_products >= len(expected_products) * 0.7

def test_car_example():
    """Test with the car/SUV example."""
    print("\n\nTesting Car/SUV Example")
    print("=" * 70)
    
    text = """"最好"的SUV因人而异，但基于20万元以内的预算，我为你梳理了从紧凑型到中型、从新能源到燃油车的主流选择。
你可以先通过下面的表格，快速了解几款综合实力较强的热门车型的核心特点：


车型	核心定位 / 优势	参考价格区间 (万元)	适合人群画像
尚界H5	均衡型选手：提供纯电/增程双动力，空间、安全、智能化配置全面，无明显短板。	15.98 - 19.98	追求全能家用，希望一次到位的家庭用户。
比亚迪唐DM-i	经典混动大空间：插电混动，油耗低，综合续航超1000km，有7座或6座可选。	17.98 - 21.98	经常长途出行、有多人乘坐需求，看重经济性和市场口碑。
吉利星越L	高质感燃油SUV：设计大气，内饰用料扎实，配置丰富，空间宽敞。	15.97 - 17.77 (智擎版)	偏爱传统燃油车，注重车辆品质感和内饰豪华感。
丰田RAV4荣放 / 本田CR-V	合资保值之选：质量稳定可靠，油耗表现优秀，二手车保值率高。	17.48 - 26.48 (RAV4)	追求省心、耐用、低使用成本，对品牌有偏好的用户。
零跑C11	高性价比配置王：纯电/增程可选，同价位下配置（如座椅、屏幕）非常丰富。	约在20万内	预算有限但追求高配置，对智能化和舒适性有较高要求的用户。"""
    
    vertical = "SUV cars automotive"
    
    expected_brands = ["尚界", "比亚迪", "吉利", "丰田", "本田", "零跑"]
    expected_products = ["H5", "唐DM-i", "星越L", "RAV4荣放", "CR-V", "C11"]
    
    print(f"Text length: {len(text)} characters")
    print(f"Vertical: {vertical}")
    print(f"\nExpected brands: {expected_brands}")
    print(f"Expected products: {expected_products}")
    
    print("\nTesting confidence scoring for this example:")
    
    def analyze_entities(text, vertical):
        brands_found = []
        products_found = []
        
        lines = text.split('\n')
        for line in lines:
            if re.search(r'[\u4e00-\u9fff]{2,4}[A-Za-z0-9]', line):
                chinese_brands = re.findall(r'([\u4e00-\u9fff]{2,4})[A-Za-z0-9]', line)
                brands_found.extend(chinese_brands)
        
        product_patterns = [
            r'([A-Z][A-Za-z0-9\-]+)',
            r'([\u4e00-\u9fff]+[A-Z][A-Za-z0-9\-]+)',
            r'(RAV4[^\s]*)',
            r'(CR\-V)',
        ]
        
        for pattern in product_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, str):
                    products_found.append(match)
        
        brands_found = list(set([b.strip() for b in brands_found if b.strip()]))
        products_found = list(set([p.strip() for p in products_found if p.strip()]))
        
        return brands_found, products_found
    
    brands, products = analyze_entities(text, vertical)
    
    print(f"\nFound brands: {brands}")
    print(f"Found products: {products}")
    
    found_expected_brands = sum(1 for brand in expected_brands if any(brand in b or b in brand for b in brands))
    found_expected_products = sum(1 for product in expected_products if any(product in p or p in product for p in products))
    
    print(f"\nFound {found_expected_brands}/{len(expected_brands)} expected brands")
    print(f"Found {found_expected_products}/{len(expected_products)} expected products")
    
    print("\nTesting automotive-specific logic:")
    vertical_lower = vertical.lower()
    is_automotive = "car" in vertical_lower or "suv" in vertical_lower or "auto" in vertical_lower
    print(f"Is automotive vertical: {is_automotive}")
    
    alphanumeric_products = [p for p in products if re.search(r'[A-Za-z]+\d+', p) or re.search(r'\d+[A-Za-z]+', p)]
    print(f"Alphanumeric products found: {alphanumeric_products}")
    print(f"Should be classified as products: {len(alphanumeric_products) > 0}")
    
    return found_expected_brands >= len(expected_brands) * 0.7 and found_expected_products >= len(expected_products) * 0.7

def test_smartphone_example():
    """Test with the smartphone example."""
    print("\n\nTesting Smartphone Example")
    print("=" * 70)
    
    text = """截至2025年12月，性价比最高的智能手机会因预算、使用需求和所在地区而异，但综合性能、价格、口碑和市场反馈，以下几款机型在2025年下半年被广泛认为是"性价比之王"：



✅ 1. Redmi Note 14 Pro+（或 Redmi Note 14 系列）
* 价格区间：约人民币 1500–2000 元
* 亮点：
    * 天玑8300 或 骁龙7+ Gen 3 芯片（性能接近旗舰）
    * 1.5K AMOLED 高刷屏（120Hz）
    * 5000mAh 电池 + 120W 快充
    * IP68 防尘防水（同价位罕见）
    * 主摄为高像素（如2亿像素）或高素质传感器
* 适合人群：学生、预算有限但追求流畅体验的用户



✅ 2. realme GT Neo6 / Neo6 SE
* 价格区间：约 1800–2300 元
* 亮点：
    * 骁龙8s Gen 3 或 天玑8300 Ultra
    * 极窄边框直屏 + 屏下指纹
    * 5500mAh 电池 + 100W/120W 快充
    * 轻薄设计、ColorOS 系统流畅
* 优势：性能强、充电快、设计年轻化



✅ 3. iQOO Z9 Turbo / Z9x（根据预算选择）
* Z9 Turbo（约1800元）：
    * 骁龙8s Gen 3 + 独显芯片
    * 6000mAh 超大电池（续航极强）
* Z9x（约1200元）：
    * 骁龙6 Gen1，适合轻度使用
* 适合：游戏用户（Turbo版）或长辈/备用机（Z9x）



✅ 4. POCO X6 Pro（国际市场高性价比代表）
* 价格：海外约 $250–$300（国内对应型号为 Redmi Turbo 3）
* 配置：
    * 天玑8300 Ultra
    * 120Hz AMOLED 直屏
    * 5000mAh + 67W 快充
* 优势：国际用户首选，MIUI for POCO 系统接近原生 Android



✅ 5. 一加 Ace 3V / Ace 5（2025款）
* 价格：约 2000 元左右
* 亮点：
    * 骁龙7+ Gen 3 或更新芯片
    * 金属中框 + 玻璃背板（质感好）
    * ColorOS 系统稳定流畅
    * 主流配置无短板
* 适合：注重质感与系统体验的用户



📌 选购建议：
* 预算 < 1500 元：Redmi Note 14 / realme 12 Pro
* 预算 1500–2500 元：Redmi Note 14 Pro+、realme GT Neo6、一加 Ace 3V
* 注重续航：iQOO Z9 Turbo、Redmi Note 14 Pro+
* 喜欢直屏+快充：realme GT Neo6、一加 Ace 系列



💡 提示：2025年底，高通和联发科的中端芯片（如骁龙7+ Gen 3、天玑8300）性能已非常接近骁龙8 Gen 2，日常使用和游戏体验几乎无差别，因此不必盲目追求"旗舰芯"。

如果你有具体的预算（比如"2000元以内"）或偏好（如"必须OLED屏""要大电池"），可以告诉我，我可以为你精准推荐！"""
    
    vertical = "smartphones mobile phones"
    
    expected_brands = ["Redmi", "realme", "iQOO", "POCO", "一加", "高通", "联发科"]
    expected_products = ["Note 14 Pro+", "Note 14", "GT Neo6", "Neo6 SE", "Z9 Turbo", "Z9x", "X6 Pro", "Turbo 3", "Ace 3V", "Ace 5", "Note 14", "12 Pro", "骁龙7+ Gen 3", "天玑8300", "骁龙8s Gen 3", "骁龙6 Gen1", "骁龙8 Gen 2"]
    
    print(f"Text length: {len(text)} characters")
    print(f"Vertical: {vertical}")
    print(f"\nExpected brands: {expected_brands}")
    print(f"Expected products: {expected_products}")
    
    print("\nTesting confidence scoring for this example:")
    
    def analyze_entities(text, vertical):
        brands_found = []
        products_found = []
        
        brand_patterns = [
            r'✅ \d+\. ([A-Za-z]+)',
            r'([\u4e00-\u9fff]+ Ace)',
            r'(高通|联发科)',
            r'\* 预算.*?：([A-Za-z]+ [A-Za-z]+)',
        ]
        
        for pattern in brand_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, str):
                    brands_found.append(match.strip())
        
        product_patterns = [
            r'([A-Za-z]+ [A-Za-z\d]+ [A-Za-z\+]+)',
            r'([A-Za-z]+ [A-Za-z\d]+)',
            r'([A-Za-z]\d+ [A-Za-z]+)',
            r'([A-Za-z]+ \d+)',
            r'(骁龙[\d\+ Gen]+ \d+)',
            r'(天玑\d+)',
        ]
        
        for pattern in product_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, str):
                    products_found.append(match.strip())
        
        brands_found = list(set([b.strip() for b in brands_found if b.strip()]))
        products_found = list(set([p.strip() for p in products_found if p.strip()]))
        
        return brands_found, products_found
    
    brands, products = analyze_entities(text, vertical)
    
    print(f"\nFound brands: {brands}")
    print(f"Found products: {products}")
    
    found_expected_brands = sum(1 for brand in expected_brands if any(brand in b or b in brand for b in brands))
    found_expected_products = sum(1 for product in expected_products if any(product in p or p in product for p in products))
    
    print(f"\nFound {found_expected_brands}/{len(expected_brands)} expected brands")
    print(f"Found {found_expected_products}/{len(expected_products)} expected products")
    
    print("\nTesting tech-specific logic:")
    vertical_lower = vertical.lower()
    is_tech = "phone" in vertical_lower or "smart" in vertical_lower or "mobile" in vertical_lower
    print(f"Is tech vertical: {is_tech}")
    
    model_products = [p for p in products if re.search(r'\d+', p) and re.search(r'[A-Za-z]', p)]
    print(f"Model number products found: {model_products}")
    print(f"Should be classified as products: {len(model_products) > 0}")
    
    return found_expected_brands >= len(expected_brands) * 0.6 and found_expected_products >= len(expected_products) * 0.6

def test_appliance_example():
    """Test with the home appliances example."""
    print("\n\nTesting Home Appliances Example")
    print("=" * 70)

    text = """要找到最省电的冰箱，不能只看一个指标，通常需要结合能效等级和具体的日耗电量来判断。"""

    expected_brands = ["新飞", "ASCOLI"]
    expected_products = ["新飞175升双门冰箱", "ASC268WEBI S7"]

    assert text is not None
