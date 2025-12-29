import asyncio
import importlib
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

import numpy as np

from src.constants import (
    PRODUCT_HINTS,
    KNOWN_PRODUCTS,
    GENERIC_TERMS,
    DESCRIPTOR_PATTERNS,
    LIST_PATTERNS,
    COMPILED_LIST_PATTERNS,
    COMPARISON_MARKERS,
    CLAUSE_SEPARATORS,
    VALID_EXTRA_TERMS,
)
from src.services.wikidata_lookup import (
    is_known_brand as wikidata_is_known_brand,
    is_known_product as wikidata_is_known_product,
    get_cache_available as wikidata_cache_available,
)

logger = logging.getLogger(__name__)

ENABLE_QWEN_FILTERING = os.getenv("ENABLE_QWEN_FILTERING", "true").lower() == "true"
ENABLE_QWEN_EXTRACTION = os.getenv("ENABLE_QWEN_EXTRACTION", "true").lower() == "true"
ENABLE_EMBEDDING_CLUSTERING = os.getenv("ENABLE_EMBEDDING_CLUSTERING", "false").lower() == "true"
ENABLE_LLM_CLUSTERING = os.getenv("ENABLE_LLM_CLUSTERING", "false").lower() == "true"
ENABLE_WIKIDATA_NORMALIZATION = os.getenv("ENABLE_WIKIDATA_NORMALIZATION", "false").lower() == "true"
ENABLE_BRAND_VALIDATION = os.getenv("ENABLE_BRAND_VALIDATION", "false").lower() == "true"
ENABLE_CONFIDENCE_VERIFICATION = os.getenv("ENABLE_CONFIDENCE_VERIFICATION", "false").lower() == "true"
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "qllama/bge-small-zh-v1.5:latest")


def _is_descriptor_pattern(name: str) -> bool:
    for pattern in DESCRIPTOR_PATTERNS:
        if re.match(pattern, name):
            if name.lower() not in PRODUCT_HINTS:
                return True
    return False


@dataclass
class EntityCandidate:
    name: str
    source: str
    entity_type: str = "unknown"


@dataclass
class ExtractedEntities:
    primary_brand: str | None
    primary_product: str | None
    brand_confidence: float = 0.0
    product_confidence: float = 0.0


@dataclass
class ExtractionDebugInfo:
    raw_brands: List[str]
    raw_products: List[str]
    rejected_at_normalization: List[dict]
    rejected_at_validation: List[str]
    rejected_at_list_filter: List[str]
    final_brands: List[str]
    final_products: List[str]


@dataclass
class ExtractionResult:
    brands: Dict[str, List[str]]
    products: Dict[str, List[str]]
    debug_info: ExtractionDebugInfo | None = None

    def all_entities(self) -> Dict[str, List[str]]:
        combined = dict(self.brands)
        combined.update(self.products)
        return combined


def is_likely_brand(name: str) -> bool:
    name_lower = name.lower().strip()

    if name_lower in GENERIC_TERMS:
        return False

    if _is_descriptor_pattern(name):
        return False

    if _has_product_model_patterns(name):
        return False

    if re.match(r"^[A-Z][a-z]+$", name) and len(name) >= 4:
        return True

    if re.search(r"[\u4e00-\u9fff]{2,4}$", name) and not re.search(r"\d", name):
        if not _has_product_suffix(name):
            return True

    if re.match(r"^[A-Z]{2,5}$", name) and name not in {"EV", "DM", "AI", "VR", "AR"}:
        return True

    return False


def is_likely_product(name: str) -> bool:
    name_lower = name.lower().strip()

    if name_lower in GENERIC_TERMS:
        return False

    if _has_product_model_patterns(name):
        return True

    if name_lower in PRODUCT_HINTS:
        return True

    if _has_product_suffix(name):
        return True

    return False


def _has_product_model_patterns(name: str) -> bool:
    if re.search(r"[A-Za-z]+\d+", name) or re.search(r"\d+[A-Za-z]+", name):
        return True
    if re.match(r"^[A-Z]\d+$", name):
        return True
    if re.match(r"^Model\s+[A-Z0-9]", name, re.IGNORECASE):
        return True
    if re.match(r"^ID\.\d+", name):
        return True
    if re.match(r"^[A-Z]{1,3}-?[A-Z]?\d+", name):
        return True
    return False


def _has_product_suffix(name: str) -> bool:
    product_suffixes = [
        "PLUS", "Plus", "plus",
        "Pro", "PRO", "pro",
        "Max", "MAX", "max",
        "Ultra", "ULTRA", "ultra",
        "Mini", "MINI", "mini",
        "EV", "ev",
        "DM", "DM-i", "DM-p", "dm", "dm-i", "dm-p",
        "GT", "gt",
        "SE", "se",
        "XL", "xl",
    ]
    return any(name.endswith(suffix) or f" {suffix}" in name for suffix in product_suffixes)


def classify_entity_type(name: str, vertical: str = "") -> str:
    name_lower = name.lower().strip()
    if name_lower in GENERIC_TERMS:
        return "other"
    if is_likely_brand(name):
        return "brand"
    if is_likely_product(name):
        return "product"
    return "other"


def extract_primary_entities_from_list_item(item: str) -> Dict[str, str | None]:
    result: Dict[str, str | None] = {"primary_brand": None, "primary_product": None}
    item_normalized = normalize_text_for_ner(item)
    item_lower = item_normalized.lower()
    product_positions: List[Tuple[int, int, str]] = []
    for product in KNOWN_PRODUCTS:
        pos = item_lower.find(product.lower())
        if pos != -1:
            display = product.upper() if len(product) <= 4 and product.isascii() else product.title()
            chinese_products_display = {
                "宋plus": "宋PLUS", "汉ev": "汉EV", "秦plus": "秦PLUS", "元plus": "元PLUS",
                "宋pro": "宋Pro", "唐dm": "唐DM", "汉dm": "汉DM",
            }
            if product.lower() in chinese_products_display:
                display = chinese_products_display[product.lower()]
            product_positions.append((pos, -len(product), display))
    if product_positions:
        product_positions.sort(key=lambda x: (x[0], x[1]))
        result["primary_product"] = product_positions[0][2]
    if result["primary_brand"] is None:
        brand_pattern = r"\b([A-Z][a-z]{3,}|[A-Z]{2,4})\b"
        for match in re.finditer(brand_pattern, item_normalized):
            candidate = match.group(1)
            if is_likely_brand(candidate) and candidate.lower() not in GENERIC_TERMS:
                result["primary_brand"] = candidate
                break
    if result["primary_product"] is None:
        product_pattern = r"\b([A-Z][A-Za-z]*\d+[A-Za-z]*|[A-Z]\d+|Model\s+[A-Z0-9]+|ID\.\d+)\b"
        for match in re.finditer(product_pattern, item_normalized):
            candidate = match.group(1)
            if is_likely_product(candidate):
                result["primary_product"] = candidate
                break
    return result


def normalize_text_for_ner(text: str) -> str:
    if not text:
        return text

    normalized = text

    fullwidth_to_halfwidth = {
        '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
        '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
        'Ａ': 'A', 'Ｂ': 'B', 'Ｃ': 'C', 'Ｄ': 'D', 'Ｅ': 'E',
        'Ｆ': 'F', 'Ｇ': 'G', 'Ｈ': 'H', 'Ｉ': 'I', 'Ｊ': 'J',
        'Ｋ': 'K', 'Ｌ': 'L', 'Ｍ': 'M', 'Ｎ': 'N', 'Ｏ': 'O',
        'Ｐ': 'P', 'Ｑ': 'Q', 'Ｒ': 'R', 'Ｓ': 'S', 'Ｔ': 'T',
        'Ｕ': 'U', 'Ｖ': 'V', 'Ｗ': 'W', 'Ｘ': 'X', 'Ｙ': 'Y',
        'Ｚ': 'Z',
        'ａ': 'a', 'ｂ': 'b', 'ｃ': 'c', 'ｄ': 'd', 'ｅ': 'e',
        'ｆ': 'f', 'ｇ': 'g', 'ｈ': 'h', 'ｉ': 'i', 'ｊ': 'j',
        'ｋ': 'k', 'ｌ': 'l', 'ｍ': 'm', 'ｎ': 'n', 'ｏ': 'o',
        'ｐ': 'p', 'ｑ': 'q', 'ｒ': 'r', 'ｓ': 's', 'ｔ': 't',
        'ｕ': 'u', 'ｖ': 'v', 'ｗ': 'w', 'ｘ': 'x', 'ｙ': 'y',
        'ｚ': 'z',
        '　': ' ', '（': '(', '）': ')', '［': '[', '］': ']',
        '｛': '{', '｝': '}', '＜': '<', '＞': '>',
        '＋': '+', '－': '-', '＝': '=', '＊': '*', '／': '/',
        '＆': '&', '％': '%', '＄': '$', '＃': '#', '＠': '@',
        '！': '!', '？': '?', '．': '.', '，': ',', '：': ':',
        '；': ';', '｜': '|', '～': '~', '＿': '_',
    }

    for fullwidth, halfwidth in fullwidth_to_halfwidth.items():
        normalized = normalized.replace(fullwidth, halfwidth)

    chinese_punct_map = {
        '，': ',', '。': '.', '！': '!', '？': '?',
        '：': ':', '；': ';', '、': ',',
        '"': '"', '"': '"', ''': "'", ''': "'",
        '「': '"', '」': '"', '『': '"', '』': '"',
        '【': '[', '】': ']', '《': '<', '》': '>',
        '—': '-', '…': '...',
    }

    for chinese_punct, ascii_punct in chinese_punct_map.items():
        normalized = normalized.replace(chinese_punct, ascii_punct)

    normalized = normalized.replace('\u3000', ' ')
    normalized = normalized.replace('\xa0', ' ')

    normalized = ' '.join(normalized.split())

    return normalized


def is_list_format(text: str) -> bool:
    for pattern in COMPILED_LIST_PATTERNS:
        matches = pattern.findall(text)
        if len(matches) >= 2:
            return True
    return False


def split_into_list_items(text: str) -> List[str]:
    if not is_list_format(text):
        return []

    combined_pattern = r'(?:^\s*\d+[.\)]|^\s*\d+、|^\s*[-*]|^\s*[・○→]|^#{1,4}\s*\**\d+[.\)])\s*'
    parts = re.split(combined_pattern, text, flags=re.MULTILINE)
    items = [p.strip() for p in parts if p and p.strip()]

    first_item_idx = _find_first_list_item_index(text)
    if first_item_idx > 0 and items:
        items = items[1:] if _is_intro_paragraph(items[0], text) else items

    return items


def _find_first_list_item_index(text: str) -> int:
    combined_pattern = r'(?:^\s*\d+[.\)]|^\s*\d+、|^\s*[-*]|^\s*[・○→]|^#{1,4}\s*\**\d+[.\)])'
    match = re.search(combined_pattern, text, flags=re.MULTILINE)
    return match.start() if match else 0


