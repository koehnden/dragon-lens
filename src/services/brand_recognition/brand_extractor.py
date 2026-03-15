"""Legacy brand/product normalization helpers kept for active workflows."""

import logging
import re
from typing import Dict, List, Tuple

from services.brand_recognition.config import (
    ENABLE_WIKIDATA_NORMALIZATION,
)
from services.brand_recognition.classification import (
    is_likely_brand,
    is_likely_product,
    _has_product_model_patterns,
    _has_product_suffix,
)
from services.brand_recognition.prompts import load_prompt
from constants import GENERIC_TERMS, PRODUCT_HINTS

# Note: Many functions below (_normalize_brands_unified, _validate_products, etc.)
# are kept for use by the consolidation service. They are no longer called
# during per-prompt extraction.

logger = logging.getLogger(__name__)

def _calculate_brand_confidence(entity: str, entity_lower: str, vertical: str) -> float:
    """Calculate confidence score for a brand entity."""
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
    """Calculate confidence score for a product entity."""
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
    """Check if entity is a known brand in Wikidata."""
    try:
        from services.wikidata_lookup import (
            is_known_brand as wikidata_is_known_brand,
            get_cache_available as wikidata_cache_available,
        )
        if not wikidata_cache_available():
            return False
        return wikidata_is_known_brand(entity, vertical)
    except Exception:
        return False


def _check_wikidata_product(entity: str, vertical: str) -> bool:
    """Check if entity is a known product in Wikidata."""
    try:
        from services.wikidata_lookup import (
            is_known_product as wikidata_is_known_product,
            get_cache_available as wikidata_cache_available,
        )
        if not wikidata_cache_available():
            return False
        return wikidata_is_known_product(entity, vertical)
    except Exception:
        return False

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



async def _normalize_brands_unified(
    brands: List[str],
    vertical: str,
    vertical_description: str,
    ollama,
) -> Dict:
    """Normalize brands using Wikidata and/or Qwen."""
    if not brands:
        return {"brands": [], "rejected": []}

    wikidata_known = []
    wikidata_rejected = []
    need_qwen = list(brands)

    if ENABLE_WIKIDATA_NORMALIZATION:
        wikidata_known, wikidata_rejected, need_qwen = _process_brands_with_wikidata(
            brands, vertical
        )

    qwen_result = {"brands": [], "rejected": []}
    if need_qwen:
        qwen_result = await _normalize_brands_with_qwen(
            ollama, need_qwen, vertical, vertical_description
        )

    all_brands = _merge_and_deduplicate_brands(
        wikidata_known, qwen_result.get("brands", [])
    )
    all_rejected = wikidata_rejected + qwen_result.get("rejected", [])

    logger.info(
        f"Brand normalization: {len(brands)} input -> "
        f"{len(all_brands)} normalized, {len(all_rejected)} rejected"
    )

    return {"brands": all_brands, "rejected": all_rejected}


def _process_brands_with_wikidata(
    brands: List[str],
    vertical: str
) -> Tuple[List[Dict], List[Dict], List[str]]:
    """Process brands using Wikidata lookup."""
    from services.wikidata_lookup import (
        get_canonical_brand_name,
        get_chinese_name,
        is_brand_in_vertical,
    )

    wikidata_known = []
    wikidata_rejected = []
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

    return wikidata_known, wikidata_rejected, need_qwen


async def _normalize_brands_with_qwen(
    ollama,
    brands: List[str],
    vertical: str,
    vertical_description: str
) -> Dict:
    """Normalize brands using Qwen."""
    prompt = _build_brand_normalization_prompt(brands, vertical, vertical_description)
    try:
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt=prompt,
            system_prompt="",
            temperature=0.0,
        )
        return _parse_normalization_response(response)
    except Exception as e:
        logger.warning(f"Brand normalization failed: {e}")
        return {
            "brands": [{"canonical": b, "chinese": "", "original_forms": [b]} for b in brands],
            "rejected": []
        }


def _build_brand_normalization_prompt(
    brands: List[str],
    vertical: str,
    vertical_description: str
) -> str:
    """Build prompt for brand normalization using template."""
    import json
    brands_json = json.dumps(brands, ensure_ascii=False)
    return load_prompt(
        "brand_normalization_prompt",
        vertical=vertical,
        vertical_description=vertical_description,
        brands_json=brands_json,
        validated_brands=[],
        rejected_brands=[],
    )


def _parse_normalization_response(response: str) -> Dict:
    """Parse brand normalization response."""
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


def _merge_and_deduplicate_brands(
    wikidata_brands: List[Dict],
    qwen_brands: List[Dict]
) -> List[Dict]:
    """Merge and deduplicate brands from multiple sources."""
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
        canonical_map[canonical]["original_forms"].extend(brand.get("original_forms", []))

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
        canonical_map[canonical]["original_forms"].extend(brand.get("original_forms", []))

    for key in canonical_map:
        canonical_map[key]["original_forms"] = list(
            dict.fromkeys(canonical_map[key]["original_forms"])
        )

    return list(canonical_map.values())


async def _validate_products(
    ollama,
    products: List[str],
    text: str,
    vertical: str,
    vertical_description: str,
) -> List[str]:
    """Validate product candidates."""
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


def _build_product_validation_system_prompt(vertical: str, vertical_description: str) -> str:
    """Build system prompt for product validation using template."""
    return load_prompt(
        "product_validation_system_prompt",
        vertical=vertical,
        vertical_description=vertical_description,
    )


def _build_product_validation_prompt(products: List[str], text_snippet: str, vertical: str) -> str:
    """Build prompt for product validation using template."""
    import json
    products_json = json.dumps(products, ensure_ascii=False)
    return load_prompt(
        "product_validation_user_prompt",
        products_json=products_json,
        text=text_snippet,
    )


def _parse_single_type_validation_response(response: str, original_entities: List[str]) -> List[str]:
    """Parse validation response for a single entity type."""
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
