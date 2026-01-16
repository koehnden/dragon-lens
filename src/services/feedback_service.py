from typing import Iterable

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Run, RunStatus, Vertical
from models.domain import EntityType
from models.knowledge_domain import (
    FeedbackStatus,
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeFeedbackEvent,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeProductBrandMapping,
    KnowledgeRejectedEntity,
    KnowledgeTranslationOverride,
    KnowledgeVertical,
    KnowledgeVerticalAlias,
)
from models.schemas import (
    FeedbackAction,
    FeedbackAppliedSummary,
    FeedbackCanonicalVertical,
    FeedbackLanguage,
    FeedbackMappingAction,
    FeedbackMappingFeedbackItem,
    FeedbackProductFeedbackItem,
    FeedbackSubmitRequest,
    FeedbackSubmitResponse,
    FeedbackTranslationOverrideItem,
    FeedbackBrandFeedbackItem,
    FeedbackVerticalAliasResponse,
)
from services.canonicalization_metrics import normalize_entity_key


def submit_feedback(
    db: Session,
    knowledge_db: Session,
    payload: FeedbackSubmitRequest,
    reviewer: str = "user",
    reviewer_model: str | None = None,
) -> FeedbackSubmitResponse:
    _validate_payload(payload)
    _validate_run(db, payload.run_id, payload.vertical_id)
    vertical = _load_vertical(db, payload.vertical_id)
    canonical = _resolve_canonical_vertical(knowledge_db, payload.canonical_vertical)
    _ensure_vertical_alias(knowledge_db, canonical.id, vertical.name)
    applied = _apply_feedback(knowledge_db, canonical.id, payload)
    _store_feedback_event(knowledge_db, canonical.id, payload, reviewer, reviewer_model)
    knowledge_db.commit()
    return _response(payload.run_id, canonical.id, applied)


def validate_feedback_request(
    db: Session,
    payload: FeedbackSubmitRequest,
) -> Vertical:
    _validate_payload(payload)
    _validate_run(db, payload.run_id, payload.vertical_id)
    return _load_vertical(db, payload.vertical_id)


def save_vertical_alias(
    db: Session,
    knowledge_db: Session,
    vertical_id: int,
    canonical: FeedbackCanonicalVertical,
) -> FeedbackVerticalAliasResponse:
    vertical = _load_vertical(db, vertical_id)
    resolved = _resolve_canonical_vertical(knowledge_db, canonical)
    created = _ensure_vertical_alias_created(knowledge_db, resolved.id, vertical.name)
    knowledge_db.commit()
    return FeedbackVerticalAliasResponse(
        status="ok",
        vertical_id=vertical.id,
        vertical_name=vertical.name,
        canonical_vertical_id=resolved.id,
        canonical_vertical_name=resolved.name,
        alias_created=created,
    )


def _validate_payload(payload: FeedbackSubmitRequest) -> None:
    _validate_canonical_vertical(payload.canonical_vertical)
    _validate_brand_items(payload.brand_feedback)
    _validate_product_items(payload.product_feedback)
    _validate_mapping_items(payload.mapping_feedback)
    _validate_translation_items(payload.translation_overrides)


def _validate_run(db: Session, run_id: int, vertical_id: int) -> Run:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.vertical_id != vertical_id:
        raise HTTPException(status_code=400, detail="Run does not match vertical")
    if run.status != RunStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Run is not completed")
    return run


def _load_vertical(db: Session, vertical_id: int) -> Vertical:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail="Vertical not found")
    return vertical


def _validate_canonical_vertical(canonical: FeedbackCanonicalVertical) -> None:
    if canonical.is_new:
        _require(canonical.name, "Canonical vertical name is required")
        return
    _require(canonical.id, "Canonical vertical id is required")


def _validate_brand_items(items: Iterable[FeedbackBrandFeedbackItem]) -> None:
    for item in items:
        _validate_brand_item(item)


def _validate_brand_item(item: FeedbackBrandFeedbackItem) -> None:
    if item.action == FeedbackAction.REPLACE:
        _validate_replace_item(item.wrong_name, item.correct_name, "brand")
        return
    _require(item.name, "Brand name is required")