def _is_intro_paragraph(candidate: str, full_text: str) -> bool:
    first_marker_idx = _find_first_list_item_index(full_text)
    if first_marker_idx == 0:
        return False
    intro_part = full_text[:first_marker_idx].strip()
    return candidate.strip() == intro_part


def extract_entities(
    text: str,
    primary_brand: str,
    aliases: Dict[str, List[str]],
    vertical: str = "",
    vertical_description: str = "",
) -> ExtractionResult:
    if ENABLE_QWEN_EXTRACTION:
        return _run_async(_extract_entities_with_qwen(text, vertical, vertical_description))

    normalized_text = normalize_text_for_ner(text)
    candidates = generate_candidates(normalized_text, primary_brand, aliases)

    if ENABLE_QWEN_FILTERING:
        filtered_candidates = _run_async(
            _filter_candidates_with_qwen(candidates, normalized_text, vertical, vertical_description)
        )
    else:
        filtered_candidates = _filter_candidates_simple(candidates)

    filtered_candidates = _filter_by_list_position(filtered_candidates, text)

    if ENABLE_EMBEDDING_CLUSTERING:
        embedding_clusters = _run_async(_cluster_with_embeddings(filtered_candidates))
    else:
        embedding_clusters = {c.name: [c] for c in filtered_candidates}

    if ENABLE_LLM_CLUSTERING:
        final_clusters = _run_async(_llm_assisted_clustering(embedding_clusters, primary_brand, aliases))
    else:
        final_clusters = _simple_clustering(embedding_clusters, primary_brand, aliases)

    brands, products = _split_clusters_by_type(final_clusters, filtered_candidates)
    return ExtractionResult(brands=brands, products=products)


def _is_automotive_vertical(vertical_lower: str) -> bool:
    automotive_keywords = ["car", "suv", "automotive", "vehicle", "auto", "truck"]
    for keyword in automotive_keywords:
        pattern = rf'\b{keyword}s?\b'
        if re.search(pattern, vertical_lower):
            return True
        if keyword in vertical_lower:
            idx = vertical_lower.find(keyword)
            if (idx == 0 or not vertical_lower[idx-1].isalpha()) and \
               (idx + len(keyword) == len(vertical_lower) or not vertical_lower[idx + len(keyword)].isalpha()):
                return True
    return False


def _boost_confidence_for_known_relationships(
    product_confidences: Dict[str, float],
    relationships: Dict[str, str],
    brands: List[str]
) -> Dict[str, float]:
    for product, parent in relationships.items():
        if product in product_confidences:
            if parent in brands:
                product_confidences[product] = min(0.95, product_confidences[product] + 0.2)
                logger.debug(f"Boosted confidence for product '{product}' (parent: {parent})")
    return product_confidences


AMBIGUOUS_CONFIDENCE_THRESHOLD = 0.5


def _identify_ambiguous_entities(
    brand_confidences: Dict[str, float],
    product_confidences: Dict[str, float]
) -> Tuple[List[str], Dict[str, str]]:
    ambiguous_entities = []
    entity_source = {}
    for brand, confidence in brand_confidences.items():
        if confidence < AMBIGUOUS_CONFIDENCE_THRESHOLD:
            ambiguous_entities.append(brand)
            entity_source[brand] = "brand"
    for product, confidence in product_confidences.items():
        if confidence < AMBIGUOUS_CONFIDENCE_THRESHOLD:
            ambiguous_entities.append(product)
            entity_source[product] = "product"
    return ambiguous_entities, entity_source


def _process_brands_with_verification(
    brands: List[str],
    verified_results: Dict[str, str],
    brand_confidences: Dict[str, float]
) -> List[str]:
    corrected_brands = []
    for brand in brands:
        if brand in verified_results:
            entity_type = verified_results[brand]
            if entity_type == "brand":
                corrected_brands.append(brand)
        else:
            confidence = brand_confidences.get(brand, 0.5)
            if confidence >= 0.6:
                corrected_brands.append(brand)
            elif confidence <= 0.4 and not _has_product_patterns(brand):
                corrected_brands.append(brand)
            else:
                corrected_brands.append(brand)
    return corrected_brands


def _process_products_with_verification(
    products: List[str],
    verified_results: Dict[str, str],
    product_confidences: Dict[str, float]
) -> List[str]:
    corrected_products = []
    for product in products:
        if product in verified_results:
            entity_type = verified_results[product]
            if entity_type == "product":
                corrected_products.append(product)
        else:
            confidence = product_confidences.get(product, 0.5)
            if confidence >= 0.6:
                corrected_products.append(product)
            elif confidence <= 0.4 and not _has_brand_patterns(product):
                corrected_products.append(product)
            else:
                corrected_products.append(product)
    return corrected_products


async def _extract_entities_with_qwen(
    text: str,
    vertical: str = "",
    vertical_description: str = ""
) -> ExtractionResult:
    import json
    from services.ollama import OllamaService

    ollama = OllamaService()

    system_prompt = _build_extraction_system_prompt(vertical, vertical_description)
    prompt = _build_extraction_prompt(text)

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )

        result = _parse_extraction_response(response)
        brands = result.get("brands", [])
        products = result.get("products", [])
        relationships = result.get("relationships", {})

        logger.info(f"[Extraction] Raw from Qwen: brands={brands}, products={products}")

        if ENABLE_CONFIDENCE_VERIFICATION:
            brand_confidences = _calculate_confidence_scores(brands, vertical, is_brand=True)
            product_confidences = _calculate_confidence_scores(products, vertical, is_brand=False)
            product_confidences = _boost_confidence_for_known_relationships(
                product_confidences, relationships, brands
            )

            logger.debug(f"[Extraction] Brand confidences: {brand_confidences}")
            logger.debug(f"[Extraction] Product confidences: {product_confidences}")

            ambiguous_entities, entity_source = _identify_ambiguous_entities(
                brand_confidences, product_confidences
            )
            verified_results = await _verify_ambiguous_entities_with_qwen(
                ollama, ambiguous_entities, text, vertical, vertical_description
            ) if ambiguous_entities else {}

            if ambiguous_entities:
                logger.info(f"[Extraction] Ambiguous entities verified: {verified_results}")

            corrected_brands = _process_brands_with_verification(
                brands, verified_results, brand_confidences
            )
            corrected_products = _process_products_with_verification(
                products, verified_results, product_confidences
            )
            corrected_brands = list(dict.fromkeys(corrected_brands))
            corrected_products = list(dict.fromkeys(corrected_products))

            logger.info(f"[Extraction] After verification: brands={corrected_brands}")
        else:
            logger.info(f"[Extraction] Skipping confidence verification (ENABLE_CONFIDENCE_VERIFICATION=false)")
            corrected_brands = list(dict.fromkeys(brands))
            corrected_products = list(dict.fromkeys(products))

        normalized_result = await _normalize_brands_unified(
            corrected_brands,
            vertical,
            vertical_description,
            ollama,
        )

        rejected_at_normalization = normalized_result.get("rejected", [])
        if rejected_at_normalization:
            logger.info(f"[Extraction] Rejected at normalization: {rejected_at_normalization}")

        validated_products = await _validate_products(
            ollama, corrected_products, text, vertical, vertical_description
        )

        rejected_products = set(corrected_products) - set(validated_products)
        if rejected_products:
            logger.info(f"[Extraction] Rejected at product validation: {list(rejected_products)}")

        normalized_brands = [
            b["canonical"] for b in normalized_result.get("brands", [])
        ]
        brand_chinese_map = {
            b["canonical"]: b.get("chinese", "")
            for b in normalized_result.get("brands", [])
        }

        logger.info(f"[Extraction] Normalized brands: {normalized_brands}")

        candidates = [
            EntityCandidate(name=b, source="qwen", entity_type="brand")
            for b in normalized_brands
        ] + [
            EntityCandidate(name=p, source="qwen", entity_type="product")
            for p in validated_products
        ]

        filtered = _filter_by_list_position(candidates, text)

        filtered_out_list = list(set(c.name for c in candidates) - set(c.name for c in filtered))
        if filtered_out_list:
            logger.info(f"[Extraction] Filtered by list position: {filtered_out_list}")

        brand_clusters: Dict[str, List[str]] = {}
        product_clusters: Dict[str, List[str]] = {}

        for c in filtered:
            if c.entity_type == "brand":
                chinese = brand_chinese_map.get(c.name, "")
                brand_clusters[c.name] = [c.name]
                if chinese:
                    brand_clusters[c.name].append(chinese)
            elif c.entity_type == "product":
                product_clusters[c.name] = [c.name]

        debug_info = ExtractionDebugInfo(
            raw_brands=brands,
            raw_products=products,
            rejected_at_normalization=rejected_at_normalization,
            rejected_at_validation=list(rejected_products),
            rejected_at_list_filter=filtered_out_list,
            final_brands=list(brand_clusters.keys()),
            final_products=list(product_clusters.keys()),
        )

        logger.info(
            f"[Extraction] Final: {len(brands)} raw -> "
            f"{len(normalized_brands)} normalized -> "
            f"{len(brand_clusters)} brands, {len(product_clusters)} products"
        )
        return ExtractionResult(brands=brand_clusters, products=product_clusters, debug_info=debug_info)

    except Exception as e:
        logger.error(f"Qwen extraction failed: {e}")
        return ExtractionResult(brands={}, products={})


