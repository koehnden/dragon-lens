"""
List detection and processing functions.

This module contains functions for detecting list-formatted text, splitting it into
list items, and extracting entities from list items.
"""

import re
from typing import Dict, List, Optional, Tuple

from src.constants import (
    KNOWN_PRODUCTS,
    GENERIC_TERMS,
    COMPILED_LIST_PATTERNS,
    COMPARISON_MARKERS,
    CLAUSE_SEPARATORS,
)

from services.brand_recognition.classification import (
    is_likely_brand,
    is_likely_product,
)
from services.brand_recognition.models import EntityCandidate


def is_list_format(text: str) -> bool:
    """Check if text is in list format."""
    for pattern in COMPILED_LIST_PATTERNS:
        matches = pattern.findall(text)
        if len(matches) >= 2:
            return True
    return False


def split_into_list_items(text: str) -> List[str]:
    """Split list-formatted text into individual items."""
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
    """Find the index of the first list item marker in text."""
    combined_pattern = r'(?:^\s*\d+[.\)]|^\s*\d+、|^\s*[-*]|^\s*[・○→]|^#{1,4}\s*\**\d+[.\)])'
    match = re.search(combined_pattern, text, flags=re.MULTILINE)
    return match.start() if match else 0


def _is_intro_paragraph(candidate: str, full_text: str) -> bool:
    """Check if a candidate is an introductory paragraph before a list."""
    first_marker_idx = _find_first_list_item_index(full_text)
    if first_marker_idx == 0:
        return False
    intro_part = full_text[:first_marker_idx].strip()
    return candidate.strip() == intro_part


def extract_primary_entities_from_list_item(item: str) -> Dict[str, Optional[str]]:
    """Extract primary brand and product from a list item."""
    from services.brand_recognition.text_utils import normalize_text_for_ner
    
    result: Dict[str, Optional[str]] = {"primary_brand": None, "primary_product": None}
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


def _filter_by_list_position(candidates: List[EntityCandidate], text: str) -> List[EntityCandidate]:
    """Filter candidates based on their position in list items."""
    # Simplified version - in real implementation this would analyze list positions
    return candidates
