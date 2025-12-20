import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Set

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_CASES = [
    {
        "name": "SUV recommendation Chinese",
        "vertical": "SUV Cars",
        "vertical_description": "Sport utility vehicles for family and off-road use",
        "text": """
在选择SUV时，以下是一些值得推荐的品牌和车型：

1. 大众途观L - 产品质量出色，环保性能好，适合家庭使用
2. 奥迪Q3 - 先进的技术配置，豪华内饰
3. 宝马X3 - 动力强劲，操控优秀
4. 比亚迪宋PLUS DM-i - 新能源SUV，性价比高
5. 长安CS75 PLUS - 自主品牌代表，配置丰富

总之，在选择车型时，需要考虑产品质量、环保性能和家庭需求。与宝马和奥迪相比，自主品牌的性价比更高。
""",
        "expected_brands": {"大众", "奥迪", "宝马", "比亚迪", "长安"},
        "expected_products": {"途观L", "Q3", "X3", "宋PLUS DM-i", "CS75 PLUS"},
        "false_positive_brands": {"自主", "产品质量", "环保性能", "家庭", "先进", "与宝马", "和奥迪", "在选择", "车型时"},
        "false_positive_products": set(),
    },
    {
        "name": "Skincare products",
        "vertical": "Skincare",
        "vertical_description": "Facial skincare and beauty products",
        "text": """
推荐几款好用的护肤品：

1. 欧莱雅小黑瓶 - 抗老精华，温和性好
2. 雅诗兰黛小棕瓶 - 修护效果出色
3. 兰蔻粉水 - 适合敏感肌，保湿效果好
4. SK-II神仙水 - 日本品牌，成分优秀

在选择护肤品时，需要根据自己的肤质选择。温和性好的产品更适合敏感肌。
""",
        "expected_brands": {"欧莱雅", "雅诗兰黛", "兰蔻", "SK-II"},
        "expected_products": {"小黑瓶", "小棕瓶", "粉水", "神仙水"},
        "false_positive_brands": {"温和性好", "保湿效果", "在选择", "敏感肌"},
        "false_positive_products": set(),
    },
    {
        "name": "Smartphone comparison",
        "vertical": "Smartphones",
        "vertical_description": "Mobile phones and related accessories",
        "text": """
Top smartphones in 2024:

1. Apple iPhone 15 Pro - Best camera system, A17 chip
2. Samsung Galaxy S24 Ultra - Advanced AI features
3. Huawei Mate 60 Pro - Self-developed chip technology
4. Xiaomi 14 Ultra - Leica camera partnership

When choosing a smartphone, consider battery life and camera quality.
Apple and Samsung lead in premium segment, while Huawei and Xiaomi offer good value.
""",
        "expected_brands": {"Apple", "Samsung", "Huawei", "Xiaomi"},
        "expected_products": {"iPhone 15 Pro", "Galaxy S24 Ultra", "Mate 60 Pro", "14 Ultra"},
        "false_positive_brands": {"Top1", "In Choosing", "Advanced", "Self-developed"},
        "false_positive_products": set(),
    },
]


@dataclass
class ExtractionResult:
    brands: Set[str]
    products: Set[str]
    method: str


async def extract_with_current_pipeline(
    text: str,
    vertical: str,
    vertical_description: str
) -> ExtractionResult:
    from services.brand_recognition import (
        generate_candidates,
        _filter_candidates_with_qwen,
    )

    candidates = generate_candidates(text, "", {})
    filtered = await _filter_candidates_with_qwen(
        candidates, text, vertical, vertical_description
    )

    brands = {c.name for c in filtered if c.entity_type == "brand"}
    products = {c.name for c in filtered if c.entity_type == "product"}

    return ExtractionResult(brands=brands, products=products, method="current")


