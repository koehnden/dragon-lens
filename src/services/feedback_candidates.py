from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    Brand,
    BrandMention,
    LLMAnswer,
    Product,
    ProductBrandMapping,
    ProductMention,
    Run,
    RunStatus,
    Vertical,
)
from models.domain import EntityType
from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeProduct,
    KnowledgeProductBrandMapping,
    KnowledgeRejectedEntity,
    KnowledgeTranslationOverride,
    KnowledgeVertical,
    KnowledgeVerticalAlias,
)
from models.schemas import (
    FeedbackCandidateBrand,
    FeedbackCandidateMapping,
    FeedbackCandidateMissingMapping,
    FeedbackCandidateProduct,
    FeedbackCandidateTranslation,
    FeedbackCandidatesResponse,
    FeedbackEntityType,
)
from services.knowledge_verticals import resolve_knowledge_vertical_id
from services.translater import has_chinese_characters, has_latin_letters


def feedback_candidates(
    db: Session,
    knowledge_db: Session,
    vertical_id: int,
) -> FeedbackCandidatesResponse:
    vertical = _vertical_or_404(db, vertical_id)
    knowledge_vertical_id = _knowledge_vertical_id(knowledge_db, vertical.name)
    group_vertical_ids = _group_vertical_ids(db, knowledge_db, vertical, knowledge_vertical_id)
    run_id = _latest_completed_run_id(db, group_vertical_ids)
    return FeedbackCandidatesResponse(
        group_vertical_ids=group_vertical_ids,
        vertical_id=vertical_id,
        vertical_name=vertical.name,
        latest_completed_run_id=run_id,
        resolved_canonical_vertical_id=knowledge_vertical_id,
        resolved_canonical_vertical_name=_knowledge_vertical_name(knowledge_db, knowledge_vertical_id),
        brands=_brand_candidates(db, knowledge_db, group_vertical_ids, knowledge_vertical_id),
        products=_product_candidates(db, knowledge_db, group_vertical_ids, knowledge_vertical_id),
        mappings=_mapping_candidates(db, knowledge_db, group_vertical_ids, knowledge_vertical_id),
        missing_mappings=_missing_mapping_candidates(db, knowledge_db, group_vertical_ids, knowledge_vertical_id),
        translations=_translation_candidates(db, knowledge_db, group_vertical_ids, knowledge_vertical_id),
    )


def _vertical_or_404(db: Session, vertical_id: int) -> Vertical:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail="Vertical not found")
    return vertical


def _latest_completed_run_id(db: Session, vertical_ids: list[int]) -> Optional[int]:
    if not vertical_ids:
        return None
    run = db.query(Run).filter(Run.vertical_id.in_(vertical_ids), Run.status == RunStatus.COMPLETED).order_by(
        Run.run_time.desc()
    ).first()
    return int(run.id) if run else None


def _knowledge_vertical_id(knowledge_db: Session, vertical_name: str) -> Optional[int]:
    return resolve_knowledge_vertical_id(knowledge_db, vertical_name) if vertical_name else None


def _knowledge_vertical_name(knowledge_db: Session, vertical_id: Optional[int]) -> Optional[str]:
    if not vertical_id:
        return None
    row = knowledge_db.query(KnowledgeVertical).filter(KnowledgeVertical.id == vertical_id).first()
    return row.name if row else None


def _group_vertical_ids(
    db: Session,
    knowledge_db: Session,
    vertical: Vertical,
    knowledge_vertical_id: Optional[int],
) -> list[int]:
    if not knowledge_vertical_id:
        return [int(vertical.id)]
    names = _group_vertical_names(knowledge_db, knowledge_vertical_id)
    ids = _local_vertical_ids(db, names)
    return ids or [int(vertical.id)]


def _group_vertical_names(knowledge_db: Session, vertical_id: int) -> list[str]:
    canonical = _knowledge_vertical_name(knowledge_db, vertical_id) or ""
    aliases = knowledge_db.query(KnowledgeVerticalAlias.alias).filter(KnowledgeVerticalAlias.vertical_id == vertical_id).all()
    return [canonical] + [a for (a,) in aliases if a]


