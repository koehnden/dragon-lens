"""
Brand extraction using Qwen.

This module contains functions for extracting entities using Qwen-based
extraction with structured prompts.
"""

import logging
import re
from typing import Dict, List, Set, Tuple

from services.brand_recognition.models import (
    EntityCandidate,
    ExtractionResult,
    ExtractionDebugInfo,
)
from services.brand_recognition.config import (
    ENABLE_CONFIDENCE_VERIFICATION,
    ENABLE_WIKIDATA_NORMALIZATION,
    ENABLE_BRAND_VALIDATION,
    AMBIGUOUS_CONFIDENCE_THRESHOLD,
)
from services.brand_recognition.classification import (
    is_likely_brand,
    is_likely_product,
    _has_product_model_patterns,
    _has_product_suffix,
)
from services.brand_recognition.list_processor import _filter_by_list_position
from services.brand_recognition.prompts import load_prompt
from constants import GENERIC_TERMS, PRODUCT_HINTS

logger = logging.getLogger(__name__)


async def _extract_entities_with_qwen(
    text: str,
    vertical: str = "",
    vertical_description: str = ""
) -> ExtractionResult:
    """Extract entities using Qwen-based extraction."""
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
            corrected_brands, corrected_products = await _process_with_confidence_verification(
                ollama, brands, products, relationships, text, vertical, vertical_description
            )
        else:
            logger.info("[Extraction] Skipping confidence verification (ENABLE_CONFIDENCE_VERIFICATION=false)")
            corrected_brands = list(dict.fromkeys(brands))
            corrected_products = list(dict.fromkeys(products))

        normalized_result = await _normalize_brands_unified(
            corrected_brands, vertical, vertical_description, ollama
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

        normalized_brands = [b["canonical"] for b in normalized_result.get("brands", [])]
        brand_chinese_map = {
            b["canonical"]: b.get("chinese", "")
            for b in normalized_result.get("brands", [])
        }

        logger.info(f"[Extraction] Normalized brands: {normalized_brands}")

        candidates = _build_candidates_from_results(
            normalized_brands, validated_products, brand_chinese_map
        )

        filtered = _filter_by_list_position(candidates, text)

        filtered_out_list = list(set(c.name for c in candidates) - set(c.name for c in filtered))
        if filtered_out_list:
            logger.info(f"[Extraction] Filtered by list position: {filtered_out_list}")

        brand_clusters, product_clusters = _build_clusters_from_filtered(
            filtered, brand_chinese_map
        )

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


async def _process_with_confidence_verification(
    ollama,
    brands: List[str],
    products: List[str],
    relationships: Dict[str, str],
    text: str,
    vertical: str,
    vertical_description: str,
) -> Tuple[List[str], List[str]]:
    """Process entities with confidence verification."""
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
    verified_results = {}
    if ambiguous_entities:
        verified_results = await _verify_ambiguous_entities_with_qwen(
            ollama, ambiguous_entities, text, vertical, vertical_description
        )
        logger.info(f"[Extraction] Ambiguous entities verified: {verified_results}")

    corrected_brands = _process_brands_with_verification(
        brands, verified_results, brand_confidences
    )
    corrected_products = _process_products_with_verification(
        products, verified_results, product_confidences
    )

    return list(dict.fromkeys(corrected_brands)), list(dict.fromkeys(corrected_products))


def _build_candidates_from_results(
    normalized_brands: List[str],
    validated_products: List[str],
    brand_chinese_map: Dict[str, str],
) -> List[EntityCandidate]:
    """Build EntityCandidate list from normalized results."""
    candidates = [
        EntityCandidate(name=b, source="qwen", entity_type="brand")
        for b in normalized_brands
    ] + [
        EntityCandidate(name=p, source="qwen", entity_type="product")
        for p in validated_products
    ]
    return candidates


def _build_clusters_from_filtered(
    filtered: List[EntityCandidate],
    brand_chinese_map: Dict[str, str],
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Build brand and product clusters from filtered candidates."""
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

    return brand_clusters, product_clusters


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


def _build_extraction_system_prompt(vertical: str, vertical_description: str) -> str:
    """Build the system prompt for entity extraction using template."""
    is_automotive = _is_automotive_vertical(vertical.lower()) if vertical else False
    return load_prompt(
        "extraction_system_prompt",
        vertical=vertical,
        vertical_description=vertical_description,
        is_automotive=is_automotive,
    )


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


def _calculate_confidence_scores(entities: List[str], vertical: str, is_brand: bool) -> Dict[str, float]:
    """Calculate confidence scores for entities."""
    scores = {}
    for entity in entities:
        entity_lower = entity.lower()
        if is_brand:
            confidence = _calculate_brand_confidence(entity, entity_lower, vertical)
        else:
            confidence = _calculate_product_confidence(entity, entity_lower, vertical)
        scores[entity] = max(0.1, min(0.95, confidence))
    return scores


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


def _boost_confidence_for_known_relationships(
    product_confidences: Dict[str, float],
    relationships: Dict[str, str],
    brands: List[str]
) -> Dict[str, float]:
    """Boost confidence for products with known brand relationships."""
    for product, parent in relationships.items():
        if product in product_confidences and parent in brands:
            product_confidences[product] = min(0.95, product_confidences[product] + 0.2)
            logger.debug(f"Boosted confidence for product '{product}' (parent: {parent})")
    return product_confidences


def _identify_ambiguous_entities(
    brand_confidences: Dict[str, float],
    product_confidences: Dict[str, float]
) -> Tuple[List[str], Dict[str, str]]:
    """Identify entities with low confidence scores."""
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


async def _verify_ambiguous_entities_with_qwen(
    ollama,
    ambiguous_entities: List[str],
    text: str,
    vertical: str = "",
    vertical_description: str = ""
) -> Dict[str, str]:
    """Verify ambiguous entities with Qwen."""
    if not ambiguous_entities:
        return {}

    candidates = [EntityCandidate(name=e, source="ambiguous") for e in ambiguous_entities]
    return await _verify_batch_with_qwen(ollama, candidates, text, vertical, vertical_description)


def _process_brands_with_verification(
    brands: List[str],
    verified_results: Dict[str, str],
    brand_confidences: Dict[str, float]
) -> List[str]:
    """Process brands with verification results."""
    corrected_brands = []
    for brand in brands:
        if brand in verified_results:
            if verified_results[brand] == "brand":
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
    """Process products with verification results."""
    corrected_products = []
    for product in products:
        if product in verified_results:
            if verified_results[product] == "product":
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


async def _verify_batch_with_qwen(
    ollama,
    batch: List[EntityCandidate],
    text: str,
    vertical: str = "",
    vertical_description: str = ""
) -> Dict[str, str]:
    """Verify a batch of entities with Qwen."""
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
