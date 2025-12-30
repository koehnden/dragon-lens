"""
Basic entity classification functions.

This module contains functions for classifying text as brands, products, or other
entity types based on pattern matching and heuristics.
"""

import re
from typing import Dict, List

from constants import (
    PRODUCT_HINTS,
    GENERIC_TERMS,
    DESCRIPTOR_PATTERNS,
)


def _is_descriptor_pattern(name: str) -> bool:
    """Check if a name matches descriptor patterns."""
    for pattern in DESCRIPTOR_PATTERNS:
        if re.match(pattern, name):
            if name.lower() not in PRODUCT_HINTS:
                return True
    return False


def is_likely_brand(name: str) -> bool:
    """Determine if a name is likely a brand."""
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
    """Determine if a name is likely a product."""
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
    """Check if a name has product model patterns."""
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
    """Check if a name has product suffixes."""
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
    """Classify an entity as brand, product, or other."""
    name_lower = name.lower().strip()
    if name_lower in GENERIC_TERMS:
        return "other"
    if is_likely_brand(name):
        return "brand"
    if is_likely_product(name):
        return "product"
    return "other"
