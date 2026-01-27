"""
List detection and processing functions.

This module contains functions for detecting list-formatted text, splitting it into
list items, and extracting entities from list items.
"""

import re
from typing import Dict, List, Optional, Tuple

from constants import (
    KNOWN_PRODUCTS,
    GENERIC_TERMS,
    PRODUCT_HINTS,
    COMPILED_LIST_PATTERNS,
    LIST_ITEM_MARKER_REGEX,
    LIST_ITEM_SPLIT_REGEX,
    COMPARISON_MARKERS,
    CLAUSE_SEPARATORS,
    VALID_EXTRA_TERMS,
)

from services.brand_recognition.classification import (
    is_likely_brand,
    is_likely_product,
)
from services.brand_recognition.models import EntityCandidate
from services.brand_recognition.markdown_table import (
    extract_markdown_table_row_items,
    find_first_markdown_table_index,
    markdown_table_has_min_data_rows,
)


def is_list_format(text: str) -> bool:
    """Check if text is in list format."""
    if markdown_table_has_min_data_rows(text, min_rows=2):
        return True

    for pattern in COMPILED_LIST_PATTERNS:
        matches = pattern.findall(text)
        if len(matches) >= 2:
            return True
    return False


def split_into_list_items(text: str) -> List[str]:
    """Split list-formatted text into individual items."""
    if not is_list_format(text):
        return []

    if markdown_table_has_min_data_rows(text, min_rows=2):
        return extract_markdown_table_row_items(text)

    parts = re.split(LIST_ITEM_SPLIT_REGEX, text, flags=re.MULTILINE)
    items = [p.strip() for p in parts if p and p.strip()]

    first_item_idx = _find_first_list_item_index(text)
    if first_item_idx > 0 and items:
        items = items[1:] if _is_intro_paragraph(items[0], text) else items

    return items


def _find_first_list_item_index(text: str) -> int:
    """Find the index of the first list item marker in text."""
    marker_match = re.search(LIST_ITEM_MARKER_REGEX, text, flags=re.MULTILINE)
    marker_idx = marker_match.start() if marker_match else None
    table_idx = find_first_markdown_table_index(text)

    if marker_idx is None and table_idx is None:
        return 0
    if marker_idx is None:
        return table_idx or 0
    if table_idx is None:
        return marker_idx
    return min(marker_idx, table_idx)


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
    import logging
    logger = logging.getLogger(__name__)

    if not is_list_format(text):
        return candidates

    list_items = split_into_list_items(text)
    if not list_items:
        return candidates

    allowed_brands: set = set()
    allowed_products: set = set()

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


def _get_intro_text(text: str) -> Optional[str]:
    """Get introductory text before the first list item."""
    first_marker_idx = _find_first_list_item_index(text)
    if first_marker_idx > 0:
        return text[:first_marker_idx].strip()
    return None


def _add_all_entities_from_text(
    text: str, candidates: List[EntityCandidate], brands: set, products: set
) -> None:
    """Add all entities found in text to the allowed sets."""
    from services.brand_recognition.classification import _has_product_model_patterns, _has_product_suffix

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


def _has_product_patterns(name: str) -> bool:
    """Check if name has product-like patterns."""
    from services.brand_recognition.classification import _has_product_model_patterns, _has_product_suffix

    if _has_product_model_patterns(name):
        return True
    if _has_product_suffix(name):
        return True
    if name.lower() in PRODUCT_HINTS:
        return True
    return False


def _has_brand_patterns(name: str) -> bool:
    """Check if name has brand-like patterns."""
    from services.brand_recognition.classification import _has_product_model_patterns, _has_product_suffix

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


def _extract_first_brand_and_product_from_item(
    item: str, candidates: List[EntityCandidate]
) -> Dict[str, Optional[str]]:
    """Extract the first brand and product from a list item."""
    result: Dict[str, Optional[str]] = {"brand": None, "product": None}

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
    """Check if a name looks like a product."""
    if re.search(r"\d", name):
        return True
    if re.search(r"(PLUS|Plus|Pro|Max|Ultra|Mini|EV|DM)", name):
        return True
    return False


def _get_primary_region(item: str) -> str:
    """Get the primary region of a list item (before cutoff markers)."""
    cutoff = _find_first_cutoff(item)
    return item[:cutoff] if cutoff else item


def _find_first_cutoff(item: str) -> Optional[int]:
    """Find the first cutoff position in a list item."""
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


def _match_candidates_to_allowed(
    candidates: List[EntityCandidate],
    allowed_brands: set,
    allowed_products: set
) -> List[EntityCandidate]:
    """Match candidates to allowed sets."""
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


def _candidate_matches_allowed(candidate_lower: str, allowed_set: set) -> bool:
    """Check if a candidate matches any allowed entity."""
    for allowed in allowed_set:
        if candidate_lower in allowed:
            return True
        if allowed == candidate_lower:
            return True
        if _is_clean_substring_match(allowed, candidate_lower):
            return True
    return False


def _is_clean_substring_match(allowed: str, candidate: str) -> bool:
    """Check if candidate is a clean substring match of allowed."""
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
    """Check if extra text is valid for substring matching."""
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