def _validate_product_items(items: Iterable[FeedbackProductFeedbackItem]) -> None:
    for item in items:
        _validate_product_item(item)


def _validate_product_item(item: FeedbackProductFeedbackItem) -> None:
    if item.action == FeedbackAction.REPLACE:
        _validate_replace_item(item.wrong_name, item.correct_name, "product")
        return
    _require(item.name, "Product name is required")


def _validate_mapping_items(items: Iterable[FeedbackMappingFeedbackItem]) -> None:
    for item in items:
        _validate_mapping_item(item)


def _validate_mapping_item(item: FeedbackMappingFeedbackItem) -> None:
    _require(item.product_name, "Product name is required for mapping")
    _require(item.brand_name, "Brand name is required for mapping")


def _validate_translation_items(
    items: Iterable[FeedbackTranslationOverrideItem],
) -> None:
    for item in items:
        _validate_translation_item(item)


def _validate_translation_item(item: FeedbackTranslationOverrideItem) -> None:
    _require(item.canonical_name, "Canonical name is required for translation")
    _require(item.override_text, "Override text is required for translation")
    _require(
        item.language == FeedbackLanguage.EN,
        "Only EN translation overrides are supported",
    )


def _validate_replace_item(
    wrong_name: str | None, correct_name: str | None, label: str
) -> None:
    _require(wrong_name, f"Wrong {label} name is required")
    _require(correct_name, f"Correct {label} name is required")
    _require(wrong_name != correct_name, f"{label} replacement must differ")


def _require(condition: object, message: str) -> None:
    if not condition:
        raise HTTPException(status_code=400, detail=message)


def _resolve_canonical_vertical(
    knowledge_db: Session,
    canonical: FeedbackCanonicalVertical,
) -> KnowledgeVertical:
    if canonical.is_new:
        return _get_or_create_vertical_by_name(knowledge_db, canonical.name or "")
    vertical = _get_vertical_by_id(knowledge_db, canonical.id or 0)
    if not vertical:
        raise HTTPException(status_code=404, detail="Canonical vertical not found")
    return vertical


def _get_or_create_vertical_by_name(
    knowledge_db: Session,
    name: str,
) -> KnowledgeVertical:
    return _get_vertical_by_name(knowledge_db, name) or _create_vertical(
        knowledge_db, name
    )


def _get_vertical_by_name(knowledge_db: Session, name: str) -> KnowledgeVertical | None:
    return (
        knowledge_db.query(KnowledgeVertical)
        .filter(func.lower(KnowledgeVertical.name) == name.casefold())
        .first()
    )


def _get_vertical_by_id(
    knowledge_db: Session, vertical_id: int
) -> KnowledgeVertical | None:
    return (
        knowledge_db.query(KnowledgeVertical)
        .filter(KnowledgeVertical.id == vertical_id)
        .first()
    )


def _create_vertical(knowledge_db: Session, name: str) -> KnowledgeVertical:
    vertical = KnowledgeVertical(name=name.strip())
    knowledge_db.add(vertical)
    knowledge_db.flush()
    return vertical


def _ensure_vertical_alias(
    knowledge_db: Session,
    vertical_id: int,
    alias: str,
) -> None:
    alias_key = normalize_entity_key(alias)
    existing = _find_vertical_alias(knowledge_db, alias_key)
    _raise_if_vertical_alias_conflict(existing, vertical_id, alias)
    if not existing:
        _add_vertical_alias(knowledge_db, vertical_id, alias, alias_key)


def _ensure_vertical_alias_created(
    knowledge_db: Session,
    vertical_id: int,
    alias: str,
) -> bool:
    alias_key = normalize_entity_key(alias)
    existing = _find_vertical_alias(knowledge_db, alias_key)
    _raise_if_vertical_alias_conflict(existing, vertical_id, alias)
    if existing:
        return False
    _add_vertical_alias(knowledge_db, vertical_id, alias, alias_key)
    return True


def _find_vertical_alias(
    knowledge_db: Session,
    alias_key: str,
) -> KnowledgeVerticalAlias | None:
    return (
        knowledge_db.query(KnowledgeVerticalAlias)
        .filter(KnowledgeVerticalAlias.alias_key == alias_key)
        .first()
    )


