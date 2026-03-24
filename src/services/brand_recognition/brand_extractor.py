"""
Brand extraction using Qwen.

This module contains functions for extracting entities using Qwen-based
extraction with structured prompts. Supports augmentation with validated
entities and previous mistakes from earlier runs.
"""

import logging
import re
from typing import Dict, List, Optional, Set, Tuple

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


async def _extract_entities_with_qwen(
    text: str,
    vertical: str = "",
    vertical_description: str = "",
    db: Optional[Session] = None,
    vertical_id: Optional[int] = None,
    min_expected_entities: Optional[int] = None,
    retry_feedback: Optional[str] = None,
) -> ExtractionResult:
    """Extract entities using Qwen - simplified for maximum recall.

    Only applies light filtering (GENERIC_TERMS). Normalization, validation,
    and list position filtering are deferred to the consolidation step.

    If db and vertical_id are provided, augments the prompt with validated
    entities (positive examples) and previous mistakes (negative examples).
    Validated entities bypass the light filter.
    """
    from services.ollama import OllamaService

    ollama = OllamaService()

    augmentation_context = {}
    validated_brand_names: Set[str] = set()
    validated_product_names: Set[str] = set()

    if db is not None and vertical_id is not None:
        from services.brand_recognition.extraction_augmentation import (
            get_augmentation_context,
            get_validated_entity_names,
        )
        augmentation_context = get_augmentation_context(db, vertical_id)
        validated_brand_names, validated_product_names = get_validated_entity_names(db, vertical_id)
        logger.debug(
            f"[Extraction] Augmentation loaded: {len(augmentation_context.get('validated_brands', []))} "
            f"validated brands, {len(augmentation_context.get('rejected_brands', []))} rejected brands"
        )

    system_prompt = _build_extraction_system_prompt(
        vertical, vertical_description, augmentation_context,
        min_expected_entities=min_expected_entities,
        retry_feedback=retry_feedback,
    )
    prompt = _build_extraction_prompt(text)

    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )

        result = _parse_extraction_response(response)
        raw_brands = result.get("brands", [])
        raw_products = result.get("products", [])
        raw_relationships = result.get("relationships", {})

        logger.info(f"[Extraction] Raw from Qwen: brands={raw_brands}, products={raw_products}")
        if raw_relationships:
            logger.info(f"[Extraction] Relationships from Qwen: {raw_relationships}")

        filtered_brands, rejected_brands = _apply_light_filter_with_bypass(
            raw_brands, validated_brand_names
        )
        filtered_products, rejected_products = _apply_light_filter_with_bypass(
            raw_products, validated_product_names
        )

        rejected_at_light_filter = rejected_brands + rejected_products
        if rejected_at_light_filter:
            logger.info(f"[Extraction] Rejected at light filter: {rejected_at_light_filter}")

        brand_clusters = {b: [b] for b in filtered_brands}
        product_clusters = {p: [p] for p in filtered_products}

        debug_info = ExtractionDebugInfo(
            raw_brands=raw_brands,
            raw_products=raw_products,
            rejected_at_light_filter=rejected_at_light_filter,
            final_brands=filtered_brands,
            final_products=filtered_products,
        )

        filtered_relationships = _filter_relationships(
            raw_relationships, set(filtered_products), set(filtered_brands)
        )

        logger.info(
            f"[Extraction] Final: {len(raw_brands)} raw brands -> {len(filtered_brands)} after light filter, "
            f"{len(raw_products)} raw products -> {len(filtered_products)} after light filter"
        )
        if filtered_relationships:
            logger.info(f"[Extraction] Filtered relationships: {filtered_relationships}")

        return ExtractionResult(
            brands=brand_clusters,
            products=product_clusters,
            product_brand_relationships=filtered_relationships,
            debug_info=debug_info,
        )

    except Exception as e:
        logger.error(f"Qwen extraction failed: {e}")
        return ExtractionResult(brands={}, products={}, product_brand_relationships={})

