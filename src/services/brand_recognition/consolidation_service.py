"""
Enhanced consolidation service for brand recognition.

This module handles the consolidation of raw entity extractions from multiple
prompts, applying normalization, validation, and filtering at the run level
rather than per-prompt.
"""

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Any

from sqlalchemy.orm import Session

from models import (
    ConsolidationDebug,
    EntityType,
    ExtractionDebug,
    LLMAnswer,
    RejectedEntity,
    Run,
)
from services.brand_recognition.models import ConsolidationDebugInfo
from services.brand_recognition.list_processor import (
    is_list_format,
    split_into_list_items,
)

logger = logging.getLogger(__name__)


@dataclass
class AnswerEntities:
    """Entities extracted from a single answer."""
    answer_id: int
    answer_text: str
    raw_brands: List[str]
    raw_products: List[str]


@dataclass
class ConsolidationInput:
    """Input for consolidation gathered from all answers in a run."""
    run_id: int
    vertical_id: int
    vertical_name: str
    vertical_description: str
    answer_entities: List[AnswerEntities]
    all_unique_brands: Set[str]
    all_unique_products: Set[str]
    all_rejected_at_light_filter: Set[str]


@dataclass
class NormalizationResult:
    """Result of brand normalization."""
    normalized_brands: Dict[str, str]
    rejected_brands: List[dict]


@dataclass
class ValidationResult:
    """Result of product validation."""
    valid_products: Set[str]
    rejected_products: List[str]


@dataclass
class EnhancedConsolidationResult:
    """Result of the enhanced consolidation process."""
    final_brands: Dict[str, List[str]]
    final_products: Dict[str, List[str]]
    debug_info: ConsolidationDebugInfo