def _raise_if_vertical_alias_conflict(
    existing: KnowledgeVerticalAlias | None,
    requested_vertical_id: int,
    alias: str,
) -> None:
    if existing and existing.vertical_id != requested_vertical_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Vertical alias '{alias}' already mapped to canonical_vertical_id={existing.vertical_id}"
            ),
        )


def _add_vertical_alias(
    knowledge_db: Session,
    vertical_id: int,
    alias: str,
    alias_key: str,
) -> None:
    knowledge_db.add(
        KnowledgeVerticalAlias(
            vertical_id=vertical_id,
            alias=alias,
            alias_key=alias_key,
            source="user_input",
        )
    )


def _apply_feedback(
    knowledge_db: Session,
    vertical_id: int,
    payload: FeedbackSubmitRequest,
) -> FeedbackAppliedSummary:
    return _summary(_apply_counts(knowledge_db, vertical_id, payload))


def _apply_counts(
    knowledge_db: Session,
    vertical_id: int,
    payload: FeedbackSubmitRequest,
) -> tuple[int, int, int, int]:
    return (
        _apply_brand_feedback(knowledge_db, vertical_id, payload.brand_feedback),
        _apply_product_feedback(knowledge_db, vertical_id, payload.product_feedback),
        _apply_mapping_feedback(knowledge_db, vertical_id, payload.mapping_feedback),
        _apply_translation_overrides(
            knowledge_db, vertical_id, payload.translation_overrides
        ),
    )


def _summary(counts: tuple[int, int, int, int]) -> FeedbackAppliedSummary:
    return FeedbackAppliedSummary(
        brands=counts[0],
        products=counts[1],
        mappings=counts[2],
        translations=counts[3],
    )


def _apply_brand_feedback(
    knowledge_db: Session,
    vertical_id: int,
    items: Iterable[FeedbackBrandFeedbackItem],
) -> int:
    count = 0
    for item in items:
        _apply_brand_item(knowledge_db, vertical_id, item)
        count += 1
    return count


def _apply_brand_item(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackBrandFeedbackItem,
) -> None:
    if item.action == FeedbackAction.REPLACE:
        _apply_brand_replace(knowledge_db, vertical_id, item)
        return
    if item.action == FeedbackAction.VALIDATE:
        _apply_brand_validate(knowledge_db, vertical_id, item)
        return
    _apply_brand_reject(knowledge_db, vertical_id, item)


def _apply_brand_replace(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackBrandFeedbackItem,
) -> None:
    wrong = _clean_name(item.wrong_name)
    correct = _clean_name(item.correct_name)
    brand = _upsert_brand(knowledge_db, vertical_id, correct, True, "feedback")
    if _alias_variant_brand(wrong, correct):
        _add_knowledge_brand_alias(knowledge_db, brand.id, wrong)
        _delete_rejected(knowledge_db, vertical_id, EntityType.BRAND, wrong)
        return
    _upsert_rejected_entity(knowledge_db, vertical_id, EntityType.BRAND, wrong, item.reason)


def _apply_brand_validate(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackBrandFeedbackItem,
) -> None:
    _upsert_brand(knowledge_db, vertical_id, item.name, True, "feedback")


def _apply_brand_reject(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackBrandFeedbackItem,
) -> None:
    _upsert_rejected_entity(
        knowledge_db, vertical_id, EntityType.BRAND, item.name, item.reason
    )


def _apply_product_feedback(
    knowledge_db: Session,
    vertical_id: int,
    items: Iterable[FeedbackProductFeedbackItem],
) -> int:
    count = 0
    for item in items:
        _apply_product_item(knowledge_db, vertical_id, item)
        count += 1
    return count


def _apply_product_item(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackProductFeedbackItem,
) -> None:
    if item.action == FeedbackAction.REPLACE:
        _apply_product_replace(knowledge_db, vertical_id, item)
        return
    if item.action == FeedbackAction.VALIDATE:
        _apply_product_validate(knowledge_db, vertical_id, item)
        return
    _apply_product_reject(knowledge_db, vertical_id, item)