def _build_extraction_system_prompt(vertical: str, vertical_description: str) -> str:
    vertical_context = f"Industry: {vertical}" if vertical else "Industry: General"
    if vertical_description:
        vertical_context += f"\nDescription: {vertical_description}"

    is_automotive = _is_automotive_vertical(vertical.lower())
    system_prompt = f"""You are an expert entity extractor for the {vertical or 'general'} industry.

TASK: Extract ALL genuine brand names and product names mentioned in the text.

CRITICAL: Scan the ENTIRE text from start to end. Do NOT skip entities that appear:
- At the start of sentences or list items
- Before comparison words like "similar to", "comparable to", "vs", "better than"
Example: "iPhone 15 is great, similar to Galaxy S24" -> Extract BOTH "iPhone 15" AND "Galaxy S24"

DEFINITIONS:
- BRAND: A company/manufacturer name that creates and sells products
  Examples: Toyota, Apple, Nike, 比亚迪, 欧莱雅, Samsung, BMW, 兰蔻
- PRODUCT: A specific model/item name made by a brand
  Examples: RAV4, iPhone 15, 宋PLUS, Galaxy S24, X5, 神仙水

CRITICAL - DO NOT EXTRACT:
- Generic terms or categories (SUV, smartphone, skincare, 汽车, 护肤品)
- Descriptive phrases (产品质量, 环保性能, advanced features, 性价比)
- Adjectives or modifiers alone (先进, 自主, premium, best, 好用)
- Partial phrases with prepositions (在选择, 与宝马, 和奥迪, "compared to X")
- Feature/technology names (CarPlay, GPS, AI, 新能源, hybrid)
- Quality descriptors (出色, excellent, 温和性好)
- Sentence fragments or non-entity text (Top1, 车型时)
- Rankings, numbers alone, or list markers

EXTRACTION RULES:
1. Extract the EXACT brand/product name as standalone text
2. Do NOT include surrounding words or prepositions
3. Products often contain model numbers/letters (X3, Q5, i7, V15, S24)
4. Brands are proper nouns (company names)
5. When unsure, DO NOT include - precision over recall
6. Separate brand from product (e.g., "大众途观" -> brand: "大众", product: "途观")
7. Pattern: "BrandName ModelNumber" (e.g., "Brand X1", "Brand 15 Pro"):
   - The word BEFORE the model number is usually the BRAND
   - The model number/alphanumeric code is the PRODUCT
8. Extract BOTH the brand AND product when they appear together"""

    if is_automotive:
        system_prompt += """

AUTOMOTIVE-SPECIFIC RULES:
- In the automotive industry, alphanumeric model codes (e.g., RAV4, H6, L9, BJ80, Q7, X5, CR-V) are PRODUCTS, not brands.
- The brand is the manufacturer (e.g., Toyota, Haval, Li Auto, Beijing Off-Road, Audi, BMW).
- For example: "Toyota RAV4" -> brand: "Toyota", product: "RAV4"
- If a model code is mentioned without the brand (e.g., "RAV4"), still extract it as a PRODUCT, but note that the brand may not be mentioned in the text.
"""

    system_prompt += f"""

{vertical_context}

OUTPUT FORMAT - Use this exact JSON structure:
{{
  "entities": [
    {{"name": "Toyota", "type": "brand"}},
    {{"name": "RAV4", "type": "product", "parent_brand": "Toyota"}},
    {{"name": "BYD", "type": "brand"}},
    {{"name": "宋PLUS", "type": "product", "parent_brand": "BYD"}}
  ]
}}

IMPORTANT:
- For each PRODUCT, include "parent_brand" if you know which brand makes it
- If unsure of parent_brand, omit the field
- "type" must be either "brand" or "product"
"""

    return system_prompt


def _build_extraction_prompt(text: str) -> str:
    text_snippet = text[:2000] if len(text) > 2000 else text
    return f"""Extract brands and products from this text:

{text_snippet}

Output JSON with "entities" array. For each entity include name, type (brand/product), and parent_brand if known:"""


def _build_brand_normalization_prompt(
    brands: List[str],
    vertical: str,
    vertical_description: str
) -> str:
    import json
    brands_json = json.dumps(brands, ensure_ascii=False)

    vertical_context = vertical
    if vertical_description:
        vertical_context = f"{vertical} ({vertical_description})"

    return f"""You are a brand normalization expert for the {vertical_context} industry.

TASK: Normalize and canonicalize this list of brand names. Do NOT reject any brands - just normalize them.

BRANDS TO PROCESS:
{brands_json}

FOR EACH BRAND, DO THE FOLLOWING:

1. JV/OWNER NORMALIZATION: Extract the consumer-facing brand
   - Chinese JV format: "中方+外方" -> Extract FOREIGN brand
   - Examples: 长安福特 -> Ford, 华晨宝马 -> BMW, 一汽大众 -> Volkswagen, 东风日产 -> Nissan
   - Owner+Brand format: "集团+品牌" -> Extract the BRAND
   - Examples: 上汽名爵 -> MG, 广汽传祺 -> Trumpchi, 上汽通用别克 -> Buick

2. ALIAS DEDUPLICATION: Merge duplicates to canonical English name
   - Same brand in different forms -> One canonical entry
   - Examples: Jeep + 吉普 -> Jeep, BYD + 比亚迪 -> BYD, 宝马 + BMW -> BMW

3. KEEP ALL BRANDS: Do not reject any brand. If unsure about canonicalization, keep the original name.

OUTPUT FORMAT (JSON only):
{{
  "brands": [
    {{"canonical": "English Name", "chinese": "中文名", "original_forms": ["form1", "form2"]}}
  ],
  "rejected": []
}}

IMPORTANT:
- canonical MUST be the English brand name (or original if no English name known)
- chinese should be the Chinese name if known, or empty string if not
- original_forms lists all input forms that map to this brand
- rejected should ALWAYS be an empty array - do not reject any brands
- Be thorough: normalize ALL JVs, merge ALL duplicates"""


def _parse_normalization_response(response: str) -> Dict:
    import json

    response = response.strip()
    if response.startswith("```json"):
        response = response[7:]
    if response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    response = response.strip()

    try:
        parsed = json.loads(response)
        return parsed
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

    return {"brands": [], "rejected": []}


def _parse_extraction_response(response: str) -> Dict[str, List[str]]:
    import json

    response = response.strip()

    if response.startswith("```"):
        parts = response.split("```")
        if len(parts) >= 2:
            response = parts[1]
            if response.startswith("json"):
                response = response[4:]
    response = response.strip()

    parsed = None
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

    if not parsed or not isinstance(parsed, dict):
        return {"brands": [], "products": [], "relationships": {}}

    if "entities" in parsed:
        return _parse_entities_format(parsed)

    return {
        "brands": parsed.get("brands", []),
        "products": parsed.get("products", []),
        "relationships": {},
    }


def _build_brand_validation_system_prompt(vertical: str, vertical_description: str) -> str:
    vertical_context = f"Industry: {vertical}" if vertical else "General market"
    if vertical_description:
        vertical_context += f" ({vertical_description})"

    return f"""You are a quality control expert validating BRAND extractions in the Chinese market for the {vertical_context} industry.

YOUR ROLE: Identify genuine brands while filtering obvious non-brands. 

TASK: For each candidate, determine if it is a genuine BRAND (company/manufacturer) - ACCEPT or REJECT.

---

WHAT IS A BRAND (ACCEPT):
A brand is a COMPANY or MANUFACTURER name - an organization that creates and sells products.
- Examples: Toyota, Apple, Nike, 比亚迪, Samsung, L'Oreal, Huawei, BMW, 华为, Adidas
- Must be a proper noun representing a business entity
- The company behind products, not the products themselves

---

CRITICAL: REJECT PRODUCTS - This is the most common error!
Products are NOT brands. Products are specific items MADE BY brands.
- RAV4, Camry, Corolla → These are Toyota PRODUCTS, not brands. REJECT.
- iPhone, MacBook, iPad → These are Apple PRODUCTS, not brands. REJECT.
- Model Y, Model 3 → These are Tesla PRODUCTS, not brands. REJECT.
- 宋PLUS, 汉EV, 秦Pro → These are BYD PRODUCTS, not brands. REJECT.
- Galaxy S24, Note → These are Samsung PRODUCTS, not brands. REJECT.
- Air Jordan, Air Max → These are Nike PRODUCTS, not brands. REJECT.

How to identify products vs brands:
- Products often have: model numbers (X5, S24), version suffixes (Pro, Plus, Max, EV, DM-i), or are specific item names
- Brands are company names that appear BEFORE products (e.g., "Toyota RAV4" → Toyota=brand, RAV4=product)

---

ALSO REJECT these non-brand categories:

1. GENERIC TERMS: Category names
   - SUV, sedan, smartphone, laptop, 汽车, 手机, 护肤品, electric vehicle

2. FEATURES/SPECIFICATIONS: Technical attributes
   - CarPlay, GPS, AWD, hybrid, 续航, 马力, OLED, 5G

3. QUALITY DESCRIPTORS: Evaluative terms
   - premium, best, 高端, 性价比高, 舒适, 安全, luxury

4. INDUSTRY JARGON: Technical terms
   - 新能源, 纯电动, all-wheel drive, turbocharged

5. PARTIAL/INCOMPLETE: Fragments
   - "在选择", "与奥迪", "Top1", "最好的"

6. MODIFIERS ALONE: Suffixes without product name
   - Pro, Max, Plus, Ultra, Mini, EV, DM-i (standalone)

7. ACTIONS/VERBS: Action words
   - 推荐, 选择, 购买, 比较

---

VALIDATION RULES:
1. If reasonably confident it's a company/manufacturer name, ACCEPT
2. ASK YOURSELF: "Is this a company that makes products, or is this a product itself?"
3. CONTEXT CHECK: Does it make sense as a manufacturer in {vertical_context}?
4. When uncertain about established company names (especially Chinese brands like 哈弗, 吉利, 长安, 荣威, 奇瑞), lean toward ACCEPT

---

OUTPUT FORMAT (JSON only):
{{
  "validations": [
    {{"entity": "Toyota", "decision": "ACCEPT", "reason": "Japanese automotive manufacturer"}},
    {{"entity": "RAV4", "decision": "REJECT", "reason": "Product model by Toyota, not a brand"}},
    {{"entity": "性价比", "decision": "REJECT", "reason": "Quality descriptor, not a company name"}}
  ]
}}"""


def _build_product_validation_system_prompt(vertical: str, vertical_description: str) -> str:
    vertical_context = f"Industry: {vertical}" if vertical else "General market"
    if vertical_description:
        vertical_context += f" ({vertical_description})"

    return f"""You are a quality control expert validating PRODUCT extractions for the {vertical_context} industry.

YOUR ROLE: Identify genuine products while filtering obvious non-products. When uncertain about a known product model, lean toward ACCEPT.

TASK: For each candidate, determine if it is a genuine PRODUCT (specific model/item) - ACCEPT or REJECT.

---

WHAT IS A PRODUCT (ACCEPT):
A product is a SPECIFIC MODEL or ITEM made by a brand/company.
- Examples: iPhone 15, Model Y, 宋PLUS, Galaxy S24, RAV4, Air Jordan 1, MacBook Pro
- Usually has: model numbers, version identifiers, or distinctive product line names
- Something you can buy as a specific item

---

CRITICAL: REJECT BRANDS - This is a common error!
Brands are COMPANIES, not products. Don't confuse the manufacturer with what they make.
- Toyota, Honda, BMW → These are COMPANIES that make cars. REJECT.
- Apple, Samsung, Huawei → These are COMPANIES that make phones. REJECT.
- Nike, Adidas → These are COMPANIES that make shoes. REJECT.
- 比亚迪, 蔚来, 理想 → These are COMPANIES that make EVs. REJECT.

How to identify brands vs products:
- Brands are company/manufacturer names
- Products are specific items WITH distinguishing identifiers (numbers, suffixes, model names)
- "Tesla Model Y" → Tesla=brand (REJECT), Model Y=product (ACCEPT)

---

ALSO REJECT these non-product categories:

1. GENERIC TERMS: Category names, not specific products
   - SUV, sedan, smartphone, 汽车, 手机 (these are categories, not specific products)

2. FEATURES/SPECIFICATIONS: Technical attributes
   - CarPlay, GPS, AWD, OLED, 5G, 续航, 马力

3. QUALITY DESCRIPTORS: Evaluative terms
   - premium, best, 高端, 性价比高, luxury, 舒适

4. INDUSTRY JARGON: Technical terms
   - 新能源, 纯电动, all-wheel drive, turbocharged

5. PARTIAL/INCOMPLETE: Fragments
   - "在选择", "与奥迪", "Top1", incomplete names

6. MODIFIERS ALONE: Suffixes without the base product
   - Pro, Max, Plus, Ultra, Mini, EV (must be attached to a product name)

---

VALIDATION RULES:
1. If reasonably confident it's a specific product model, ACCEPT
2. ASK YOURSELF: "Can I buy this specific item? Does it have a model number or distinctive name?"
3. CONTEXT CHECK: Does it make sense as a purchasable product in {vertical_context}?
4. When uncertain about product models with alphanumeric codes (H6, CS75, RX5, CR-V, RAV4), lean toward ACCEPT

---

OUTPUT FORMAT (JSON only):
{{
  "validations": [
    {{"entity": "Model Y", "decision": "ACCEPT", "reason": "Specific Tesla electric vehicle model"}},
    {{"entity": "Tesla", "decision": "REJECT", "reason": "Company/brand name, not a product"}},
    {{"entity": "SUV", "decision": "REJECT", "reason": "Generic vehicle category, not a specific product"}}
  ]
}}"""