def gather_consolidation_input(db: Session, run_id: int) -> ConsolidationInput:
    """Gather all raw entities from ExtractionDebug for a run."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    vertical = run.vertical
    answers = db.query(LLMAnswer).filter(LLMAnswer.run_id == run_id).all()

    answer_entities_list: List[AnswerEntities] = []
    all_brands: Set[str] = set()
    all_products: Set[str] = set()
    all_rejected_at_light_filter: Set[str] = set()

    for answer in answers:
        debug = db.query(ExtractionDebug).filter(
            ExtractionDebug.llm_answer_id == answer.id
        ).first()

        if not debug:
            continue

        raw_brands = json.loads(debug.final_brands or "[]")
        raw_products = json.loads(debug.final_products or "[]")
        rejected_at_light = json.loads(debug.rejected_at_light_filter or "[]")

        answer_entities_list.append(AnswerEntities(
            answer_id=answer.id,
            answer_text=answer.raw_answer_zh or "",
            raw_brands=raw_brands,
            raw_products=raw_products,
        ))

        all_brands.update(raw_brands)
        all_products.update(raw_products)
        all_rejected_at_light_filter.update(rejected_at_light)

    logger.info(
        f"[Consolidation] Gathered from {len(answer_entities_list)} answers: "
        f"{len(all_brands)} unique brands, {len(all_products)} unique products, "
        f"{len(all_rejected_at_light_filter)} rejected at light filter"
    )

    return ConsolidationInput(
        run_id=run_id,
        vertical_id=vertical.id,
        vertical_name=vertical.name,
        vertical_description=vertical.description or "",
        answer_entities=answer_entities_list,
        all_unique_brands=all_brands,
        all_unique_products=all_products,
        all_rejected_at_light_filter=all_rejected_at_light_filter,
    )


async def normalize_brands_batch(
    brands: List[str],
    vertical: str,
    vertical_description: str,
    db: Optional[Session] = None,
    vertical_id: Optional[int] = None,
) -> NormalizationResult:
    """Normalize all brands in a single Qwen call with bypass for validated brands."""
    if not brands:
        return NormalizationResult(normalized_brands={}, rejected_brands=[])

    from services.ollama import OllamaService
    from services.brand_recognition.prompts import load_prompt

    bypass_brands: Dict[str, str] = {}
    need_normalization: List[str] = []
    validated_brand_names: Set[str] = set()
    augmentation_context: Dict = {}

    if db is not None and vertical_id is not None:
        from services.brand_recognition.extraction_augmentation import (
            get_validated_brands_for_prompt,
            get_rejected_brands_for_prompt,
            get_validated_entity_names,
            get_canonical_for_validated_brand,
        )
        validated_brand_names, _ = get_validated_entity_names(db, vertical_id)
        augmentation_context = {
            "validated_brands": get_validated_brands_for_prompt(db, vertical_id),
            "rejected_brands": get_rejected_brands_for_prompt(db, vertical_id),
        }

        for brand in brands:
            if brand in validated_brand_names or brand.lower() in validated_brand_names:
                canonical = get_canonical_for_validated_brand(db, brand, vertical_id)
                bypass_brands[brand] = canonical
                logger.debug(f"[Consolidation] Bypassed normalization for validated brand: {brand} -> {canonical}")
            else:
                need_normalization.append(brand)
    else:
        need_normalization = list(brands)

    if bypass_brands:
        logger.info(f"[Consolidation] Bypassed {len(bypass_brands)} validated brands in normalization")

    qwen_result = NormalizationResult(normalized_brands={}, rejected_brands=[])
    if need_normalization:
        ollama = OllamaService()
        brands_json = json.dumps(need_normalization, ensure_ascii=False)

        prompt = load_prompt(
            "brand_normalization_prompt",
            vertical=vertical,
            vertical_description=vertical_description,
            brands_json=brands_json,
            validated_brands=augmentation_context.get("validated_brands", []),
            rejected_brands=augmentation_context.get("rejected_brands", []),
        )

        try:
            response = await ollama._call_ollama(
                model=ollama.ner_model,
                prompt=prompt,
                system_prompt="",
                temperature=0.0,
            )
            qwen_result = _parse_normalization_response(response, need_normalization)
        except Exception as e:
            logger.error(f"Brand normalization failed: {e}")
            qwen_result = NormalizationResult(
                normalized_brands={b: b for b in need_normalization},
                rejected_brands=[],
            )

    merged_brands = {**bypass_brands, **qwen_result.normalized_brands}

    logger.info(
        f"[Consolidation] Brand normalization: {len(brands)} input -> "
        f"{len(bypass_brands)} bypassed, {len(qwen_result.normalized_brands)} from Qwen, "
        f"{len(qwen_result.rejected_brands)} rejected"
    )

    return NormalizationResult(
        normalized_brands=merged_brands,
        rejected_brands=qwen_result.rejected_brands,
    )


def _parse_normalization_response(
    response: str,
    original_brands: List[str],
) -> NormalizationResult:
    """Parse the brand normalization response from Qwen."""
    import re

    response = response.strip()
    if response.startswith("```json"):
        response = response[7:]
    if response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    response = response.strip()

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                return NormalizationResult(
                    normalized_brands={b: b for b in original_brands},
                    rejected_brands=[],
                )
        else:
            return NormalizationResult(
                normalized_brands={b: b for b in original_brands},
                rejected_brands=[],
            )

    normalized_brands: Dict[str, str] = {}
    rejected_brands: List[dict] = data.get("rejected", [])

    for brand_info in data.get("brands", []):
        canonical = brand_info.get("canonical", "")
        original_forms = brand_info.get("original_forms", [])

        for form in original_forms:
            if form in original_brands:
                normalized_brands[form] = canonical

    for brand in original_brands:
        if brand not in normalized_brands:
            normalized_brands[brand] = brand

    return NormalizationResult(
        normalized_brands=normalized_brands,
        rejected_brands=rejected_brands,
    )


async def validate_products_batch(
    products: List[str],
    sample_text: str,
    vertical: str,
    vertical_description: str,
    db: Optional[Session] = None,
    vertical_id: Optional[int] = None,
) -> ValidationResult:
    """Validate all products in a single Qwen call with bypass for validated products."""
    if not products:
        return ValidationResult(valid_products=set(), rejected_products=[])

    from services.ollama import OllamaService
    from services.brand_recognition.prompts import load_prompt

    bypass_products: Set[str] = set()
    need_validation: List[str] = []
    validated_product_names: Set[str] = set()
    augmentation_context: Dict = {}

    if db is not None and vertical_id is not None:
        from services.brand_recognition.extraction_augmentation import (
            get_validated_products_for_prompt,
            get_rejected_products_for_prompt,
            get_validated_entity_names,
        )
        _, validated_product_names = get_validated_entity_names(db, vertical_id)
        augmentation_context = {
            "validated_products": get_validated_products_for_prompt(db, vertical_id),
            "rejected_products": get_rejected_products_for_prompt(db, vertical_id),
        }

        for product in products:
            if product in validated_product_names or product.lower() in validated_product_names:
                bypass_products.add(product)
                logger.debug(f"[Consolidation] Bypassed validation for validated product: {product}")
            else:
                need_validation.append(product)
    else:
        need_validation = list(products)

    if bypass_products:
        logger.info(f"[Consolidation] Bypassed {len(bypass_products)} validated products in validation")

    qwen_result = ValidationResult(valid_products=set(), rejected_products=[])
    if need_validation:
        ollama = OllamaService()
        products_json = json.dumps(need_validation, ensure_ascii=False)

        system_prompt = load_prompt(
            "product_validation_system_prompt",
            vertical=vertical,
            vertical_description=vertical_description,
            validated_products=augmentation_context.get("validated_products", []),
            rejected_products=augmentation_context.get("rejected_products", []),
        )
        prompt = load_prompt(
            "product_validation_user_prompt",
            text=sample_text[:2000],
            products_json=products_json,
        )

        try:
            response = await ollama._call_ollama(
                model=ollama.ner_model,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.0,
            )
            qwen_result = _parse_validation_response(response, need_validation)
        except Exception as e:
            logger.error(f"Product validation failed: {e}")
            qwen_result = ValidationResult(
                valid_products=set(need_validation),
                rejected_products=[],
            )

    merged_valid = bypass_products | qwen_result.valid_products

    logger.info(
        f"[Consolidation] Product validation: {len(products)} input -> "
        f"{len(bypass_products)} bypassed, {len(qwen_result.valid_products)} from Qwen, "
        f"{len(qwen_result.rejected_products)} rejected"
    )

    return ValidationResult(
        valid_products=merged_valid,
        rejected_products=qwen_result.rejected_products,
    )


def _parse_validation_response(
    response: str,
    original_products: List[str],
) -> ValidationResult:
    """Parse the product validation response from Qwen."""
    import re

    response = response.strip()
    if response.startswith("```json"):
        response = response[7:]
    if response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    response = response.strip()

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                return ValidationResult(
                    valid_products=set(original_products),
                    rejected_products=[],
                )
        else:
            return ValidationResult(
                valid_products=set(original_products),
                rejected_products=[],
            )

    valid = set(data.get("valid", []))
    invalid = data.get("invalid", [])

    return ValidationResult(valid_products=valid, rejected_products=invalid)


def apply_list_position_filter_per_answer(
    answer_entities: AnswerEntities,
    brand_mapping: Dict[str, str],
    valid_products: Set[str],
    validated_brand_names: Optional[Set[str]] = None,
    validated_product_names: Optional[Set[str]] = None,
) -> Tuple[Set[str], Set[str], List[str]]:
    """Apply list position filter for a single answer using raw names.

    Validated brands/products bypass the filter and are always kept.

    Returns:
        Tuple of (kept_normalized_brands, kept_products, rejected_entities)
    """
    text = answer_entities.answer_text
    raw_brands = answer_entities.raw_brands
    raw_products = answer_entities.raw_products
    validated_brand_names = validated_brand_names or set()
    validated_product_names = validated_product_names or set()

    if not is_list_format(text):
        kept_brands = {brand_mapping.get(b, b) for b in raw_brands}
        kept_products = {p for p in raw_products if p in valid_products}
        return kept_brands, kept_products, []

    list_items = split_into_list_items(text)
    if not list_items:
        kept_brands = {brand_mapping.get(b, b) for b in raw_brands}
        kept_products = {p for p in raw_products if p in valid_products}
        return kept_brands, kept_products, []

    primary_brands: Set[str] = set()
    primary_products: Set[str] = set()

    for item in list_items:
        first_brand = _find_first_entity_in_text(item, raw_brands)
        first_product = _find_first_entity_in_text(item, raw_products)

        if first_brand:
            primary_brands.add(first_brand)
        if first_product and first_product in valid_products:
            primary_products.add(first_product)

    bypassed_brands = 0
    bypassed_products = 0
    for brand in raw_brands:
        if brand not in primary_brands:
            if brand in validated_brand_names or brand.lower() in validated_brand_names:
                primary_brands.add(brand)
                bypassed_brands += 1

    for product in raw_products:
        if product not in primary_products and product in valid_products:
            if product in validated_product_names or product.lower() in validated_product_names:
                primary_products.add(product)
                bypassed_products += 1

    if bypassed_brands or bypassed_products:
        logger.debug(
            f"[Consolidation] List filter bypass: {bypassed_brands} brands, {bypassed_products} products"
        )

    rejected = []
    for brand in raw_brands:
        if brand not in primary_brands:
            rejected.append(brand)
    for product in raw_products:
        if product not in primary_products and product in valid_products:
            rejected.append(product)

    kept_normalized_brands = {brand_mapping.get(b, b) for b in primary_brands}

    logger.debug(
        f"[Consolidation] List filter for answer {answer_entities.answer_id}: "
        f"kept {len(kept_normalized_brands)} brands, {len(primary_products)} products"
    )

    return kept_normalized_brands, primary_products, rejected


def _find_first_entity_in_text(text: str, entities: List[str]) -> Optional[str]:
    """Find the first occurring entity in the text."""
    if not entities:
        return None

    first_pos = len(text) + 1
    first_entity = None

    for entity in entities:
        pos = text.find(entity)
        if pos != -1 and pos < first_pos:
            first_pos = pos
            first_entity = entity

    return first_entity


async def run_enhanced_consolidation(
    db: Session,
    run_id: int,
) -> EnhancedConsolidationResult:
    """Run the enhanced consolidation process for a run."""
    consolidation_input = gather_consolidation_input(db, run_id)

    if not consolidation_input.all_unique_brands and not consolidation_input.all_unique_products:
        logger.info("[Consolidation] No entities to consolidate")
        debug_info = ConsolidationDebugInfo(
            input_brands=[],
            input_products=[],
            rejected_at_normalization=[],
            rejected_at_validation=[],
            rejected_at_list_filter=[],
            final_brands=[],
            final_products=[],
        )
        return EnhancedConsolidationResult(
            final_brands={},
            final_products={},
            debug_info=debug_info,
        )

    sample_text = ""
    if consolidation_input.answer_entities:
        sample_text = consolidation_input.answer_entities[0].answer_text

    from services.brand_recognition.extraction_augmentation import get_validated_entity_names
    validated_brand_names, validated_product_names = get_validated_entity_names(
        db, consolidation_input.vertical_id
    )

    normalization_result = await normalize_brands_batch(
        list(consolidation_input.all_unique_brands),
        consolidation_input.vertical_name,
        consolidation_input.vertical_description,
        db=db,
        vertical_id=consolidation_input.vertical_id,
    )

    validation_result = await validate_products_batch(
        list(consolidation_input.all_unique_products),
        sample_text,
        consolidation_input.vertical_name,
        consolidation_input.vertical_description,
        db=db,
        vertical_id=consolidation_input.vertical_id,
    )

    all_kept_brands: Set[str] = set()
    all_kept_products: Set[str] = set()
    all_rejected_at_list_filter: List[str] = []

    for answer_entities in consolidation_input.answer_entities:
        kept_brands, kept_products, rejected = apply_list_position_filter_per_answer(
            answer_entities,
            normalization_result.normalized_brands,
            validation_result.valid_products,
            validated_brand_names=validated_brand_names,
            validated_product_names=validated_product_names,
        )
        all_kept_brands.update(kept_brands)
        all_kept_products.update(kept_products)
        all_rejected_at_list_filter.extend(rejected)

    all_rejected_at_list_filter = list(set(all_rejected_at_list_filter))

    final_brands = {b: [b] for b in all_kept_brands}
    final_products = {p: [p] for p in all_kept_products}

    debug_info = ConsolidationDebugInfo(
        input_brands=list(consolidation_input.all_unique_brands),
        input_products=list(consolidation_input.all_unique_products),
        rejected_at_normalization=normalization_result.rejected_brands,
        rejected_at_validation=validation_result.rejected_products,
        rejected_at_list_filter=all_rejected_at_list_filter,
        final_brands=list(final_brands.keys()),
        final_products=list(final_products.keys()),
    )

    _store_consolidation_debug(db, run_id, debug_info)
    _store_rejected_entities(
        db,
        consolidation_input.vertical_id,
        normalization_result.rejected_brands,
        validation_result.rejected_products,
        all_rejected_at_list_filter,
        list(consolidation_input.all_rejected_at_light_filter),
    )

    logger.info(
        f"[Consolidation] Final results: {len(final_brands)} brands, {len(final_products)} products"
    )

    return EnhancedConsolidationResult(
        final_brands=final_brands,
        final_products=final_products,
        debug_info=debug_info,
    )


def _store_consolidation_debug(
    db: Session,
    run_id: int,
    debug_info: ConsolidationDebugInfo,
) -> None:
    """Store consolidation debug information."""
    debug_record = ConsolidationDebug(
        run_id=run_id,
        input_brands=json.dumps(debug_info.input_brands, ensure_ascii=False),
        input_products=json.dumps(debug_info.input_products, ensure_ascii=False),
        rejected_at_normalization=json.dumps(debug_info.rejected_at_normalization, ensure_ascii=False),
        rejected_at_validation=json.dumps(debug_info.rejected_at_validation, ensure_ascii=False),
        rejected_at_list_filter=json.dumps(debug_info.rejected_at_list_filter, ensure_ascii=False),
        final_brands=json.dumps(debug_info.final_brands, ensure_ascii=False),
        final_products=json.dumps(debug_info.final_products, ensure_ascii=False),
    )
    db.add(debug_record)


def _store_rejected_entities(
    db: Session,
    vertical_id: int,
    rejected_at_normalization: List[dict],
    rejected_at_validation: List[str],
    rejected_at_list_filter: List[str],
    rejected_at_light_filter: List[str],
) -> None:
    """Store rejected entities for future analysis."""
    for rejected in rejected_at_normalization:
        name = rejected.get("name", str(rejected))
        reason = rejected.get("reason", "rejected_at_normalization")
        _add_rejected_entity(db, vertical_id, EntityType.BRAND, name, reason)

    for product in rejected_at_validation:
        _add_rejected_entity(
            db, vertical_id, EntityType.PRODUCT, product, "rejected_at_validation"
        )

    for entity in rejected_at_list_filter:
        _add_rejected_entity(
            db, vertical_id, EntityType.BRAND, entity, "rejected_at_list_filter"
        )

    for entity in rejected_at_light_filter:
        _add_rejected_entity(
            db, vertical_id, EntityType.BRAND, entity, "light_filter"
        )


def _add_rejected_entity(
    db: Session,
    vertical_id: int,
    entity_type: EntityType,
    name: str,
    reason: str,
) -> None:
    """Add a rejected entity if it doesn't already exist."""
    existing = db.query(RejectedEntity).filter(
        RejectedEntity.vertical_id == vertical_id,
        RejectedEntity.entity_type == entity_type,
        RejectedEntity.name == name,
    ).first()

    if not existing:
        rejected = RejectedEntity(
            vertical_id=vertical_id,
            entity_type=entity_type,
            name=name,
            rejection_reason=reason,
        )
        db.add(rejected)