def _apply_product_replace(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackProductFeedbackItem,
) -> None:
    wrong = _clean_name(item.wrong_name)
    correct = _clean_name(item.correct_name)
    product = _upsert_product(knowledge_db, vertical_id, None, correct, True, "feedback")
    if _alias_variant_simple(wrong, correct):
        _add_knowledge_product_alias(knowledge_db, product.id, wrong)
        _delete_rejected(knowledge_db, vertical_id, EntityType.PRODUCT, wrong)
        return
    _upsert_rejected_entity(knowledge_db, vertical_id, EntityType.PRODUCT, wrong, item.reason)


def _apply_product_validate(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackProductFeedbackItem,
) -> None:
    _upsert_product(knowledge_db, vertical_id, None, item.name, True, "feedback")


def _apply_product_reject(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackProductFeedbackItem,
) -> None:
    _upsert_rejected_entity(
        knowledge_db, vertical_id, EntityType.PRODUCT, item.name, item.reason
    )


def _apply_mapping_feedback(
    knowledge_db: Session,
    vertical_id: int,
    items: Iterable[FeedbackMappingFeedbackItem],
) -> int:
    count = 0
    for item in items:
        _apply_mapping_item(knowledge_db, vertical_id, item)
        count += 1
    return count


def _apply_mapping_item(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackMappingFeedbackItem,
) -> None:
    if item.action == FeedbackMappingAction.ADD:
        _apply_mapping_add(knowledge_db, vertical_id, item)
        return
    if item.action == FeedbackMappingAction.VALIDATE:
        _apply_mapping_validate(knowledge_db, vertical_id, item)
        return
    _apply_mapping_reject(knowledge_db, vertical_id, item)


def _apply_mapping_add(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackMappingFeedbackItem,
) -> None:
    brand = _upsert_brand(knowledge_db, vertical_id, item.brand_name, True, "feedback")
    product = _upsert_product(
        knowledge_db, vertical_id, brand.id, item.product_name, True, "feedback"
    )
    _upsert_mapping(knowledge_db, vertical_id, product.id, brand.id, True, "feedback")


def _apply_mapping_validate(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackMappingFeedbackItem,
) -> None:
    brand = _upsert_brand(knowledge_db, vertical_id, item.brand_name, True, "feedback")
    product = _upsert_product(
        knowledge_db, vertical_id, brand.id, item.product_name, True, "feedback"
    )
    _upsert_mapping(knowledge_db, vertical_id, product.id, brand.id, True, "feedback")


def _apply_mapping_reject(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackMappingFeedbackItem,
) -> None:
    brand = _upsert_brand(knowledge_db, vertical_id, item.brand_name, False, None)
    product = _upsert_product(
        knowledge_db, vertical_id, None, item.product_name, False, None
    )
    _upsert_mapping(
        knowledge_db, vertical_id, product.id, brand.id, False, "user_reject"
    )


def _apply_translation_overrides(
    knowledge_db: Session,
    vertical_id: int,
    items: Iterable[FeedbackTranslationOverrideItem],
) -> int:
    count = 0
    for item in items:
        _upsert_translation_override(knowledge_db, vertical_id, item)
        count += 1
    return count


def _upsert_brand(
    knowledge_db: Session,
    vertical_id: int,
    name: str | None,
    validated: bool,
    source: str | None,
) -> KnowledgeBrand:
    clean = _clean_name(name)
    brand = _find_brand(knowledge_db, vertical_id, clean)
    return _save_brand(knowledge_db, brand, vertical_id, clean, validated, source)


def _find_brand(
    knowledge_db: Session,
    vertical_id: int,
    name: str,
) -> KnowledgeBrand | None:
    return (
        knowledge_db.query(KnowledgeBrand)
        .filter(
            KnowledgeBrand.vertical_id == vertical_id,
            func.lower(KnowledgeBrand.canonical_name) == name.casefold(),
        )
        .first()
    )