def _local_vertical_ids(db: Session, names: list[str]) -> list[int]:
    cleaned = [n.strip() for n in names if n and n.strip()]
    if not cleaned:
        return []
    lowered = [n.casefold() for n in cleaned]
    rows = db.query(Vertical.id).filter(func.lower(Vertical.name).in_(lowered)).all()
    return [int(r[0]) for r in rows]


def _brand_counts(db: Session, vertical_ids: list[int]) -> dict[int, int]:
    if not vertical_ids:
        return {}
    rows = db.query(BrandMention.brand_id, func.count(BrandMention.id)).join(
        LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id
    ).join(
        Run, Run.id == LLMAnswer.run_id
    ).filter(
        Run.vertical_id.in_(vertical_ids), Run.status == RunStatus.COMPLETED, BrandMention.mentioned
    ).group_by(BrandMention.brand_id).all()
    return {int(brand_id): int(count) for brand_id, count in rows}


def _product_counts(db: Session, vertical_ids: list[int]) -> dict[int, int]:
    if not vertical_ids:
        return {}
    rows = db.query(ProductMention.product_id, func.count(ProductMention.id)).join(
        LLMAnswer, LLMAnswer.id == ProductMention.llm_answer_id
    ).join(
        Run, Run.id == LLMAnswer.run_id
    ).filter(
        Run.vertical_id.in_(vertical_ids), Run.status == RunStatus.COMPLETED, ProductMention.mentioned
    ).group_by(ProductMention.product_id).all()
    return {int(product_id): int(count) for product_id, count in rows}


def _brand_candidates(
    db: Session,
    knowledge_db: Session,
    vertical_ids: list[int],
    knowledge_vertical_id: Optional[int],
) -> list[FeedbackCandidateBrand]:
    counts = _brand_counts(db, vertical_ids)
    brands = _brands_for_ids(db, set(counts.keys()))
    items = [_brand_candidate(b, counts.get(b.id, 0)) for b in brands if _candidate_name(b.original_name)]
    return _filter_brands(knowledge_db, knowledge_vertical_id, items)


def _product_candidates(
    db: Session,
    knowledge_db: Session,
    vertical_ids: list[int],
    knowledge_vertical_id: Optional[int],
) -> list[FeedbackCandidateProduct]:
    counts = _product_counts(db, vertical_ids)
    products = _products_for_ids(db, set(counts.keys()))
    items = [_product_candidate(p, counts.get(p.id, 0)) for p in products if _candidate_name(p.original_name)]
    return _filter_products(knowledge_db, knowledge_vertical_id, items)


def _brands_for_ids(db: Session, ids: set[int]) -> list[Brand]:
    return db.query(Brand).filter(Brand.id.in_(ids)).all() if ids else []


def _products_for_ids(db: Session, ids: set[int]) -> list[Product]:
    return db.query(Product).filter(Product.id.in_(ids)).all() if ids else []


def _candidate_name(value: str | None) -> str:
    return (value or "").strip()


def _brand_candidate(brand: Brand, count: int) -> FeedbackCandidateBrand:
    return FeedbackCandidateBrand(name=brand.original_name.strip(), translated_name=brand.translated_name, mention_count=count)


def _product_candidate(product: Product, count: int) -> FeedbackCandidateProduct:
    brand = db_brand_name(product)
    return FeedbackCandidateProduct(
        name=product.original_name.strip(),
        translated_name=product.translated_name,
        brand_name=brand,
        mention_count=count,
    )


def db_brand_name(product: Product) -> Optional[str]:
    brand = getattr(product, "brand", None)
    if not brand:
        return None
    return (brand.original_name or "").strip() or None


def _filter_brands(
    knowledge_db: Session,
    knowledge_vertical_id: Optional[int],
    items: list[FeedbackCandidateBrand],
) -> list[FeedbackCandidateBrand]:
    resolved = _resolved_entity_names(knowledge_db, knowledge_vertical_id, EntityType.BRAND)
    return [item for item in items if item.name.casefold() not in resolved]


def _filter_products(
    knowledge_db: Session,
    knowledge_vertical_id: Optional[int],
    items: list[FeedbackCandidateProduct],
) -> list[FeedbackCandidateProduct]:
    resolved = _resolved_entity_names(knowledge_db, knowledge_vertical_id, EntityType.PRODUCT)
    return [item for item in items if item.name.casefold() not in resolved]