def _build_brand_validation_prompt(brands: List[str], text_snippet: str, vertical: str) -> str:
    import json
    entities_json = json.dumps(brands, ensure_ascii=False)

    return f"""Validate these extracted BRAND candidates from {vertical or 'general'} industry text.

SOURCE TEXT (for context):
\"\"\"{text_snippet}\"\"\"

BRAND CANDIDATES TO VALIDATE:
{entities_json}

For EACH candidate, decide: ACCEPT (genuine company/manufacturer) or REJECT (product, generic term, or other).

Remember: Products like "RAV4", "iPhone", "Model Y" are NOT brands - they are products made BY brands.

When uncertain about established company names, lean toward ACCEPT.

Output JSON with "validations" array:"""


def _build_product_validation_prompt(products: List[str], text_snippet: str, vertical: str) -> str:
    import json
    entities_json = json.dumps(products, ensure_ascii=False)

    return f"""Validate these extracted PRODUCT candidates from {vertical or 'general'} industry text.

SOURCE TEXT (for context):
\"\"\"{text_snippet}\"\"\"

PRODUCT CANDIDATES TO VALIDATE:
{entities_json}

For EACH candidate, decide: ACCEPT (genuine specific product/model) or REJECT (brand, generic term, or other).

Remember: Company names like "Toyota", "Apple", "Nike" are NOT products - they are brands that MAKE products.

When uncertain about specific product models, lean toward ACCEPT.

Output JSON with "validations" array:"""


async def _validate_brands(
    ollama,
    brands: List[str],
    text: str,
    vertical: str,
    vertical_description: str,
) -> List[str]:
    if not brands:
        return []

    system_prompt = _build_brand_validation_system_prompt(vertical, vertical_description)
    text_snippet = text[:1500] if len(text) > 1500 else text
    prompt = _build_brand_validation_prompt(brands, text_snippet, vertical)

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )

        validated = _parse_single_type_validation_response(response, brands)

        rejected = set(brands) - set(validated)
        if rejected:
            logger.info(f"Brand validation rejected: {list(rejected)}")

        return validated

    except Exception as e:
        logger.warning(f"Brand validation failed, keeping all: {e}")
        return brands


async def _validate_products(
    ollama,
    products: List[str],
    text: str,
    vertical: str,
    vertical_description: str,
) -> List[str]:
    if not products:
        return []

    system_prompt = _build_product_validation_system_prompt(vertical, vertical_description)
    text_snippet = text[:1500] if len(text) > 1500 else text
    prompt = _build_product_validation_prompt(products, text_snippet, vertical)

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )

        validated = _parse_single_type_validation_response(response, products)

        rejected = set(products) - set(validated)
        if rejected:
            logger.info(f"Product validation rejected: {list(rejected)}")

        return validated

    except Exception as e:
        logger.warning(f"Product validation failed, keeping all: {e}")
        return products


async def _run_negative_validation(
    ollama,
    brands: List[str],
    products: List[str],
    text: str,
    vertical: str,
    vertical_description: str,
) -> Tuple[List[str], List[str]]:
    if not brands and not products:
        return [], []

    if ENABLE_BRAND_VALIDATION:
        validated_brands = await _validate_brands(
            ollama, brands, text, vertical, vertical_description
        )
    else:
        logger.info(f"[Extraction] Skipping brand validation (ENABLE_BRAND_VALIDATION=false), keeping all {len(brands)} brands")
        validated_brands = brands

    validated_products = await _validate_products(
        ollama, products, text, vertical, vertical_description
    )

    return validated_brands, validated_products


async def _normalize_brands_unified(
    brands: List[str],
    vertical: str,
    vertical_description: str,
    ollama,
) -> Dict:
    if not brands:
        return {"brands": [], "rejected": []}

    wikidata_known = []
    wikidata_rejected = []

    if ENABLE_WIKIDATA_NORMALIZATION:
        from src.services.wikidata_lookup import (
            get_canonical_brand_name,
            get_chinese_name,
            is_brand_in_vertical,
        )
        need_qwen = []
        for brand in brands:
            is_known, in_vertical = is_brand_in_vertical(brand, vertical)
            if is_known and in_vertical:
                canonical = get_canonical_brand_name(brand, vertical)
                chinese = get_chinese_name(brand, vertical)
                wikidata_known.append({
                    "canonical": canonical or brand,
                    "chinese": chinese or "",
                    "original_forms": [brand]
                })
            elif is_known and not in_vertical:
                wikidata_rejected.append({
                    "name": brand,
                    "reason": f"Known brand but not in {vertical} industry"
                })
            else:
                need_qwen.append(brand)
    else:
        need_qwen = list(brands)

    qwen_result = {"brands": [], "rejected": []}
    if need_qwen:
        prompt = _build_brand_normalization_prompt(
            need_qwen, vertical, vertical_description
        )
        try:
            response = await ollama._call_ollama(
                model=ollama.ner_model,
                prompt=prompt,
                system_prompt="",
                temperature=0.0,
            )
            qwen_result = _parse_normalization_response(response)
        except Exception as e:
            logger.warning(f"Brand normalization failed: {e}")
            for brand in need_qwen:
                qwen_result["brands"].append({
                    "canonical": brand,
                    "chinese": "",
                    "original_forms": [brand]
                })

    all_brands = _merge_and_deduplicate_brands(
        wikidata_known, qwen_result.get("brands", [])
    )
    all_rejected = wikidata_rejected + qwen_result.get("rejected", [])

    logger.info(
        f"Brand normalization: {len(brands)} input -> "
        f"{len(all_brands)} normalized, {len(all_rejected)} rejected"
    )

    return {"brands": all_brands, "rejected": all_rejected}


def _merge_and_deduplicate_brands(
    wikidata_brands: List[Dict],
    qwen_brands: List[Dict]
) -> List[Dict]:
    canonical_map: Dict[str, Dict] = {}

    for brand in wikidata_brands:
        canonical = brand.get("canonical", "").lower()
        if not canonical:
            continue
        if canonical not in canonical_map:
            canonical_map[canonical] = {
                "canonical": brand.get("canonical", ""),
                "chinese": brand.get("chinese", ""),
                "original_forms": []
            }
        canonical_map[canonical]["original_forms"].extend(
            brand.get("original_forms", [])
        )

    for brand in qwen_brands:
        canonical = brand.get("canonical", "").lower()
        if not canonical:
            continue
        if canonical not in canonical_map:
            canonical_map[canonical] = {
                "canonical": brand.get("canonical", ""),
                "chinese": brand.get("chinese", ""),
                "original_forms": []
            }
        else:
            if not canonical_map[canonical]["chinese"] and brand.get("chinese"):
                canonical_map[canonical]["chinese"] = brand.get("chinese", "")
        canonical_map[canonical]["original_forms"].extend(
            brand.get("original_forms", [])
        )

    for key in canonical_map:
        canonical_map[key]["original_forms"] = list(
            dict.fromkeys(canonical_map[key]["original_forms"])
        )

    return list(canonical_map.values())


def _parse_single_type_validation_response(response: str, original_entities: List[str]) -> List[str]:
    import json

    response = response.strip()
    if response.startswith("```json"):
        response = response[7:]
    if response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    response = response.strip()

    parsed = None
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

    if not parsed or "validations" not in parsed:
        logger.warning("Could not parse validation response, keeping all entities")
        return original_entities

    validated = []
    entity_decisions = {}

    for item in parsed.get("validations", []):
        if not isinstance(item, dict):
            continue

        entity = item.get("entity", "")
        decision = item.get("decision", "").upper()

        entity_decisions[entity] = decision

        if decision == "ACCEPT":
            validated.append(entity)

    for entity in original_entities:
        if entity not in entity_decisions:
            validated.append(entity)

    return validated


def _parse_entities_format(parsed: Dict) -> Dict[str, List[str]]:
    brands = []
    products = []
    relationships = {}

    for entity in parsed.get("entities", []):
        if not isinstance(entity, dict):
            continue

        name = entity.get("name", "")
        entity_type = entity.get("type", "")
        parent_brand = entity.get("parent_brand")

        if not name:
            continue

        if entity_type == "brand":
            brands.append(name)
        elif entity_type == "product":
            products.append(name)
            if parent_brand:
                relationships[name] = parent_brand

    return {"brands": brands, "products": products, "relationships": relationships}


def _filter_by_list_position(candidates: List[EntityCandidate], text: str) -> List[EntityCandidate]:
    if not is_list_format(text):
        return candidates

    list_items = split_into_list_items(text)
    if not list_items:
        return candidates

    allowed_brands: Set[str] = set()
    allowed_products: Set[str] = set()

    intro_text = _get_intro_text(text)
    if intro_text:
        _add_all_entities_from_text(intro_text, candidates, allowed_brands, allowed_products)

    for item in list_items:
        primary = _extract_first_brand_and_product_from_item(item, candidates)
        if primary["brand"]:
            allowed_brands.add(primary["brand"].lower())
        if primary["product"]:
            allowed_products.add(primary["product"].lower())

    filtered = _match_candidates_to_allowed(candidates, allowed_brands, allowed_products)
    logger.info(f"List position filter: {len(candidates)} -> {len(filtered)} candidates")
    return filtered


def _match_candidates_to_allowed(
    candidates: List[EntityCandidate],
    allowed_brands: Set[str],
    allowed_products: Set[str]
) -> List[EntityCandidate]:
    filtered: List[EntityCandidate] = []
    allowed_all = allowed_brands | allowed_products

    for candidate in candidates:
        name_lower = candidate.name.lower()

        if name_lower in allowed_all:
            filtered.append(candidate)
            continue

        if _candidate_matches_allowed(name_lower, allowed_brands):
            filtered.append(candidate)
            continue

        if _candidate_matches_allowed(name_lower, allowed_products):
            filtered.append(candidate)
            continue

    return filtered