def _save_brand(
    knowledge_db: Session,
    brand: KnowledgeBrand | None,
    vertical_id: int,
    name: str,
    validated: bool,
    source: str | None,
) -> KnowledgeBrand:
    if brand:
        _set_brand_fields(brand, name, validated, source)
        return brand
    return _create_brand(knowledge_db, vertical_id, name, validated, source)


def _create_brand(
    knowledge_db: Session,
    vertical_id: int,
    name: str,
    validated: bool,
    source: str | None,
) -> KnowledgeBrand:
    brand = _new_brand(vertical_id, name, validated, source)
    knowledge_db.add(brand)
    knowledge_db.flush()
    return brand


def _set_brand_fields(
    brand: KnowledgeBrand,
    name: str,
    validated: bool,
    source: str | None,
) -> None:
    brand.canonical_name = name
    brand.display_name = name
    if validated:
        brand.is_validated = True
        brand.validation_source = source


def _new_brand(
    vertical_id: int,
    name: str,
    validated: bool,
    source: str | None,
) -> KnowledgeBrand:
    return KnowledgeBrand(
        vertical_id=vertical_id,
        canonical_name=name,
        display_name=name,
        is_validated=validated,
        validation_source=source,
    )


def _upsert_product(
    knowledge_db: Session,
    vertical_id: int,
    brand_id: int | None,
    name: str | None,
    validated: bool,
    source: str | None,
) -> KnowledgeProduct:
    clean = _clean_name(name)
    product = _find_product(knowledge_db, vertical_id, clean)
    return _save_product(
        knowledge_db, product, vertical_id, brand_id, clean, validated, source
    )


def _find_product(
    knowledge_db: Session,
    vertical_id: int,
    name: str,
) -> KnowledgeProduct | None:
    return (
        knowledge_db.query(KnowledgeProduct)
        .filter(
            KnowledgeProduct.vertical_id == vertical_id,
            func.lower(KnowledgeProduct.canonical_name) == name.casefold(),
        )
        .first()
    )


def _save_product(
    knowledge_db: Session,
    product: KnowledgeProduct | None,
    vertical_id: int,
    brand_id: int | None,
    name: str,
    validated: bool,
    source: str | None,
) -> KnowledgeProduct:
    if product:
        _set_product_fields(product, name, brand_id, validated, source)
        return product
    return _create_product(knowledge_db, vertical_id, brand_id, name, validated, source)


def _create_product(
    knowledge_db: Session,
    vertical_id: int,
    brand_id: int | None,
    name: str,
    validated: bool,
    source: str | None,
) -> KnowledgeProduct:
    product = _new_product(vertical_id, brand_id, name, validated, source)
    knowledge_db.add(product)
    knowledge_db.flush()
    return product


def _set_product_fields(
    product: KnowledgeProduct,
    name: str,
    brand_id: int | None,
    validated: bool,
    source: str | None,
) -> None:
    product.canonical_name = name
    product.display_name = name
    if brand_id:
        product.brand_id = brand_id
    if validated:
        product.is_validated = True
        product.validation_source = source


def _new_product(
    vertical_id: int,
    brand_id: int | None,
    name: str,
    validated: bool,
    source: str | None,
) -> KnowledgeProduct:
    return KnowledgeProduct(
        vertical_id=vertical_id,
        brand_id=brand_id,
        canonical_name=name,
        display_name=name,
        is_validated=validated,
        validation_source=source,
    )


def _upsert_rejected_entity(
    knowledge_db: Session,
    vertical_id: int,
    entity_type: EntityType,
    name: str | None,
    reason: str | None,
) -> KnowledgeRejectedEntity:
    clean = _clean_name(name)
    rejected = _find_rejected_entity(knowledge_db, vertical_id, entity_type, clean)
    if rejected:
        return _update_rejected(rejected, reason)
    return _create_rejected(knowledge_db, vertical_id, entity_type, clean, reason)


def _find_rejected_entity(
    knowledge_db: Session,
    vertical_id: int,
    entity_type: EntityType,
    name: str,
) -> KnowledgeRejectedEntity | None:
    return (
        knowledge_db.query(KnowledgeRejectedEntity)
        .filter(
            KnowledgeRejectedEntity.vertical_id == vertical_id,
            KnowledgeRejectedEntity.entity_type == entity_type,
            func.lower(KnowledgeRejectedEntity.name) == name.casefold(),
        )
        .first()
    )


