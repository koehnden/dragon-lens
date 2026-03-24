"""Legacy brand/product normalization helpers kept for active workflows."""

import logging
import re
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from services.brand_recognition.models import (
    ExtractionResult,
    ExtractionDebugInfo,
)
from services.brand_recognition.classification import (
    is_likely_brand,
    is_likely_product,
    _has_product_model_patterns,
    _has_product_suffix,
)
from services.brand_recognition.prompts import load_prompt
from constants import GENERIC_TERMS, PRODUCT_HINTS

logger = logging.getLogger(__name__)

def _calculate_brand_confidence(entity: str, entity_lower: str, vertical: str) -> float:
    """Calculate confidence score for a brand entity."""
    if entity_lower in GENERIC_TERMS:
        return 0.2
    if _has_product_model_patterns(entity):
        return 0.3
    if _has_product_suffix(entity):
        return 0.35
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
    """Calculate confidence score for a product entity."""
    if entity_lower in GENERIC_TERMS:
        return 0.2
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


def _has_product_patterns(name: str) -> bool:
    """Check if name has product-like patterns."""
    if _has_product_model_patterns(name):
        return True
    if _has_product_suffix(name):
        return True
    if name.lower() in PRODUCT_HINTS:
        return True
    return False


def _has_brand_patterns(name: str) -> bool:
    """Check if name has brand-like patterns."""
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