def _candidate_matches_allowed(candidate_lower: str, allowed_set: Set[str]) -> bool:
    for allowed in allowed_set:
        if candidate_lower in allowed:
            return True
        if allowed == candidate_lower:
            return True
        if _is_clean_substring_match(allowed, candidate_lower):
            return True
    return False


def _is_clean_substring_match(allowed: str, candidate: str) -> bool:
    if allowed not in candidate:
        return False
    if len(candidate) > len(allowed) * 4:
        return False
    extra = candidate.replace(allowed, "", 1).strip()
    if re.search(r"[\u4e00-\u9fff]{2,}", extra):
        return False
    if _extra_is_valid(extra):
        return True
    if re.search(r"[a-z]{3,}", extra):
        return False
    return True


def _extra_is_valid(extra: str) -> bool:
    words = extra.lower().split()
    for word in words:
        word = word.strip()
        if not word:
            continue
        if word in VALID_EXTRA_TERMS:
            continue
        if word.isdigit():
            continue
        if re.match(r"^\d+[a-z]{0,2}$", word):
            continue
        return False
    return True


def _add_all_entities_from_text(
    text: str, candidates: List[EntityCandidate], brands: Set[str], products: Set[str]
) -> None:
    text_lower = text.lower()
    for candidate in candidates:
        name_lower = candidate.name.lower()
        if name_lower in text_lower:
            if candidate.entity_type == "brand":
                brands.add(name_lower)
            elif candidate.entity_type == "product" or name_lower in PRODUCT_HINTS:
                products.add(name_lower)
            elif _has_brand_patterns(candidate.name):
                brands.add(name_lower)
            elif _has_product_patterns(candidate.name):
                products.add(name_lower)


def _extract_first_brand_and_product_from_item(
    item: str, candidates: List[EntityCandidate]
) -> Dict[str, str | None]:
    result: Dict[str, str | None] = {"brand": None, "product": None}

    primary_region = _get_primary_region(item)
    primary_region_lower = primary_region.lower()

    candidate_brands: List[Tuple[int, int, str]] = []
    candidate_products: List[Tuple[int, int, str]] = []

    for candidate in candidates:
        name = candidate.name
        name_lower = name.lower()
        pos = primary_region_lower.find(name_lower)
        if pos == -1:
            continue

        is_brand = candidate.entity_type == "brand"
        is_product = candidate.entity_type == "product"

        if is_brand:
            candidate_brands.append((pos, -len(name), name))
        elif is_product:
            candidate_products.append((pos, -len(name), name))
        elif _looks_like_product(name) or _has_product_patterns(name):
            candidate_products.append((pos, -len(name), name))
        elif _has_brand_patterns(name):
            candidate_brands.append((pos, -len(name), name))

    if candidate_brands:
        candidate_brands.sort(key=lambda x: (x[0], x[1]))
        result["brand"] = candidate_brands[0][2]

    if candidate_products:
        candidate_products.sort(key=lambda x: (x[0], x[1]))
        result["product"] = candidate_products[0][2]

    if result["product"] is None:
        known_products: List[Tuple[int, int, str]] = []
        for product in KNOWN_PRODUCTS:
            pos = primary_region_lower.find(product.lower())
            if pos != -1:
                known_products.append((pos, -len(product), product))
        if known_products:
            known_products.sort(key=lambda x: (x[0], x[1]))
            result["product"] = known_products[0][2]

    return result


def _looks_like_product(name: str) -> bool:
    if re.search(r"\d", name):
        return True
    if re.search(r"(PLUS|Plus|Pro|Max|Ultra|Mini|EV|DM)", name):
        return True
    return False


def _get_intro_text(text: str) -> str | None:
    first_marker_idx = _find_first_list_item_index(text)
    if first_marker_idx > 0:
        return text[:first_marker_idx].strip()
    return None


def _get_primary_region(item: str) -> str:
    cutoff = _find_first_cutoff(item)
    return item[:cutoff] if cutoff else item


def _find_first_cutoff(item: str) -> int | None:
    cutoff_positions = []

    for marker in COMPARISON_MARKERS:
        pos = item.find(marker)
        if pos != -1:
            cutoff_positions.append(pos)

    for sep in CLAUSE_SEPARATORS:
        pos = item.find(sep)
        if pos != -1 and pos > 5:
            cutoff_positions.append(pos)

    return min(cutoff_positions) if cutoff_positions else None


def generate_candidates(text: str, primary_brand: str, aliases: Dict[str, List[str]]) -> List[EntityCandidate]:
    seeds = _seed_primary(primary_brand, aliases)
    alias_hits = _alias_hits(text, _default_alias_table())
    hanlp_entities = _extract_with_hanlp(text)
    ltp_entities = _extract_with_ltp(text)
    regex_hits = _regex_candidates(text)
    quoted_hits = _quoted_candidates(text)
    list_hits = _list_table_candidates(text)

    names = seeds | alias_hits | hanlp_entities | ltp_entities | regex_hits | quoted_hits | list_hits
    names |= _expand_subtokens(names)

    return [
        EntityCandidate(
            name=n,
            source=_candidate_source(n, seeds, hanlp_entities, ltp_entities, regex_hits, quoted_hits, list_hits)
        )
        for n in names
    ]


async def _filter_candidates_with_qwen(
    candidates: List[EntityCandidate],
    text: str,
    vertical: str = "",
    vertical_description: str = ""
) -> List[EntityCandidate]:
    from services.ollama import OllamaService

    filtered = []
    needs_qwen_verification = []

    for candidate in candidates:
        name_lower = candidate.name.lower()
        if name_lower in GENERIC_TERMS:
            continue
        if candidate.source == "seed":
            candidate.entity_type = "brand"
            filtered.append(candidate)
        elif name_lower in KNOWN_PRODUCTS:
            candidate.entity_type = "product"
            filtered.append(candidate)
        elif _is_valid_brand_candidate(candidate.name):
            filtered.append(candidate)
        elif _might_be_brand_needs_verification(candidate.name):
            needs_qwen_verification.append(candidate)

    if needs_qwen_verification:
        ollama = OllamaService()
        batch_results = await _batch_verify_entities_with_qwen(
            ollama, needs_qwen_verification, text, vertical, vertical_description
        )
        for candidate in needs_qwen_verification:
            entity_type = batch_results.get(candidate.name, "other")
            if entity_type in ["brand", "product"]:
                candidate.entity_type = entity_type
                filtered.append(candidate)

    logger.info(f"Qwen filtering: {len(candidates)} -> {len(filtered)} candidates")
    return filtered


def _might_be_brand_needs_verification(name: str) -> bool:
    if len(name) < 2 or len(name) > 30:
        return False

    if _contains_feature_keywords(name):
        return False

    if re.search(r"[、，。！？：；]", name):
        return False

    if re.search(r"[\u4e00-\u9fff]{2,}", name):
        return True

    if re.search(r"[A-Za-z]{2,}", name):
        return True

    return False


async def _batch_verify_entities_with_qwen(
    ollama,
    candidates: List[EntityCandidate],
    text: str,
    vertical: str = "",
    vertical_description: str = "",
    batch_size: int = 30
) -> Dict[str, str]:
    results: Dict[str, str] = {}

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        batch_results = await _verify_batch_with_qwen(ollama, batch, text, vertical, vertical_description)
        results.update(batch_results)

    return results


async def _verify_batch_with_qwen(
    ollama,
    batch: List[EntityCandidate],
    text: str,
    vertical: str = "",
    vertical_description: str = ""
) -> Dict[str, str]:
    import json

    candidate_names = [c.name for c in batch]
    text_snippet = text[:1500] if len(text) > 1500 else text

    brand_results = await _verify_brands_with_qwen(
        ollama, candidate_names, text_snippet, vertical, vertical_description
    )

    remaining = [n for n in candidate_names if brand_results.get(n) != "brand"]

    product_results = {}
    if remaining:
        product_results = await _verify_products_with_qwen(
            ollama, remaining, text_snippet, vertical, vertical_description
        )

    final_results: Dict[str, str] = {}
    for name in candidate_names:
        if brand_results.get(name) == "brand":
            final_results[name] = "brand"
        elif product_results.get(name) == "product":
            final_results[name] = "product"
        else:
            final_results[name] = "other"

    return final_results


async def _verify_brands_with_qwen(
    ollama,
    candidates: List[str],
    text: str,
    vertical: str = "",
    vertical_description: str = ""
) -> Dict[str, str]:
    import json

    candidates_json = json.dumps(candidates, ensure_ascii=False)

    vertical_info = f"Industry: {vertical}" if vertical else "Industry: General"
    if vertical_description:
        vertical_info += f"\nDescription: {vertical_description}"

    system_prompt = f"""You are an expert at identifying BRAND names (companies/manufacturers) in the {vertical or 'general'} industry.

YOUR TASK: For each candidate, determine if it is a BRAND (company/manufacturer name).

WHAT IS A BRAND:
- A company or manufacturer that creates and sells products
- Examples: Toyota, Honda, BYD, 比亚迪, Tesla, BMW, Apple, Samsung, Nike, L'Oreal
- The name of an organization that owns product lines

WHAT IS NOT A BRAND (classify as "other"):
- Product/model names (RAV4, iPhone, Model Y) - these are NOT brands
- Generic category terms (SUV, sedan, smartphone, laptop, 汽车)
- Feature/technology words (CarPlay, GPS, LED, AWD, hybrid)
- Common modifiers (One, Pro, Max, Plus, Ultra, Mini)
- Quality descriptors (best, premium, good, popular)
- Industry jargon or technical terms

Output JSON array with classification for EACH candidate:
[{{"name": "candidate1", "is_brand": true}}, {{"name": "candidate2", "is_brand": false}}]"""

    prompt = f"""{vertical_info}

Source text for context:
{text}

Candidates to evaluate:
{candidates_json}

For EACH candidate above, determine if it is a BRAND (company/manufacturer).
Output JSON array only:"""

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )
        return _parse_brand_verification_response(response, candidates)
    except Exception as e:
        logger.warning(f"Brand verification failed: {e}")
        return {}


async def _verify_products_with_qwen(
    ollama,
    candidates: List[str],
    text: str,
    vertical: str = "",
    vertical_description: str = ""
) -> Dict[str, str]:
    import json

    candidates_json = json.dumps(candidates, ensure_ascii=False)

    vertical_info = f"Industry: {vertical}" if vertical else "Industry: General"
    if vertical_description:
        vertical_info += f"\nDescription: {vertical_description}"

    system_prompt = f"""You are an expert at identifying PRODUCT names (specific models/items) in the {vertical or 'general'} industry.

YOUR TASK: For each candidate, determine if it is a PRODUCT (specific model/item name).

WHAT IS A PRODUCT:
- A specific model, item, or product line made by a brand
- Usually has model numbers, letters, or distinguishing names
- Examples: RAV4, CRV, Model Y, 宋PLUS, X5, iPhone 15, Galaxy S24, Air Max
- Can include variants: Model Y Long Range, 宋PLUS DM-i

WHAT IS NOT A PRODUCT (classify as "other"):
- Brand/company names (Toyota, Apple, Nike) - these are NOT products
- Generic category terms (SUV, sedan, smartphone, 汽车, 电动车)
- Feature/technology words (CarPlay, GPS, LED, AWD, hybrid)
- Standalone modifiers not attached to product (One, Pro, Max)
- Quality descriptors (best, premium, good)
- Industry jargon or technical terms

Output JSON array with classification for EACH candidate:
[{{"name": "candidate1", "is_product": true}}, {{"name": "candidate2", "is_product": false}}]"""

    prompt = f"""{vertical_info}

Source text for context:
{text}

Candidates to evaluate:
{candidates_json}

For EACH candidate above, determine if it is a PRODUCT (specific model/item).
Output JSON array only:"""

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )
        return _parse_product_verification_response(response, candidates)
    except Exception as e:
        logger.warning(f"Product verification failed: {e}")
        return {}