def _update_rejected(
    rejected: KnowledgeRejectedEntity,
    reason: str | None,
) -> KnowledgeRejectedEntity:
    rejected.reason = reason or rejected.reason
    return rejected


def _create_rejected(
    knowledge_db: Session,
    vertical_id: int,
    entity_type: EntityType,
    name: str,
    reason: str | None,
) -> KnowledgeRejectedEntity:
    rejected = KnowledgeRejectedEntity(
        vertical_id=vertical_id,
        entity_type=entity_type,
        name=name,
        reason=reason or "user_reject",
    )
    knowledge_db.add(rejected)
    knowledge_db.flush()
    return rejected


def _upsert_mapping(
    knowledge_db: Session,
    vertical_id: int,
    product_id: int,
    brand_id: int,
    validated: bool,
    source: str | None,
) -> KnowledgeProductBrandMapping:
    mapping = _find_mapping(knowledge_db, vertical_id, product_id, brand_id)
    if mapping:
        return _update_mapping(mapping, validated, source)
    return _create_mapping(
        knowledge_db, vertical_id, product_id, brand_id, validated, source
    )


def _find_mapping(
    knowledge_db: Session,
    vertical_id: int,
    product_id: int,
    brand_id: int,
) -> KnowledgeProductBrandMapping | None:
    return (
        knowledge_db.query(KnowledgeProductBrandMapping)
        .filter(
            KnowledgeProductBrandMapping.vertical_id == vertical_id,
            KnowledgeProductBrandMapping.product_id == product_id,
            KnowledgeProductBrandMapping.brand_id == brand_id,
        )
        .first()
    )


def _update_mapping(
    mapping: KnowledgeProductBrandMapping,
    validated: bool,
    source: str | None,
) -> KnowledgeProductBrandMapping:
    mapping.is_validated = validated
    mapping.source = source
    return mapping


def _create_mapping(
    knowledge_db: Session,
    vertical_id: int,
    product_id: int,
    brand_id: int,
    validated: bool,
    source: str | None,
) -> KnowledgeProductBrandMapping:
    mapping = KnowledgeProductBrandMapping(
        vertical_id=vertical_id,
        product_id=product_id,
        brand_id=brand_id,
        is_validated=validated,
        source=source,
    )
    knowledge_db.add(mapping)
    knowledge_db.flush()
    return mapping


def _upsert_translation_override(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackTranslationOverrideItem,
) -> KnowledgeTranslationOverride:
    override = _find_translation_override(
        knowledge_db,
        vertical_id,
        item.entity_type,
        item.canonical_name,
        item.language.value,
    )
    if override:
        return _update_translation_override(override, item)
    return _create_translation_override(knowledge_db, vertical_id, item)


def _find_translation_override(
    knowledge_db: Session,
    vertical_id: int,
    entity_type: EntityType,
    canonical_name: str,
    language: str,
) -> KnowledgeTranslationOverride | None:
    return (
        knowledge_db.query(KnowledgeTranslationOverride)
        .filter(
            KnowledgeTranslationOverride.vertical_id == vertical_id,
            KnowledgeTranslationOverride.entity_type == entity_type,
            func.lower(KnowledgeTranslationOverride.canonical_name)
            == canonical_name.casefold(),
            KnowledgeTranslationOverride.language == language,
        )
        .first()
    )


def _update_translation_override(
    override: KnowledgeTranslationOverride,
    item: FeedbackTranslationOverrideItem,
) -> KnowledgeTranslationOverride:
    override.override_text = item.override_text
    override.reason = item.reason
    return override


def _create_translation_override(
    knowledge_db: Session,
    vertical_id: int,
    item: FeedbackTranslationOverrideItem,
) -> KnowledgeTranslationOverride:
    override = KnowledgeTranslationOverride(
        vertical_id=vertical_id,
        entity_type=item.entity_type,
        canonical_name=item.canonical_name,
        language=item.language.value,
        override_text=item.override_text,
        reason=item.reason,
    )
    knowledge_db.add(override)
    knowledge_db.flush()
    return override