def _resolved_entity_names(knowledge_db: Session, vertical_id: Optional[int], entity_type: EntityType) -> set[str]:
    if not vertical_id:
        return set()
    validated = _validated_names(knowledge_db, vertical_id, entity_type)
    rejected = _rejected_names(knowledge_db, vertical_id, entity_type)
    return validated | rejected


def _validated_names(knowledge_db: Session, vertical_id: int, entity_type: EntityType) -> set[str]:
    model = KnowledgeBrand if entity_type == EntityType.BRAND else KnowledgeProduct
    rows = knowledge_db.query(model.canonical_name).filter(model.vertical_id == vertical_id, model.is_validated.is_(True)).all()
    return {str(name).casefold() for (name,) in rows if name}


def _rejected_names(knowledge_db: Session, vertical_id: int, entity_type: EntityType) -> set[str]:
    rows = knowledge_db.query(KnowledgeRejectedEntity.name).filter(
        KnowledgeRejectedEntity.vertical_id == vertical_id, KnowledgeRejectedEntity.entity_type == entity_type
    ).all()
    return {str(name).casefold() for (name,) in rows if name}


def _mapping_candidates(
    db: Session,
    knowledge_db: Session,
    vertical_ids: list[int],
    knowledge_vertical_id: Optional[int],
) -> list[FeedbackCandidateMapping]:
    product_ids = set(_product_counts(db, vertical_ids).keys())
    rows = _local_mapping_rows(db, vertical_ids, product_ids)
    items = [_mapping_candidate(row) for row in rows if _mapping_candidate(row)]
    return _filter_mappings(knowledge_db, knowledge_vertical_id, items)


def _local_mapping_rows(db: Session, vertical_ids: list[int], product_ids: set[int]):
    if not product_ids:
        return []
    return db.query(ProductBrandMapping, Product, Brand).join(
        Product, Product.id == ProductBrandMapping.product_id
    ).join(
        Brand, Brand.id == ProductBrandMapping.brand_id
    ).filter(
        ProductBrandMapping.vertical_id.in_(vertical_ids), ProductBrandMapping.product_id.in_(product_ids)
    ).all()


def _mapping_candidate(row) -> Optional[FeedbackCandidateMapping]:
    mapping, product, brand = row
    product_name = _candidate_name(product.original_name)
    brand_name = _candidate_name(brand.original_name)
    if not product_name or not brand_name:
        return None
    return FeedbackCandidateMapping(
        product_name=product_name,
        brand_name=brand_name,
        confidence=float(mapping.confidence) if mapping.confidence is not None else None,
        source=mapping.source,
    )


def _filter_mappings(
    knowledge_db: Session,
    knowledge_vertical_id: Optional[int],
    items: list[FeedbackCandidateMapping],
) -> list[FeedbackCandidateMapping]:
    resolved = _resolved_mapping_pairs(knowledge_db, knowledge_vertical_id)
    return [item for item in items if (item.product_name.casefold(), item.brand_name.casefold()) not in resolved]


def _resolved_mapping_pairs(knowledge_db: Session, vertical_id: Optional[int]) -> set[tuple[str, str]]:
    if not vertical_id:
        return set()
    rows = knowledge_db.query(KnowledgeProduct.canonical_name, KnowledgeBrand.canonical_name).join(
        KnowledgeProductBrandMapping, KnowledgeProductBrandMapping.product_id == KnowledgeProduct.id
    ).join(
        KnowledgeBrand, KnowledgeBrand.id == KnowledgeProductBrandMapping.brand_id
    ).filter(
        KnowledgeProductBrandMapping.vertical_id == vertical_id
    ).all()
    return {(p.casefold(), b.casefold()) for (p, b) in rows if p and b}


def _missing_mapping_candidates(
    db: Session,
    knowledge_db: Session,
    vertical_ids: list[int],
    knowledge_vertical_id: Optional[int],
) -> list[FeedbackCandidateMissingMapping]:
    products = _products_for_ids(db, set(_product_counts(db, vertical_ids).keys()))
    missing = [_missing_mapping_candidate(db, int(product.vertical_id), product) for product in products]
    items = [item for item in missing if item]
    return _filter_missing_mappings(knowledge_db, knowledge_vertical_id, items)


def _missing_mapping_candidate(db: Session, vertical_id: int, product: Product) -> Optional[FeedbackCandidateMissingMapping]:
    if _has_local_mapping(db, vertical_id, product.id):
        return None
    name = _candidate_name(product.original_name)
    return FeedbackCandidateMissingMapping(product_name=name) if name else None