def _parse_brand_verification_response(response: str, candidates: List[str]) -> Dict[str, str]:
    parsed = _parse_batch_json_response(response)
    if not parsed:
        return {}

    results: Dict[str, str] = {}
    for item in parsed:
        if isinstance(item, dict) and "name" in item:
            name = item["name"]
            is_brand = item.get("is_brand", False)
            if is_brand:
                results[name] = "brand"

    return results


def _parse_product_verification_response(response: str, candidates: List[str]) -> Dict[str, str]:
    parsed = _parse_batch_json_response(response)
    if not parsed:
        return {}

    results: Dict[str, str] = {}
    for item in parsed:
        if isinstance(item, dict) and "name" in item:
            name = item["name"]
            is_product = item.get("is_product", False)
            if is_product:
                results[name] = "product"

    return results


def _calculate_confidence_scores(entities: List[str], vertical: str, is_brand: bool) -> Dict[str, float]:
    scores = {}

    for entity in entities:
        entity_lower = entity.lower()
        confidence = 0.5

        if is_brand:
            confidence = _calculate_brand_confidence(entity, entity_lower, vertical)
        else:
            confidence = _calculate_product_confidence(entity, entity_lower, vertical)

        scores[entity] = max(0.1, min(0.95, confidence))

    return scores


def _calculate_brand_confidence(entity: str, entity_lower: str, vertical: str) -> float:
    if entity_lower in GENERIC_TERMS:
        return 0.2

    if _has_product_model_patterns(entity):
        return 0.3

    if _has_product_suffix(entity):
        return 0.35

    if vertical and _check_wikidata_brand(entity, vertical):
        return 0.92

    if is_likely_brand(entity):
        return 0.8

    if re.search(r"[\u4e00-\u9fff]{2,4}$", entity) and not re.search(r"\d", entity):
        return 0.7

    if re.match(r"^[A-Z][a-z]+$", entity) and len(entity) >= 4:
        return 0.7

    if re.match(r"^[A-Z]{2,5}$", entity):
        return 0.65

    return 0.5


def _calculate_product_confidence(entity: str, entity_lower: str, vertical: str) -> float:
    if entity_lower in GENERIC_TERMS:
        return 0.2

    if vertical and _check_wikidata_product(entity, vertical):
        return 0.92

    if _has_product_model_patterns(entity):
        return 0.85

    if _has_product_suffix(entity):
        return 0.8

    if entity_lower in PRODUCT_HINTS:
        return 0.9

    if is_likely_product(entity):
        return 0.8

    if re.search(r"[\u4e00-\u9fff]{2,4}$", entity) and not re.search(r"\d", entity):
        return 0.4

    if re.match(r"^[A-Z][a-z]+$", entity) and len(entity) >= 4:
        return 0.4

    return 0.5


def _check_wikidata_brand(entity: str, vertical: str) -> bool:
    try:
        if not wikidata_cache_available():
            return False
        return wikidata_is_known_brand(entity, vertical)
    except Exception:
        return False


def _check_wikidata_product(entity: str, vertical: str) -> bool:
    try:
        if not wikidata_cache_available():
            return False
        return wikidata_is_known_product(entity, vertical)
    except Exception:
        return False


async def _verify_ambiguous_entities_with_qwen(
    ollama,
    ambiguous_entities: List[str],
    text: str,
    vertical: str = "",
    vertical_description: str = ""
) -> Dict[str, str]:
    """Verify ambiguous entities with Qwen."""
    import json
    
    if not ambiguous_entities:
        return {}

    candidates = [EntityCandidate(name=e, source="ambiguous") for e in ambiguous_entities]

    batch_results = await _verify_batch_with_qwen(
        ollama, candidates, text, vertical, vertical_description
    )
    
    return batch_results


def _has_product_patterns(name: str) -> bool:
    if _has_product_model_patterns(name):
        return True

    if _has_product_suffix(name):
        return True

    name_lower = name.lower()
    if name_lower in PRODUCT_HINTS:
        return True

    return False


def _has_brand_patterns(name: str) -> bool:
    if _has_product_model_patterns(name):
        return False

    if _has_product_suffix(name):
        return False

    if re.match(r"^[A-Z][a-z]+$", name) and len(name) >= 4:
        return True

    if re.search(r"[\u4e00-\u9fff]{2,4}$", name) and not re.search(r"\d", name):
        return True

    if re.match(r"^[A-Z]{2,5}$", name) and name not in {"EV", "DM", "AI", "VR", "AR"}:
        return True

    if re.search(r"(Inc|Corp|Co|Ltd|LLC|GmbH|AG|公司|集团|企业)$", name, re.IGNORECASE):
        return True

    return False



def _parse_batch_json_response(response: str) -> List[Dict] | None:
    import json

    response = response.strip()

    if response.startswith("```json"):
        response = response[7:]
    if response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    response = response.strip()

    try:
        result = json.loads(response)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    array_match = re.search(r'\[[\s\S]*\]', response)
    if array_match:
        try:
            result = json.loads(array_match.group(0))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return None


def _filter_candidates_simple(candidates: List[EntityCandidate]) -> List[EntityCandidate]:
    filtered = []
    for candidate in candidates:
        if candidate.source == "seed":
            filtered.append(candidate)
        elif _is_valid_brand_candidate(candidate.name):
            filtered.append(candidate)
    logger.info(f"Simple filtering: {len(candidates)} -> {len(filtered)} candidates")
    return filtered


def _contains_feature_keywords(name: str) -> bool:
    keywords = [
        "动力",
        "天窗",
        "后备箱",
        "品牌口碑",
        "舒适",
        "空间",
        "配置",
        "自动驾驶",
        "主动安全",
        "车机系统",
        "发动机",
        "变速箱",
        "维修"
    ]
    return any(keyword in name for keyword in keywords)


def _is_valid_brand_candidate(name: str) -> bool:
    if len(name) < 2 or len(name) > 30:
        return False

    feature_descriptor_patterns = [
        r"等$",
        r"[\u4e00-\u9fff]+度$",
        r"[\u4e00-\u9fff]+性$",
        r"[\u4e00-\u9fff]+率$",
        r"[\u4e00-\u9fff]+感$",
        r"[\u4e00-\u9fff]+力$",
        r"[\u4e00-\u9fff]+量$",
        r"(效果|功能|特点|优点|缺点|成分|配置|体验|表现|质地|口感|触感)",
        r"(空间|时间|速度|距离|重量|容量|尺寸|含量|纯度|亮度|硬度|粘度)",
        r"(良好|优秀|出色|卓越|强劲|轻薄|厚重|柔软|坚固|充足|丰富|均衡)",
        r"(大小|高低|长短|粗细|厚薄)",
        r"^更[\u4e00-\u9fff]+$",
        r"^很[\u4e00-\u9fff]+$",
        r"^非常[\u4e00-\u9fff]+$",
        r"(舒适|保暖|透气|耐用|防水|防滑)",
        r"^[\u4e00-\u9fff]{7,}$",
    ]

    for pattern in feature_descriptor_patterns:
        if re.search(pattern, name):
            return False

    if _contains_feature_keywords(name):
        return False

    generic_stop_words = {
        "最好", "推荐", "性能", "价格", "质量", "选择",
        "品牌", "产品", "类型", "种类", "系列", "排行",
        "国产", "进口", "豪华", "高端", "入门", "国产品牌",
        "安全性", "可靠性", "舒适性", "性价比", "适口性",
        "猫粮", "狗粮", "补剂", "胶原蛋白",
        "扫地机", "吸尘器", "处方粮",
        "温和性好", "性价比高", "肤感舒适", "适合敏感肌",
    }

    if name.lower() in {w.lower() for w in generic_stop_words}:
        return False

    compound_descriptor_endings = ["高", "好", "强", "差", "低", "等", "改善", "提升", "规划", "方面", "指标"]
    if len(name) > 2 and any(name.endswith(ending) for ending in compound_descriptor_endings):
        has_brand_pattern = any(re.search(pattern, name) for pattern in [
            r"[A-Za-z]+",
            r"\d+",
            r"(PLUS|Plus|Pro|Max|Ultra|Mini|DM-i)"
        ])
        if not has_brand_pattern:
            return False

    if len(name) > 4 and any(keyword in name for keyword in ["推荐", "适合", "保湿", "消化", "粪便", "噪音", "品质", "安全性", "操作", "智能"]):
        return False

    if re.search(r"[、，。！？：；]", name):
        return False

    brand_product_patterns = [
        r"^[A-Z]{2,}[\-]?[A-Z0-9]*$",
        r"[A-Za-z]+\d+",
        r"\d+[A-Za-z]+",
        r"Model\s?[A-ZX0-9]",
        r"ID\.",
        r"[\u4e00-\u9fff]{1,6}(PLUS|Plus|Pro|Max|Ultra|Mini|DM-i|DM-p|EV)",
        r"[\u4e00-\u9fff]{2,6}\d{1,3}\s+(Pro|Max|Plus|Ultra|Mini|DM-i|DM-p|EV)",
        r"[\u4e00-\u9fff]{2,6}[A-Z]\d{1,2}",
        r"[\u4e00-\u9fff]{2,6}\d{1,3}",
        r"^[\u4e00-\u9fff]{2,8}$",
        r"^[A-Za-z]{2,}$",
        r"[A-Za-z]{2,}[\u4e00-\u9fff]+",
        r"[\u4e00-\u9fff]+[A-Za-z]{2,}",
        r"[A-Z][a-z]+[A-Z]",
        r"[A-Z][a-z]+\s+\d+",
        r"[A-Z][a-z]+\s+[A-Z][a-z]+(\s+\d+)?",
        r"[A-Z][a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+",
    ]

    for pattern in brand_product_patterns:
        if re.search(pattern, name):
            return True

    return False


