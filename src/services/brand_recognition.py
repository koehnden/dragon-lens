import asyncio
import importlib
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)

ENABLE_QWEN_FILTERING = os.getenv("ENABLE_QWEN_FILTERING", "true").lower() == "true"

KNOWN_BRANDS = {
    "honda", "本田", "toyota", "丰田", "byd", "比亚迪", "volkswagen", "vw", "大众",
    "bmw", "宝马", "mercedes", "mercedes-benz", "奔驰", "audi", "奥迪",
    "tesla", "特斯拉", "ford", "福特", "chevrolet", "雪佛兰", "nissan", "日产",
    "hyundai", "现代", "kia", "起亚", "porsche", "保时捷", "lexus", "雷克萨斯",
    "volvo", "沃尔沃", "mazda", "马自达", "subaru", "斯巴鲁", "jeep", "吉普",
    "land rover", "路虎", "jaguar", "捷豹", "ferrari", "法拉利", "lamborghini", "兰博基尼",
    "理想", "li auto", "nio", "蔚来", "xpeng", "小鹏", "geely", "吉利",
    "changan", "长安", "great wall", "长城", "haval", "哈弗", "wey", "魏牌",
    "zeekr", "极氪", "lynk & co", "领克", "buick", "别克", "cadillac", "凯迪拉克",
    "apple", "苹果", "samsung", "三星", "huawei", "华为", "xiaomi", "小米",
    "oppo", "vivo", "oneplus", "一加", "sony", "索尼", "google", "谷歌",
    "loreal", "欧莱雅", "nike", "耐克", "adidas", "阿迪达斯", "puma", "彪马",
    "under armour", "dyson", "戴森", "shark", "roomba", "irobot",
}

KNOWN_PRODUCTS = {
    "crv", "cr-v", "rav4", "rav-4", "model y", "model 3", "model s", "model x",
    "宋plus", "宋pro", "宋", "汉ev", "汉dm", "汉", "唐dm", "唐", "秦plus", "秦", "元plus", "元", "海豚", "海鸥",
    "id.4", "id.6", "tiguan", "途观", "途观l", "passat", "帕萨特", "golf", "高尔夫", "polo",
    "camry", "凯美瑞", "corolla", "卡罗拉", "highlander", "汉兰达", "prado", "普拉多", "4runner",
    "accord", "雅阁", "civic", "思域", "odyssey", "奥德赛", "pilot", "passport", "hr-v",
    "x3", "x5", "x7", "3 series", "5 series", "7 series", "x1",
    "a4", "a6", "a8", "q3", "q5", "q7", "q8", "e-tron",
    "cayenne", "macan", "panamera", "911", "taycan",
    "mustang", "野马", "f-150", "explorer", "escape", "bronco",
    "l9", "l8", "l7", "l6", "理想one", "et7", "et5", "es6", "es8", "ec6",
    "p7", "g9", "g6", "p5", "tucson", "途胜", "telluride", "palisade",
    "iphone", "iphone 14", "iphone 15", "iphone 15 pro", "galaxy", "galaxy s24",
    "mate", "mate 50", "p50", "p60", "pixel", "pixel 8",
    "mi 14", "redmi", "find x", "reno",
    "air max", "ultraboost", "v15", "navigator", "crosswave", "i7", "ascent",
    "rx", "glc", "gle", "gls", "sealion",
}

GENERIC_TERMS = {
    "suv", "sedan", "coupe", "hatchback", "mpv", "pickup", "truck", "van",
    "ev", "phev", "hev", "bev", "hybrid", "electric", "gasoline", "diesel",
    "one", "pro", "max", "plus", "ultra", "lite", "mini", "air",
    "carplay", "android auto", "gps", "abs", "esp", "acc", "lka", "bsd",
    "4wd", "awd", "fwd", "rwd", "cvt", "dct", "at", "mt",
    "led", "lcd", "oled", "hud", "360", "adas",
    "车", "汽车", "轿车", "越野车", "跑车", "电动车", "新能源",
    "品牌", "产品", "型号", "系列", "款", "版",
}
ENABLE_EMBEDDING_CLUSTERING = os.getenv("ENABLE_EMBEDDING_CLUSTERING", "false").lower() == "true"
ENABLE_LLM_CLUSTERING = os.getenv("ENABLE_LLM_CLUSTERING", "false").lower() == "true"
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "qllama/bge-small-zh-v1.5:latest")


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


