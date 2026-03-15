"""Entity validation helpers used by legacy local-only workflows."""

import logging
import re
from typing import List

from services.brand_recognition.models import EntityCandidate
from services.brand_recognition.classification import (
    classify_entity_type,
)
from constants import GENERIC_TERMS, KNOWN_PRODUCTS

logger = logging.getLogger(__name__)


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