def _simple_clustering(
    embedding_clusters: Dict[str, List[EntityCandidate]],
    primary_brand: str,
    aliases: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    from difflib import SequenceMatcher

    normalized_aliases = _build_alias_lookup(primary_brand, aliases, _default_alias_table())
    final_clusters: Dict[str, Set[str]] = {}

    for cluster_key, cluster_members in embedding_clusters.items():
        normalized = _normalize_text(cluster_key)

        product_canonical = _extract_product_canonical(normalized)
        if product_canonical:
            canonical = product_canonical
        else:
            canonical = normalized_aliases.get(normalized)
            if not canonical:
                canonical = _match_substring_alias(normalized, normalized_aliases)
            if not canonical:
                canonical = _fuzzy_match(normalized, normalized_aliases)
            if not canonical:
                canonical = normalized

        final_clusters.setdefault(canonical, set()).update(m.name for m in cluster_members)

    logger.info(f"Simple clustering: {len(embedding_clusters)} clusters -> {len(final_clusters)} final clusters")
    return {k: sorted(v) for k, v in final_clusters.items() if k}


def _extract_product_canonical(normalized: str) -> str | None:
    for product in KNOWN_PRODUCTS:
        product_norm = _normalize_text(product)
        if product_norm in normalized and normalized != product_norm:
            remaining = normalized.replace(product_norm, "").strip()
            if not remaining:
                continue
            if _remaining_is_brand_and_suffix(remaining):
                return product_norm
    return None


def _remaining_is_brand_and_suffix(remaining: str) -> bool:
    return False


def _fuzzy_match(normalized: str, lookup: Dict[str, str]) -> str | None:
    from difflib import SequenceMatcher

    candidates = list(lookup.keys())
    if not candidates:
        return None
    scores = [(SequenceMatcher(a=normalized, b=option).ratio(), option) for option in candidates]
    best_score, best_option = max(scores, key=lambda item: item[0])
    if best_score >= 0.82:
        if best_option != normalized:
            if _has_variant_signals(normalized) and not _has_variant_signals(best_option):
                logger.debug(f"Merge constraint (fuzzy): '{normalized}' has variant signals, '{best_option}' doesn't - skipping merge")
                return None

            if len(normalized) > len(best_option) and best_option in normalized:
                suffix = normalized[len(best_option):]
                if _has_variant_signals(suffix):
                    logger.debug(f"Merge constraint (fuzzy): suffix '{suffix}' has variant signals - skipping merge")
                    return None

        return lookup[best_option]
    return None


async def _verify_entity_with_qwen(ollama, name: str, text: str) -> Dict | None:
    import json

    evidence = _extract_evidence(name, text)
    if not evidence:
        logger.warning(f"No evidence found for '{name}' in text")
        return None

    system_prompt = """You are a brand recognition expert. Analyze the provided candidate entity ONLY based on the evidence from the source text.

CRITICAL RULES:
1. DO NOT invent or hallucinate entities not in the candidate or evidence
2. Base your classification ONLY on the provided evidence snippet
3. Output ONLY valid JSON in the exact format specified

Classify the entity as:
- "brand": A brand/company name (e.g., 比亚迪, Tesla, Loreal)
- "product": A specific product/model name (e.g., 宋PLUS, iPhone14, Mate50)
- "other": Feature descriptions, quality descriptors, generic terms (e.g., 保湿效果, 性价比, 空间)

Output format (JSON only, no additional text):
{
  "type": "brand|product|other",
  "canonical_guess": "normalized form (optional)",
  "confidence": 0.0-1.0,
  "why": "one short reason"
}"""

    prompt = f"""Candidate: "{name}"

Evidence from text:
{evidence['snippet']}

Offsets: character {evidence['start']}-{evidence['end']}

Classify this candidate based ONLY on the evidence above. Output JSON only:"""

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )

        result = _parse_json_response(response)
        if not result:
            logger.warning(f"Failed to parse JSON for '{name}': {response[:100]}")
            return None

        required_fields = ["type", "confidence", "why"]
        if not all(field in result for field in required_fields):
            logger.warning(f"Missing required fields in response for '{name}': {result}")
            return None

        if result["type"] not in ["brand", "product", "other"]:
            logger.warning(f"Invalid type '{result['type']}' for '{name}'")
            return None

        return result

    except Exception as e:
        logger.warning(f"Qwen verification failed for '{name}': {e}")
        return None


def _extract_evidence(name: str, text: str, context_chars: int = 50) -> Dict | None:
    name_lower = name.lower()
    text_lower = text.lower()

    start_pos = text_lower.find(name_lower)
    if start_pos == -1:
        return None

    end_pos = start_pos + len(name)

    snippet_start = max(0, start_pos - context_chars)
    snippet_end = min(len(text), end_pos + context_chars)

    snippet = text[snippet_start:snippet_end]

    if snippet_start > 0:
        snippet = "..." + snippet
    if snippet_end < len(text):
        snippet = snippet + "..."

    return {
        "snippet": snippet,
        "start": start_pos,
        "end": end_pos,
        "mention": text[start_pos:end_pos]
    }


def _parse_json_response(response: str) -> Dict | None:
    import json

    response = response.strip()

    if response.startswith("```json"):
        response = response[7:]
    if response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    response = response.strip()

    try:
        return json.loads(response)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

    return None


async def _get_embeddings_ollama(texts: List[str]) -> List[List[float]]:
    from services.ollama import OllamaService
    ollama = OllamaService()
    return await ollama.get_embeddings(texts, model=OLLAMA_EMBEDDING_MODEL)


async def _cluster_with_embeddings(candidates: List[EntityCandidate]) -> Dict[str, List[EntityCandidate]]:
    if not candidates:
        return {}

    try:
        names = [c.name for c in candidates]
        raw_embeddings = await _get_embeddings_ollama(names)
        embeddings = _normalize_embeddings(raw_embeddings)

        similarity_threshold = 0.85
        clusters = {}
        used = set()

        for i, candidate_i in enumerate(candidates):
            if i in used:
                continue

            cluster_key = candidate_i.name
            cluster_members = [candidate_i]
            used.add(i)

            for j in range(i + 1, len(candidates)):
                if j in used:
                    continue

                similarity = float(np.dot(embeddings[i], embeddings[j]))

                if similarity >= similarity_threshold:
                    cluster_members.append(candidates[j])
                    used.add(j)

            clusters[cluster_key] = cluster_members

        logger.info(f"Embedding clustering: {len(candidates)} candidates -> {len(clusters)} clusters")
        return clusters

    except Exception as e:
        logger.warning(f"Embedding clustering failed: {e}. Falling back to individual candidates.")
        return {c.name: [c] for c in candidates}


def _normalize_embeddings(embeddings: List[List[float]]) -> np.ndarray:
    arr = np.array(embeddings)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return arr / norms


async def _llm_assisted_clustering(
    embedding_clusters: Dict[str, List[EntityCandidate]],
    primary_brand: str,
    aliases: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    from services.ollama import OllamaService

    ollama = OllamaService()
    normalized_aliases = _build_alias_lookup(primary_brand, aliases, _default_alias_table())

    final_clusters: Dict[str, Set[str]] = {}

    for cluster_key, cluster_members in embedding_clusters.items():
        normalized = _normalize_text(cluster_key)

        canonical = normalized_aliases.get(normalized)
        if canonical:
            final_clusters.setdefault(canonical, set()).update(m.name for m in cluster_members)
            continue

        canonical = _match_substring_alias(normalized, normalized_aliases)
        if canonical:
            final_clusters.setdefault(canonical, set()).update(m.name for m in cluster_members)
            continue

        if len(cluster_members) == 1:
            final_clusters.setdefault(normalized, set()).add(cluster_members[0].name)
            continue

        verified_canonical = await _verify_cluster_with_qwen(ollama, cluster_members)
        if verified_canonical:
            final_clusters.setdefault(verified_canonical, set()).update(m.name for m in cluster_members)
        else:
            for member in cluster_members:
                final_clusters.setdefault(_normalize_text(member.name), set()).add(member.name)

    return {k: sorted(v) for k, v in final_clusters.items() if k}


async def _verify_cluster_with_qwen(ollama, members: List[EntityCandidate]) -> str | None:
    if len(members) < 2:
        return None

    names_list = [m.name for m in members]
    system_prompt = """You are a brand clustering expert. Determine if the given names refer to the same brand or product.

If they are the same or aliases of each other, respond with the canonical name.
If they are different, respond with 'DIFFERENT'.

Examples:
- Input: ["Tesla", "特斯拉", "特斯拉汽车"]
  Output: Tesla

- Input: ["BYD", "比亚迪", "比亞迪"]
  Output: BYD

- Input: ["Toyota", "Honda"]
  Output: DIFFERENT"""

    prompt = f"Are these the same brand/product? {names_list}\n\nAnswer with the canonical name or 'DIFFERENT':"

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )

        result = response.strip()
        if "DIFFERENT" in result.upper():
            return None

        return _normalize_text(result)
    except Exception as e:
        logger.warning(f"LLM clustering verification failed: {e}")
        return None


_persistent_event_loop = None


def _get_or_create_event_loop():
    global _persistent_event_loop
    if _persistent_event_loop is None or _persistent_event_loop.is_closed():
        _persistent_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_persistent_event_loop)
    return _persistent_event_loop


def _run_async(coro):
    try:
        asyncio.get_running_loop()
        raise RuntimeError("Cannot run async code from within async context. Use await instead.")
    except RuntimeError:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(coro)


def _seed_primary(primary_brand: str, aliases: Dict[str, List[str]]) -> Set[str]:
    seeds = {primary_brand.strip()} if primary_brand else set()
    for lang_aliases in aliases.values():
        for alias in lang_aliases:
            alias_clean = alias.strip()
            if alias_clean:
                seeds.add(alias_clean)
    return seeds


def _extract_with_hanlp(text: str) -> Set[str]:
    hanlp = _load_optional_model("hanlp", "hanlp.load")
    if not hanlp:
        return set()
    try:
        model = hanlp("NER/MSRA")
        result = model(text)
        return {item[0] for item in result}
    except Exception:
        return set()


def _extract_with_ltp(text: str) -> Set[str]:
    ltp_class = _load_optional_model("ltp", "LTP")
    if not ltp_class:
        return set()
    try:
        ltp_instance = ltp_class()
        output = ltp_instance.ner([text])
        return {text[start:end] for _, start, end in output[0]}
    except Exception:
        return set()