def _apply_light_filter_with_bypass(
    entities: List[str],
    validated_names: Set[str],
) -> Tuple[List[str], List[str]]:
    """Apply light filtering with bypass for validated entities."""
    filtered = []
    rejected = []
    seen = set()

    for entity in entities:
        if entity in seen:
            continue
        seen.add(entity)

        if entity in validated_names or entity.lower() in validated_names:
            filtered.append(entity)
            logger.debug(f"[Extraction] Bypassed light filter for validated entity: {entity}")
            continue

        entity_lower = entity.lower()
        if entity_lower in GENERIC_TERMS:
            rejected.append(entity)
        elif len(entity) < 2:
            rejected.append(entity)
        else:
            filtered.append(entity)

    return filtered, rejected


def _filter_relationships(
    relationships: Dict[str, str],
    valid_products: Set[str],
    valid_brands: Set[str],
) -> Dict[str, str]:
    """Filter relationships to only include valid products and brands."""
    filtered = {}
    valid_products_lower = {p.lower() for p in valid_products}
    valid_brands_lower = {b.lower() for b in valid_brands}

    for product, brand in relationships.items():
        product_valid = product in valid_products or product.lower() in valid_products_lower
        brand_valid = brand in valid_brands or brand.lower() in valid_brands_lower
        if product_valid and brand_valid:
            filtered[product] = brand

    return filtered

def _is_automotive_vertical(vertical_lower: str) -> bool:
    """Check if the vertical is automotive-related."""
    automotive_keywords = ["car", "suv", "automotive", "vehicle", "auto", "truck"]
    for keyword in automotive_keywords:
        pattern = rf'\b{keyword}s?\b'
        if re.search(pattern, vertical_lower):
            return True
        if keyword in vertical_lower:
            idx = vertical_lower.find(keyword)
            is_start = idx == 0 or not vertical_lower[idx-1].isalpha()
            is_end = idx + len(keyword) == len(vertical_lower) or not vertical_lower[idx + len(keyword)].isalpha()
            if is_start and is_end:
                return True
    return False


def _build_extraction_system_prompt(
    vertical: str,
    vertical_description: str,
    augmentation_context: Optional[Dict] = None,
    min_expected_entities: Optional[int] = None,
    retry_feedback: Optional[str] = None,
) -> str:
    """Build the system prompt for entity extraction using template."""
    is_automotive = _is_automotive_vertical(vertical.lower()) if vertical else False
    context = augmentation_context or {}
    base_prompt = load_prompt(
        "extraction_system_prompt",
        vertical=vertical,
        vertical_description=vertical_description,
        is_automotive=is_automotive,
        validated_brands=context.get("validated_brands", []),
        validated_products=context.get("validated_products", []),
        rejected_brands=context.get("rejected_brands", []),
        rejected_products=context.get("rejected_products", []),
    )

    # Add expected count guidance if provided
    if min_expected_entities:
        base_prompt += (
            f"\n\nIMPORTANT: The text appears to list approximately "
            f"{min_expected_entities} items. Ensure you extract at least "
            f"{min_expected_entities} brand/product entities."
        )

    # Add retry feedback if this is a retry attempt
    if retry_feedback:
        base_prompt += f"\n\nFEEDBACK FROM PREVIOUS ATTEMPT:\n{retry_feedback}"

    return base_prompt


def _build_extraction_prompt(text: str) -> str:
    """Build the user prompt for entity extraction using template."""
    text_snippet = text[:2000] if len(text) > 2000 else text
    return load_prompt("extraction_user_prompt", text=text_snippet)


def _parse_extraction_response(response: str) -> Dict[str, List[str]]:
    """Parse the Qwen extraction response."""
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


def _parse_entities_format(parsed: Dict) -> Dict[str, List[str]]:
    """Parse the entities format response."""
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