def _store_feedback_event(
    knowledge_db: Session,
    vertical_id: int,
    payload: FeedbackSubmitRequest,
    reviewer: str,
    reviewer_model: str | None,
) -> None:
    knowledge_db.add(_new_feedback_event(vertical_id, payload, reviewer, reviewer_model))


def _new_feedback_event(
    vertical_id: int,
    payload: FeedbackSubmitRequest,
    reviewer: str,
    reviewer_model: str | None,
) -> KnowledgeFeedbackEvent:
    return KnowledgeFeedbackEvent(
        vertical_id=vertical_id,
        run_id=payload.run_id,
        reviewer=reviewer,
        reviewer_model=reviewer_model,
        status=FeedbackStatus.RECEIVED,
        payload=payload.model_dump(),
    )


def _response(
    run_id: int,
    vertical_id: int,
    applied: FeedbackAppliedSummary,
) -> FeedbackSubmitResponse:
    return FeedbackSubmitResponse(
        status="ok",
        run_id=run_id,
        canonical_vertical_id=vertical_id,
        applied=applied,
        warnings=[],
    )


def _clean_name(value: str | None) -> str:
    return (value or "").strip()


def _alias_variant_simple(wrong: str, correct: str) -> bool:
    if not wrong or not correct:
        return False
    return normalize_entity_key(wrong) == normalize_entity_key(correct)


def _alias_variant_brand(wrong: str, correct: str) -> bool:
    if _alias_variant_simple(wrong, correct):
        return True
    return normalize_entity_key(_strip_brand_suffix(wrong)) == normalize_entity_key(correct)


def _strip_brand_suffix(name: str) -> str:
    value = (name or "").strip()
    if not value:
        return ""
    return _strip_brand_suffix_pass(_strip_brand_suffix_pass(value))


def _strip_brand_suffix_pass(value: str) -> str:
    lowered = value.casefold().strip().strip(".")
    if lowered.endswith("汽车"):
        return value[: -len("汽车")].strip()
    if lowered.endswith("集团"):
        return value[: -len("集团")].strip()
    if lowered.endswith("公司"):
        return value[: -len("公司")].strip()
    if lowered.endswith("有限公司"):
        return value[: -len("有限公司")].strip()
    return _strip_en_suffix(value)


def _strip_en_suffix(value: str) -> str:
    parts = [p for p in (value or "").replace(".", " ").split() if p]
    if not parts:
        return ""
    suffixes = {"auto", "automotive", "group", "inc", "ltd", "co", "company", "corp", "holdings", "limited"}
    while parts and parts[-1].casefold() in suffixes:
        parts.pop()
    return " ".join(parts).strip()


def _add_knowledge_brand_alias(knowledge_db: Session, brand_id: int, alias: str) -> None:
    if not alias:
        return
    exists = knowledge_db.query(KnowledgeBrandAlias.id).filter(KnowledgeBrandAlias.brand_id == brand_id, func.lower(KnowledgeBrandAlias.alias) == alias.casefold()).first()
    if not exists:
        knowledge_db.add(KnowledgeBrandAlias(brand_id=brand_id, alias=alias))


def _add_knowledge_product_alias(knowledge_db: Session, product_id: int, alias: str) -> None:
    if not alias:
        return
    exists = knowledge_db.query(KnowledgeProductAlias.id).filter(KnowledgeProductAlias.product_id == product_id, func.lower(KnowledgeProductAlias.alias) == alias.casefold()).first()
    if not exists:
        knowledge_db.add(KnowledgeProductAlias(product_id=product_id, alias=alias))


def _delete_rejected(knowledge_db: Session, vertical_id: int, entity_type: EntityType, name: str) -> None:
    if not name:
        return
    knowledge_db.query(KnowledgeRejectedEntity).filter(
        KnowledgeRejectedEntity.vertical_id == vertical_id,
        KnowledgeRejectedEntity.entity_type == entity_type,
        func.lower(KnowledgeRejectedEntity.name) == name.casefold(),
    ).delete(synchronize_session=False)