def _regex_candidates(text: str) -> Set[str]:
    latin_models = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][A-Za-z]{0,9}\d[\w.\-]*)", text)
    model_variants = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z]{2,}[\-]?[A-Z0-9])", text)
    model_words = re.findall(r"(?:^|[\s\u4e00-\u9fff])(Model\s?[A-Z0-9]+)", text)
    id_models = re.findall(r"(?:^|[\s\u4e00-\u9fff])(ID\.\d+)", text)

    chinese_digit_suffix = re.findall(r"([\u4e00-\u9fff]{2,6}\d{1,3}\s+(?:Pro|Max|Plus|Ultra|Mini|DM-i|DM-p|EV))", text)
    chinese_suffix = re.findall(r"([\u4e00-\u9fff]{1,6}(?:PLUS|Plus|Pro|Max|Ultra|Mini|DM-i|DM-p|EV))", text)
    chinese_digits = re.findall(r"([\u4e00-\u9fff]{2,6}[A-Z]?\d{1,3})", text)
    chinese_latin = re.findall(r"([\u4e00-\u9fff]{2,6}[A-Z]{1,3}\d?)", text)
    chinese_brands = re.findall(r"([\u4e00-\u9fff]{2,8}(?!的|了|是|在|和|与|等|个|为|有|将|被))", text)

    latin_suffix = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][A-Za-z]+(?:PLUS|Plus|Pro|Max|Ultra|Mini|DM-i|DM-p))", text)
    product_lines = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][A-Za-zÀ-ÿ']+(?:\s+[A-Z][A-Za-zÀ-ÿ']+){1,2})", text)
    mixed_case = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][a-z]+[A-Z][a-z]+)", text)
    latin_with_space = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][A-Za-z]+\s+\d+(?:\s+[A-Z][a-z]+)?)", text)
    multiword_latin_number = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\s+\d+)", text)
    standalone_latin = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z][A-Za-z]{2,15})(?:\s|[\u4e00-\u9fff]|$)", text)

    digit_prefix_models = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z]\d+[A-Za-z]*)", text)
    letter_digit_combo = re.findall(r"(?:^|[\s\u4e00-\u9fff])([A-Z]{1,3}\d{1,4}[A-Za-z]*)", text)
    digit_first_models = re.findall(r"(?:^|[\s\u4e00-\u9fff])(\d+[A-Z][A-Za-z]+)", text)

    hits = (latin_models + model_variants + model_words + id_models +
            chinese_digit_suffix + chinese_suffix + chinese_digits + chinese_latin + chinese_brands +
            latin_suffix + product_lines + mixed_case + latin_with_space + multiword_latin_number +
            standalone_latin + digit_prefix_models + letter_digit_combo + digit_first_models)

    return {n.strip() for n in hits if n.strip() and len(n.strip()) >= 2}


def _quoted_candidates(text: str) -> Set[str]:
    quoted = re.findall(r'["\'"《》【】([]([^"\'"《》【】)\]]{2,15})["\'"》】)\]]', text)
    hits = set()
    for q in quoted:
        q_stripped = q.strip()
        if 2 <= len(q_stripped) <= 15:
            if not re.search(r"[、，。！？：；]", q_stripped):
                hits.add(q_stripped)
    return hits


def _list_table_candidates(text: str) -> Set[str]:
    hits = set()

    numbered_items = re.findall(r'^\s*\d+[\.、\)]\s+([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff0-9\s\-]{1,30}?)[\s\-:]', text, re.MULTILINE)
    hits.update(numbered_items)

    bulleted_items = re.findall(r'^\s*[-•·]\s+([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff0-9\s\-]{1,30}?)[\s\-:]', text, re.MULTILINE)
    hits.update(bulleted_items)

    inline_numbered = re.findall(r'\d+[\.、]\s*([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff0-9\s]{1,20}?)[\s\-:]', text)
    hits.update(inline_numbered)

    brand_mentions = re.findall(r'(?:品牌|推荐|产品|型号)[:：]\s*([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff0-9\s]{2,20})', text)
    hits.update(brand_mentions)

    cleaned = set()
    for item in hits:
        item_clean = item.strip()
        if 2 <= len(item_clean) <= 30:
            parts = re.split(r'\s+', item_clean)
            for part in parts:
                if len(part) >= 2:
                    cleaned.add(part)
            if len(parts) <= 3:
                cleaned.add(item_clean)

    return cleaned


def _candidate_source(name: str, seeds: Set[str], hanlp: Set[str], ltp: Set[str], regex_hits: Set[str], quoted_hits: Set[str], list_hits: Set[str]) -> str:
    if name in seeds:
        return "seed"
    if name in hanlp:
        return "hanlp"
    if name in ltp:
        return "ltp"
    if name in regex_hits:
        return "regex"
    if name in quoted_hits:
        return "quoted"
    if name in list_hits:
        return "list"
    return "unknown"


def _normalize_text(value: str) -> str:
    simplified = _convert_to_simplified(value)
    folded = unicodedata.normalize("NFKC", simplified).lower()
    stripped = re.sub(r"[\s\W·•\-_/]+", "", folded)
    return stripped


def _expand_subtokens(names: Set[str]) -> Set[str]:
    expanded: Set[str] = set()
    for name in names:
        expanded.update(re.findall(r"[A-Za-z]{1,10}\.?\d[\w.\-]*", name))
        expanded.update(re.findall(r"Model\s?[A-Za-z0-9]+", name))
    return {token for token in expanded if token}


def _convert_to_simplified(value: str) -> str:
    converter = _load_optional_model("opencc", "OpenCC")
    if not converter:
        return value
    try:
        return converter("t2s").convert(value)
    except Exception:
        return value


def _build_alias_lookup(primary_brand: str, aliases: Dict[str, List[str]], alias_table: Dict[str, str]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    canonical_primary = _normalize_text(primary_brand)
    if canonical_primary:
        lookup[canonical_primary] = canonical_primary
    for alias_list in aliases.values():
        for alias in alias_list:
            normalized = _normalize_text(alias)
            if normalized:
                lookup[normalized] = canonical_primary
    for alias, canonical in alias_table.items():
        normalized_alias = _normalize_text(alias)
        normalized_canonical = _normalize_text(canonical)
        if normalized_alias and normalized_canonical:
            lookup[normalized_alias] = normalized_canonical
    return lookup


def _has_variant_signals(text: str) -> bool:
    if not text or len(text) < 2:
        return False

    text_lower = text.lower()

    if re.search(r'\d', text):
        return True

    trim_markers = [
        'pro', 'max', 'plus', 'ultra', 'mini',
        'dm-i', 'dm-p', 'ev', 'phev', 'bev',
        'sport', 'luxury', 'premium', 'elite',
        'performance'
    ]
    if any(marker in text_lower for marker in trim_markers):
        return True

    if 'longrange' in text_lower or 'long range' in text_lower:
        return True
    if 'standardrange' in text_lower or 'standard range' in text_lower:
        return True

    capacity_size_patterns = [
        r'\d+\s*[gt]b?',
        r'\d+\s*英寸',
        r'\d+\s*寸',
        r'\d+\.?\d*\s*[lt]',
        r'\d+\s*mah',
        r'\d+\s*w',
    ]
    if any(re.search(pattern, text_lower) for pattern in capacity_size_patterns):
        return True

    return False


def _match_substring_alias(normalized: str, lookup: Dict[str, str]) -> str | None:
    for alias_norm, canonical in lookup.items():
        if not alias_norm or alias_norm not in normalized:
            continue

        if alias_norm == normalized:
            return canonical

        if _has_variant_signals(normalized) and not _has_variant_signals(alias_norm):
            logger.debug(f"Merge constraint: '{normalized}' has variant signals, '{alias_norm}' doesn't - skipping merge")
            continue

        if len(normalized) > len(alias_norm):
            suffix = normalized[len(alias_norm):]
            if _has_variant_signals(suffix):
                logger.debug(f"Merge constraint: suffix '{suffix}' of '{normalized}' has variant signals - skipping merge")
                continue

        logger.debug(f"Allowing merge: '{normalized}' -> '{canonical}' via alias '{alias_norm}'")
        return canonical

    return None


def _default_alias_table() -> Dict[str, str]:
    aliases = {
        "大众": "大众",
        "大眾": "大众",
        "Volkswagen": "大众",
        "VW": "大众",
        "上汽大众": "大众",
        "一汽大众": "大众",
        "丰田": "丰田",
        "Toyota": "丰田",
        "特斯拉": "特斯拉",
        "Tesla": "特斯拉",
        "比亚迪": "比亚迪",
        "BYD": "比亚迪",
    }
    products = {
        "宋PLUS": "宋PLUS",
        "宋Plus": "宋PLUS",
        "宋PlusDM-i": "宋PLUS",
        "ID.4": "ID.4",
        "ModelY": "ModelY",
        "Model Y": "ModelY",
    }
    aliases.update(products)
    return aliases


def _alias_hits(text: str, alias_table: Dict[str, str]) -> Set[str]:
    hits = set()
    for alias in alias_table.keys():
        if alias and alias in text:
            hits.add(alias)
    return hits


def extract_snippet_for_brand(
    text: str,
    brand_start: int,
    brand_end: int,
    all_brand_positions: List[Tuple[int, int]],
    max_length: int = 50,
) -> str:
    if not text:
        return ""

    snippet_start = brand_start
    snippet_end = min(len(text), brand_end + max_length)

    for other_start, other_end in all_brand_positions:
        if other_start > brand_end and other_start < snippet_end:
            snippet_end = other_start
            break

    return text[snippet_start:snippet_end].strip()


def extract_snippet_with_list_awareness(
    text: str,
    brand_start: int,
    brand_end: int,
    all_brand_positions: List[Tuple[int, int]],
    brand_names_lower: List[str],
    max_length: int = 50,
) -> str:
    if is_list_format(text):
        list_items = split_into_list_items(text)
        list_items_lower = [item.lower() for item in list_items]
        for i, item_lower in enumerate(list_items_lower):
            for name in brand_names_lower:
                if name in item_lower:
                    return list_items[i]

    return extract_snippet_for_brand(
        text, brand_start, brand_end, all_brand_positions, max_length
    )


def _load_optional_model(module_name: str, attr: str):
    module = importlib.util.find_spec(module_name)
    if not module:
        return None
    module_obj = importlib.import_module(module_name)
    return getattr(module_obj, attr, None)


def _split_clusters_by_type(
    clusters: Dict[str, List[str]],
    candidates: List[EntityCandidate]
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    candidate_types = {c.name.lower(): c.entity_type for c in candidates}

    brands: Dict[str, List[str]] = {}
    products: Dict[str, List[str]] = {}

    for name, surface_forms in clusters.items():
        entity_type = candidate_types.get(name.lower(), "unknown")

        if entity_type == "product" or is_likely_product(name):
            products[name] = surface_forms
        elif entity_type == "brand" or is_likely_brand(name):
            brands[name] = surface_forms
        else:
            brands[name] = surface_forms

    return brands, products


def canonicalize_entities(candidates: List[EntityCandidate], primary_brand: str, aliases: Dict[str, List[str]], alias_table: Dict[str, str] | None = None, text: str = "") -> Dict[str, List[str]]:
    if ENABLE_QWEN_FILTERING and text:
        filtered_candidates = _run_async(_filter_candidates_with_qwen(candidates, text))
    else:
        filtered_candidates = _filter_candidates_simple(candidates)

    if ENABLE_EMBEDDING_CLUSTERING:
        embedding_clusters = _run_async(_cluster_with_embeddings(filtered_candidates))
    else:
        embedding_clusters = {c.name: [c] for c in filtered_candidates}

    if ENABLE_LLM_CLUSTERING:
        final_clusters = _run_async(_llm_assisted_clustering(embedding_clusters, primary_brand, aliases))
    else:
        final_clusters = _simple_clustering(embedding_clusters, primary_brand, aliases)

    return final_clusters