def is_likely_brand(name: str) -> bool:
    name_lower = name.lower().strip()
    if name_lower in KNOWN_BRANDS:
        return True
    if name_lower in GENERIC_TERMS:
        return False
    if name_lower in KNOWN_PRODUCTS:
        return False
    if len(name) <= 2 and name.isalpha() and name.isupper():
        return False
    if re.match(r"^[A-Z][a-z]+$", name) and len(name) >= 4:
        return True
    if re.search(r"[\u4e00-\u9fff]{2,4}$", name) and not re.search(r"\d", name):
        if not any(suffix in name for suffix in ["PLUS", "Plus", "Pro", "EV", "DM"]):
            return True
    return False


def is_likely_product(name: str) -> bool:
    name_lower = name.lower().strip()
    if name_lower in KNOWN_PRODUCTS:
        return True
    if name_lower in GENERIC_TERMS:
        return False
    if name_lower in KNOWN_BRANDS:
        return False
    if re.search(r"[A-Za-z]+\d+", name) or re.search(r"\d+[A-Za-z]+", name):
        return True
    if re.search(r"(PLUS|Plus|Pro|Max|Ultra|Mini|EV|DM|DM-i|DM-p)", name):
        return True
    if re.match(r"^[A-Z]\d+$", name):
        return True
    if re.match(r"^Model\s+[A-Z0-9]", name):
        return True
    if re.match(r"^ID\.\d+", name):
        return True
    return False


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
    brand_positions: List[Tuple[int, str]] = []
    for brand in KNOWN_BRANDS:
        pos = item_lower.find(brand.lower())
        if pos != -1:
            display = brand.upper() if len(brand) <= 3 else (brand.title() if brand.isascii() else brand)
            brand_positions.append((pos, display))
    if brand_positions:
        brand_positions.sort(key=lambda x: x[0])
        result["primary_brand"] = brand_positions[0][1]
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


LIST_PATTERNS = [
    r'^\s*\d+[.\)]\s+',
    r'^\s*\d+、',
    r'^\s*[-*]\s+',
    r'^\s*[・○→]\s*',
    r'^#{1,4}\s*\**\d+[.\)]\s*',
]

COMPILED_LIST_PATTERNS = [re.compile(p, re.MULTILINE) for p in LIST_PATTERNS]


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
) -> Dict[str, List[str]]:
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

    return final_clusters


COMPARISON_MARKERS = [
    "similar to", "comparable to", "like ", "better than", "worse than",
    "competing with", "compared to", "versus", " vs ", " vs.",
    "outperforming", "ahead of", "behind ",
    "类似于", "相比于", "胜过", "不如", "优于", "竞争对手",
    "，比", "，和", "，与", "，类似", "，相比",
]

CLAUSE_SEPARATORS = [". ", ", ", "; ", "。", "，", "；", " - "]


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
    if len(candidate) > len(allowed) * 2:
        return False
    extra = candidate.replace(allowed, "", 1)
    if re.search(r"[\u4e00-\u9fff]{2,}", extra):
        return False
    if re.search(r"[a-z]{3,}", extra):
        return False
    return True


def _add_all_entities_from_text(
    text: str, candidates: List[EntityCandidate], brands: Set[str], products: Set[str]
) -> None:
    text_lower = text.lower()
    for candidate in candidates:
        name_lower = candidate.name.lower()
        if name_lower in text_lower:
            if candidate.entity_type == "brand" or name_lower in KNOWN_BRANDS:
                brands.add(name_lower)
            elif candidate.entity_type == "product" or name_lower in KNOWN_PRODUCTS:
                products.add(name_lower)
            else:
                brands.add(name_lower)


