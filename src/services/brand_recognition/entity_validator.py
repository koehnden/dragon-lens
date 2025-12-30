"""
Entity validation and filtering.

This module contains functions for validating and filtering entity candidates
using Qwen-based validation and simple rule-based filtering.
"""

import logging
import re
from typing import Dict, List, Set, Optional

from services.brand_recognition.models import EntityCandidate
from services.brand_recognition.classification import (
    is_likely_brand,
    is_likely_product,
    classify_entity_type,
    _has_product_model_patterns,
    _has_product_suffix,
)
from services.brand_recognition.text_utils import _extract_evidence, _parse_json_response
from services.brand_recognition.prompts import load_prompt
from constants import GENERIC_TERMS, KNOWN_PRODUCTS

logger = logging.getLogger(__name__)


async def _verify_entity_with_qwen(
    ollama,
    entity: str,
    text: str,
) -> Optional[Dict]:
    """Verify a single entity using Qwen."""
    evidence = _extract_evidence(entity, text)
    if evidence is None:
        return None

    system_prompt = load_prompt("entity_classification_system_prompt")
    prompt = load_prompt("entity_classification_user_prompt", text=text, entity=entity)

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )
        result = _parse_json_response(response)
        if result and "type" in result and "confidence" in result and "why" in result:
            return result
        return None
    except Exception as e:
        logger.warning(f"Entity verification failed: {e}")
        return None


async def _filter_candidates_with_qwen(
    candidates: List[EntityCandidate],
    text: str,
    vertical: str = "",
    vertical_description: str = "",
) -> List[EntityCandidate]:
    """Filter candidates using Qwen-based validation."""
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


def _filter_candidates_simple(candidates: List[EntityCandidate]) -> List[EntityCandidate]:
    """Filter candidates using simple rule-based validation."""
    filtered = []
    for candidate in candidates:
        if candidate.source == "seed":
            filtered.append(candidate)
        elif _is_valid_brand_candidate(candidate.name):
            entity_type = classify_entity_type(candidate.name)
            if entity_type in ["brand", "product"]:
                candidate.entity_type = entity_type
                filtered.append(candidate)
    logger.info(f"Simple filtering: {len(candidates)} -> {len(filtered)} candidates")
    return filtered


def _might_be_brand_needs_verification(name: str) -> bool:
    """Check if a candidate might be a brand and needs Qwen verification."""
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
    """Verify entities with Qwen in batches."""
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
    """Verify a single batch of entities with Qwen."""
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
    """Verify brand candidates with Qwen using templates."""
    import json

    candidates_json = json.dumps(candidates, ensure_ascii=False)
    system_prompt = load_prompt("brand_verification_system_prompt", vertical=vertical)
    prompt = load_prompt(
        "brand_verification_user_prompt",
        vertical=vertical,
        vertical_description=vertical_description,
        text=text,
        candidates_json=candidates_json,
    )

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
    """Verify product candidates with Qwen using templates."""
    import json

    candidates_json = json.dumps(candidates, ensure_ascii=False)
    system_prompt = load_prompt("product_verification_system_prompt", vertical=vertical)
    prompt = load_prompt(
        "product_verification_user_prompt",
        vertical=vertical,
        vertical_description=vertical_description,
        text=text,
        candidates_json=candidates_json,
    )

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
    """Parse brand verification response."""
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
    """Parse product verification response."""
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


def _parse_batch_json_response(response: str) -> List[Dict] | None:
    """Parse a batch JSON response."""
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


def _contains_feature_keywords(name: str) -> bool:
    """Check if name contains feature keywords."""
    keywords = [
        "动力", "天窗", "后备箱", "品牌口碑", "舒适", "空间",
        "配置", "自动驾驶", "主动安全", "车机系统", "发动机",
        "变速箱", "维修"
    ]
    return any(keyword in name for keyword in keywords)


def _is_valid_brand_candidate(name: str) -> bool:
    """Check if a candidate is a valid brand candidate."""
    if len(name) < 2 or len(name) > 30:
        return False

    if _is_feature_descriptor(name):
        return False

    if _contains_feature_keywords(name):
        return False

    if _is_generic_stop_word(name):
        return False

    if _is_compound_descriptor(name):
        return False

    if _contains_non_brand_keywords(name):
        return False

    if re.search(r"[、，。！？：；]", name):
        return False

    return _matches_brand_product_pattern(name)


def _is_feature_descriptor(name: str) -> bool:
    """Check if name is a feature descriptor."""
    patterns = [
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
    return any(re.search(pattern, name) for pattern in patterns)


def _is_generic_stop_word(name: str) -> bool:
    """Check if name is a generic stop word."""
    stop_words = {
        "最好", "推荐", "性能", "价格", "质量", "选择",
        "品牌", "产品", "类型", "种类", "系列", "排行",
        "国产", "进口", "豪华", "高端", "入门", "国产品牌",
        "安全性", "可靠性", "舒适性", "性价比", "适口性",
        "猫粮", "狗粮", "补剂", "胶原蛋白",
        "扫地机", "吸尘器", "处方粮",
        "温和性好", "性价比高", "肤感舒适", "适合敏感肌",
    }
    return name.lower() in {w.lower() for w in stop_words}


def _is_compound_descriptor(name: str) -> bool:
    """Check if name is a compound descriptor."""
    endings = ["高", "好", "强", "差", "低", "等", "改善", "提升", "规划", "方面", "指标"]
    if len(name) > 2 and any(name.endswith(ending) for ending in endings):
        brand_patterns = [r"[A-Za-z]+", r"\d+", r"(PLUS|Plus|Pro|Max|Ultra|Mini|DM-i)"]
        has_brand_pattern = any(re.search(pattern, name) for pattern in brand_patterns)
        return not has_brand_pattern
    return False


def _contains_non_brand_keywords(name: str) -> bool:
    """Check if name contains non-brand keywords."""
    keywords = ["推荐", "适合", "保湿", "消化", "粪便", "噪音", "品质", "安全性", "操作", "智能"]
    return len(name) > 4 and any(keyword in name for keyword in keywords)


def _matches_brand_product_pattern(name: str) -> bool:
    """Check if name matches brand/product patterns."""
    patterns = [
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
    return any(re.search(pattern, name) for pattern in patterns)