async def extract_with_qwen_direct(
    text: str,
    vertical: str,
    vertical_description: str
) -> ExtractionResult:
    from services.ollama import OllamaService

    ollama = OllamaService()

    system_prompt = f"""You are an expert entity extractor for the {vertical} industry.

TASK: Extract ONLY genuine brand names and product names from the text.

DEFINITIONS:
- BRAND: A company/manufacturer name that creates and sells products (e.g., Toyota, Apple, Nike, 比亚迪, 欧莱雅)
- PRODUCT: A specific model/item name made by a brand (e.g., RAV4, iPhone 15, 宋PLUS)

CRITICAL - DO NOT EXTRACT:
- Generic terms or categories (SUV, smartphone, skincare, 汽车, 护肤品)
- Descriptive phrases (产品质量, 环保性能, advanced features)
- Adjectives or modifiers alone (先进, 自主, premium, best)
- Partial phrases with prepositions (在选择, 与宝马, and Apple)
- Feature/technology names (CarPlay, GPS, AI, 新能源)
- Quality descriptors (好用, 出色, excellent)
- Sentence fragments or non-entity text

EXTRACTION RULES:
1. Extract the EXACT brand/product name as it appears, not surrounding text
2. If unsure, DO NOT include - prefer precision over recall
3. Products often have model numbers/letters (X3, Q5, iPhone 15)
4. Brands are typically proper nouns (company names)

{f"Vertical: {vertical}" if vertical else ""}
{f"Description: {vertical_description}" if vertical_description else ""}

Output JSON only:
{{"brands": ["brand1", "brand2"], "products": ["product1", "product2"]}}"""

    prompt = f"""Extract brands and products from this text:

{text}

Output JSON with "brands" and "products" arrays. Be STRICT - only include genuine brand/product names:"""

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
        )

        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        response = response.strip()

        result = json.loads(response)
        brands = set(result.get("brands", []))
        products = set(result.get("products", []))

        return ExtractionResult(brands=brands, products=products, method="qwen_direct")
    except Exception as e:
        logger.error(f"Qwen direct extraction failed: {e}")
        return ExtractionResult(brands=set(), products=set(), method="qwen_direct")


async def extract_with_stricter_filtering(
    text: str,
    vertical: str,
    vertical_description: str
) -> ExtractionResult:
    from services.brand_recognition import generate_candidates, EntityCandidate
    from services.ollama import OllamaService
    import json

    ollama = OllamaService()
    candidates = generate_candidates(text, "", {})
    candidate_names = [c.name for c in candidates]

    if not candidate_names:
        return ExtractionResult(brands=set(), products=set(), method="stricter_filter")

    candidates_json = json.dumps(candidate_names, ensure_ascii=False)

    system_prompt = f"""You are a STRICT entity classifier for the {vertical} industry.

TASK: Classify each candidate as "brand", "product", or "other".

STRICT CLASSIFICATION RULES:

BRAND (company/manufacturer):
- Must be an actual company that makes and sells products
- Examples: Toyota, Apple, Nike, 比亚迪, 欧莱雅, Samsung
- NOT brands: descriptive terms, features, partial phrases

PRODUCT (specific model/item):
- Must be a specific product model made by a brand
- Usually contains model numbers, letters, or distinctive names
- Examples: RAV4, iPhone 15, 宋PLUS, Galaxy S24, X5
- NOT products: brand names, generic categories

OTHER (reject these):
- Generic category terms: SUV, smartphone, 汽车, 护肤品
- Descriptive phrases: 产品质量, 环保性能, advanced
- Adjectives/modifiers alone: 先进, 自主, 好用, premium
- Phrases with prepositions: 在选择, 与宝马, and Samsung
- Partial text fragments: Top1, Carmodeltime, 车型时
- Features/technologies: CarPlay, GPS, AI, hybrid
- Rankings or numbers alone: Top1, 第一

BE VERY STRICT: When in doubt, classify as "other".
Only genuine, standalone brand/product names should pass.

{f"Vertical: {vertical}" if vertical else ""}
{f"Description: {vertical_description}" if vertical_description else ""}

Output JSON array:
[{{"name": "candidate", "type": "brand|product|other"}}]"""

    prompt = f"""Source text:
{text[:1500]}

Candidates to classify:
{candidates_json}

Classify each candidate STRICTLY. Output JSON array only:"""

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
        )

        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        response = response.strip()

        import re
        array_match = re.search(r'\[[\s\S]*\]', response)
        if array_match:
            response = array_match.group(0)

        results = json.loads(response)

        brands = set()
        products = set()
        for item in results:
            if isinstance(item, dict) and "name" in item and "type" in item:
                if item["type"] == "brand":
                    brands.add(item["name"])
                elif item["type"] == "product":
                    products.add(item["name"])

        return ExtractionResult(brands=brands, products=products, method="stricter_filter")
    except Exception as e:
        logger.error(f"Stricter filtering failed: {e}")
        return ExtractionResult(brands=set(), products=set(), method="stricter_filter")