def _extract_first_brand_and_product_from_item(
    item: str, candidates: List[EntityCandidate]
) -> Dict[str, str | None]:
    result: Dict[str, str | None] = {"brand": None, "product": None}
    item_lower = item.lower()

    known_brand_positions: List[Tuple[int, int, str]] = []
    known_product_positions: List[Tuple[int, int, str]] = []

    for brand in KNOWN_BRANDS:
        pos = item_lower.find(brand.lower())
        if pos != -1:
            known_brand_positions.append((pos, -len(brand), brand))

    for product in KNOWN_PRODUCTS:
        pos = item_lower.find(product.lower())
        if pos != -1:
            known_product_positions.append((pos, -len(product), product))

    if known_brand_positions:
        known_brand_positions.sort(key=lambda x: (x[0], x[1]))
        result["brand"] = known_brand_positions[0][2]

    if known_product_positions:
        known_product_positions.sort(key=lambda x: (x[0], x[1]))
        result["product"] = known_product_positions[0][2]

    if result["brand"] is None or result["product"] is None:
        candidate_brand_positions: List[Tuple[int, int, str]] = []
        candidate_product_positions: List[Tuple[int, int, str]] = []

        for candidate in candidates:
            name = candidate.name
            name_lower = name.lower()
            pos = item_lower.find(name_lower)
            if pos == -1:
                continue

            if name_lower in KNOWN_BRANDS or name_lower in KNOWN_PRODUCTS:
                continue

            is_brand = candidate.entity_type == "brand"
            is_product = candidate.entity_type == "product"

            if is_brand and result["brand"] is None:
                candidate_brand_positions.append((pos, -len(name), name))
            elif is_product and result["product"] is None:
                candidate_product_positions.append((pos, -len(name), name))
            elif not is_brand and not is_product:
                if _looks_like_product(name) and result["product"] is None:
                    candidate_product_positions.append((pos, -len(name), name))
                elif result["brand"] is None:
                    candidate_brand_positions.append((pos, -len(name), name))

        if result["brand"] is None and candidate_brand_positions:
            candidate_brand_positions.sort(key=lambda x: (x[0], x[1]))
            result["brand"] = candidate_brand_positions[0][2]

        if result["product"] is None and candidate_product_positions:
            candidate_product_positions.sort(key=lambda x: (x[0], x[1]))
            result["product"] = candidate_product_positions[0][2]

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
        elif name_lower in KNOWN_BRANDS:
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
            temperature=0.1,
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
            temperature=0.1,
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


async def _verify_batch_with_qwen_legacy(
    ollama,
    batch: List[EntityCandidate],
    text: str,
    vertical: str = "",
    vertical_description: str = ""
) -> Dict[str, str]:
    import json

    candidate_names = [c.name for c in batch]
    candidates_json = json.dumps(candidate_names, ensure_ascii=False)

    vertical_context = ""
    if vertical:
        vertical_context = f"\nVertical/Industry: {vertical}"
        if vertical_description:
            vertical_context += f" - {vertical_description}"

    system_prompt = f"""You are an expert at distinguishing brands from products in the {vertical or 'general'} industry.

CRITICAL RULES:
1. A BRAND is a company/manufacturer name that makes multiple products
2. A PRODUCT is a specific model/item made by a brand
3. Classify as "other" for generic terms, features, or non-entity words

STRICT FILTERING - Classify as "other":
- Generic category terms: SUV, sedan, EV, hybrid, smartphone, laptop
- Feature words: CarPlay, GPS, LED, AWD, wireless, automatic
- Common words: One, Pro, Max, Plus (unless part of product name)
- Quality descriptors: best, good, popular, premium

BRAND examples: Toyota, Honda, BYD, 比亚迪, Tesla, BMW, Apple, Samsung
PRODUCT examples: RAV4, CRV, 宋PLUS, Model Y, X5, iPhone 15, Galaxy S24

Output format (JSON array only):
[{{"name": "entity1", "type": "brand"}}, {{"name": "entity2", "type": "product"}}, {{"name": "entity3", "type": "other"}}]"""

    text_snippet = text[:1500] if len(text) > 1500 else text

    prompt = f"""Industry context:{vertical_context}

Source text:
{text_snippet}

Candidates to classify:
{candidates_json}

For each candidate, determine if it's a BRAND (company), PRODUCT (specific model), or OTHER (generic term).
Output JSON array only:"""

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
        )

        parsed = _parse_batch_json_response(response)
        if not parsed:
            logger.warning(f"Failed to parse batch response, falling back to 'other'")
            return {name: "other" for name in candidate_names}

        result_map = {}
        for item in parsed:
            if isinstance(item, dict) and "name" in item and "type" in item:
                result_map[item["name"]] = item["type"]

        for name in candidate_names:
            if name not in result_map:
                result_map[name] = "other"

        return result_map

    except Exception as e:
        logger.warning(f"Batch verification failed: {e}")
        return {name: "other" for name in candidate_names}


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
            temperature=0.1,
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
            temperature=0.1,
        )

        result = response.strip()
        if "DIFFERENT" in result.upper():
            return None

        return _normalize_text(result)
    except Exception as e:
        logger.warning(f"LLM clustering verification failed: {e}")
        return None


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        raise RuntimeError("Cannot run async code from within async context. Use await instead.")


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

    hits = (latin_models + model_variants + model_words + id_models +
            chinese_digit_suffix + chinese_suffix + chinese_digits + chinese_latin + chinese_brands +
            latin_suffix + product_lines + mixed_case + latin_with_space + multiword_latin_number +
            standalone_latin + digit_prefix_models + letter_digit_combo)

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


def _load_optional_model(module_name: str, attr: str):
    module = importlib.util.find_spec(module_name)
    if not module:
        return None
    module_obj = importlib.import_module(module_name)
    return getattr(module_obj, attr, None)


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