def _has_local_mapping(db: Session, vertical_id: int, product_id: int) -> bool:
    row = db.query(ProductBrandMapping.id).filter(
        ProductBrandMapping.vertical_id == vertical_id, ProductBrandMapping.product_id == product_id
    ).first()
    return bool(row)


def _filter_missing_mappings(
    knowledge_db: Session,
    knowledge_vertical_id: Optional[int],
    items: list[FeedbackCandidateMissingMapping],
) -> list[FeedbackCandidateMissingMapping]:
    resolved_products = _resolved_product_names_for_mapping(knowledge_db, knowledge_vertical_id)
    return [item for item in items if item.product_name.casefold() not in resolved_products]


def _resolved_product_names_for_mapping(knowledge_db: Session, vertical_id: Optional[int]) -> set[str]:
    if not vertical_id:
        return set()
    rows = knowledge_db.query(KnowledgeProduct.canonical_name).join(
        KnowledgeProductBrandMapping, KnowledgeProductBrandMapping.product_id == KnowledgeProduct.id
    ).filter(
        KnowledgeProductBrandMapping.vertical_id == vertical_id
    ).all()
    return {str(name).casefold() for (name,) in rows if name}


def _translation_candidates(
    db: Session,
    knowledge_db: Session,
    vertical_ids: list[int],
    knowledge_vertical_id: Optional[int],
) -> list[FeedbackCandidateTranslation]:
    brand_counts = _brand_counts(db, vertical_ids)
    product_counts = _product_counts(db, vertical_ids)
    brands = _brands_for_ids(db, set(brand_counts.keys()))
    products = _products_for_ids(db, set(product_counts.keys()))
    items = _translation_items(brands, products, brand_counts, product_counts)
    return _filter_translations(knowledge_db, knowledge_vertical_id, items)


def _translation_items(
    brands: list[Brand],
    products: list[Product],
    brand_counts: dict[int, int],
    product_counts: dict[int, int],
) -> list[FeedbackCandidateTranslation]:
    result = [_translation_brand_item(b, brand_counts.get(b.id, 0)) for b in brands]
    result.extend([_translation_product_item(p, product_counts.get(p.id, 0)) for p in products])
    return [item for item in result if item]


def _translation_brand_item(brand: Brand, count: int) -> Optional[FeedbackCandidateTranslation]:
    name = _candidate_name(brand.original_name)
    if not _needs_english(name):
        return None
    return FeedbackCandidateTranslation(
        entity_type=FeedbackEntityType.BRAND,
        canonical_name=name,
        current_translation_en=(brand.translated_name or "").strip() or None,
        mention_count=count,
    )


def _translation_product_item(product: Product, count: int) -> Optional[FeedbackCandidateTranslation]:
    name = _candidate_name(product.original_name)
    if not _needs_english(name):
        return None
    return FeedbackCandidateTranslation(
        entity_type=FeedbackEntityType.PRODUCT,
        canonical_name=name,
        current_translation_en=(product.translated_name or "").strip() or None,
        mention_count=count,
    )


def _needs_english(name: str) -> bool:
    if not has_chinese_characters(name):
        return False
    return not has_latin_letters(name)


def _filter_translations(
    knowledge_db: Session,
    knowledge_vertical_id: Optional[int],
    items: list[FeedbackCandidateTranslation],
) -> list[FeedbackCandidateTranslation]:
    resolved = _resolved_translation_keys(knowledge_db, knowledge_vertical_id)
    return [item for item in items if _translation_key(item) not in resolved]


def _translation_key(item: FeedbackCandidateTranslation) -> tuple[str, str]:
    return (item.entity_type.value, item.canonical_name.casefold())


def _resolved_translation_keys(knowledge_db: Session, vertical_id: Optional[int]) -> set[tuple[str, str]]:
    if not vertical_id:
        return set()
    rows = knowledge_db.query(KnowledgeTranslationOverride.entity_type, KnowledgeTranslationOverride.canonical_name).filter(
        KnowledgeTranslationOverride.vertical_id == vertical_id, KnowledgeTranslationOverride.language == "en"
    ).all()
    return {(et.value, name.casefold()) for (et, name) in rows if et and name}