def evaluate_result(
    result: ExtractionResult,
    expected_brands: Set[str],
    expected_products: Set[str],
    false_positive_brands: Set[str],
    false_positive_products: Set[str]
) -> Dict:
    def normalize(s: str) -> str:
        return s.lower().strip()

    result_brands_norm = {normalize(b) for b in result.brands}
    result_products_norm = {normalize(p) for p in result.products}
    expected_brands_norm = {normalize(b) for b in expected_brands}
    expected_products_norm = {normalize(p) for p in expected_products}
    fp_brands_norm = {normalize(b) for b in false_positive_brands}
    fp_products_norm = {normalize(p) for p in false_positive_products}

    brand_hits = len(result_brands_norm & expected_brands_norm)
    brand_fp = len(result_brands_norm & fp_brands_norm)
    product_hits = len(result_products_norm & expected_products_norm)
    product_fp = len(result_products_norm & fp_products_norm)

    brand_precision = brand_hits / len(result_brands_norm) if result_brands_norm else 0
    brand_recall = brand_hits / len(expected_brands_norm) if expected_brands_norm else 0
    product_precision = product_hits / len(result_products_norm) if result_products_norm else 0
    product_recall = product_hits / len(expected_products_norm) if expected_products_norm else 0

    return {
        "method": result.method,
        "brands_extracted": len(result.brands),
        "brands_correct": brand_hits,
        "brands_false_positive": brand_fp,
        "brand_precision": round(brand_precision, 2),
        "brand_recall": round(brand_recall, 2),
        "products_extracted": len(result.products),
        "products_correct": product_hits,
        "products_false_positive": product_fp,
        "product_precision": round(product_precision, 2),
        "product_recall": round(product_recall, 2),
        "extracted_brands": sorted(result.brands),
        "extracted_products": sorted(result.products),
    }


async def run_benchmark():
    print("=" * 80)
    print("BRAND/PRODUCT EXTRACTION BENCHMARK")
    print("=" * 80)

    methods = [
        ("Current Pipeline", extract_with_current_pipeline),
        ("Stricter Filtering", extract_with_stricter_filtering),
        ("Qwen Direct Extraction", extract_with_qwen_direct),
    ]

    all_results = {m[0]: [] for m in methods}

    for test_case in TEST_CASES:
        print(f"\n{'='*80}")
        print(f"TEST: {test_case['name']}")
        print(f"Vertical: {test_case['vertical']}")
        print(f"{'='*80}")

        for method_name, method_func in methods:
            print(f"\n--- {method_name} ---")

            result = await method_func(
                test_case["text"],
                test_case["vertical"],
                test_case["vertical_description"]
            )

            evaluation = evaluate_result(
                result,
                test_case["expected_brands"],
                test_case["expected_products"],
                test_case["false_positive_brands"],
                test_case["false_positive_products"]
            )

            all_results[method_name].append(evaluation)

            print(f"Brands: {evaluation['brands_correct']}/{len(test_case['expected_brands'])} correct, {evaluation['brands_false_positive']} FP")
            print(f"  Precision: {evaluation['brand_precision']}, Recall: {evaluation['brand_recall']}")
            print(f"  Extracted: {evaluation['extracted_brands']}")
            print(f"Products: {evaluation['products_correct']}/{len(test_case['expected_products'])} correct, {evaluation['products_false_positive']} FP")
            print(f"  Precision: {evaluation['product_precision']}, Recall: {evaluation['product_recall']}")
            print(f"  Extracted: {evaluation['extracted_products']}")

    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")

    for method_name, results in all_results.items():
        avg_brand_precision = sum(r["brand_precision"] for r in results) / len(results)
        avg_brand_recall = sum(r["brand_recall"] for r in results) / len(results)
        avg_product_precision = sum(r["product_precision"] for r in results) / len(results)
        avg_product_recall = sum(r["product_recall"] for r in results) / len(results)
        total_brand_fp = sum(r["brands_false_positive"] for r in results)
        total_product_fp = sum(r["products_false_positive"] for r in results)

        print(f"\n{method_name}:")
        print(f"  Brand - Precision: {avg_brand_precision:.2f}, Recall: {avg_brand_recall:.2f}, Total FP: {total_brand_fp}")
        print(f"  Product - Precision: {avg_product_precision:.2f}, Recall: {avg_product_recall:.2f}, Total FP: {total_product_fp}")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
