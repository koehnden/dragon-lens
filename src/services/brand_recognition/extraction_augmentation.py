"""
Extraction augmentation with validated entities and previous mistakes.

This module provides functions to fetch validated brands/products and
previous rejection mistakes to augment the extraction prompt for
improved accuracy over time.
"""

import logging
from typing import Dict, List, Set, Tuple

from sqlalchemy.orm import Session

from models import EntityType, Vertical
from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeRejectedEntity,
)
from services.canonicalization_metrics import build_user_brand_variant_set
from services.knowledge_session import knowledge_session
from services.knowledge_verticals import resolve_knowledge_vertical_id

logger = logging.getLogger(__name__)

POSITIVE_EXAMPLES_LIMIT = 20
NEGATIVE_EXAMPLES_LIMIT = 100


def get_validated_brands_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = POSITIVE_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get validated brands to include as positive examples in extraction prompt."""
    return _validated_brands_for_prompt(db, vertical_id, limit)


def get_validated_products_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = POSITIVE_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get validated products to include as positive examples in extraction prompt."""
    return _validated_products_for_prompt(db, vertical_id, limit)


def get_rejected_brands_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = NEGATIVE_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get rejected brands to include as negative examples in extraction prompt."""
    return _rejected_entities_for_prompt(db, vertical_id, EntityType.BRAND, limit)


def get_rejected_products_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = NEGATIVE_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get rejected products to include as negative examples in extraction prompt."""
    return _rejected_entities_for_prompt(db, vertical_id, EntityType.PRODUCT, limit)


def get_validated_entity_names(
    db: Session,
    vertical_id: int,
) -> Tuple[Set[str], Set[str]]:
    """Get sets of validated brand and product names for bypass checking.

    Returns:
        Tuple of (validated_brand_names, validated_product_names) as lowercase sets
    """
    return _validated_entity_names(db, vertical_id)


def get_augmentation_context(
    db: Session,
    vertical_id: int,
) -> Dict:
    """Get all augmentation data for extraction prompt.

    Returns dict with:
        - validated_brands: List of validated brand dicts
        - validated_products: List of validated product dicts
        - rejected_brands: List of rejected brand dicts
        - rejected_products: List of rejected product dicts
    """
    return _augmentation_context(db, vertical_id)


def _get_brand_aliases(db: Session, brand_id: int) -> List[str]:
    aliases = db.query(KnowledgeBrandAlias.alias).filter(
        KnowledgeBrandAlias.brand_id == brand_id
    ).all()
    return [alias for (alias,) in aliases]


def _get_product_aliases(db: Session, product_id: int) -> List[str]:
    aliases = db.query(KnowledgeProductAlias.alias).filter(
        KnowledgeProductAlias.product_id == product_id
    ).all()
    return [alias for (alias,) in aliases]


def _get_all_brand_aliases(db: Session, vertical_id: int) -> Set[str]:
    brand_ids = _validated_brand_ids(db, vertical_id)
    if not brand_ids:
        return set()
    aliases = db.query(KnowledgeBrandAlias.alias).filter(
        KnowledgeBrandAlias.brand_id.in_(brand_ids)
    ).all()
    return _alias_set(aliases)


def _get_all_product_aliases(db: Session, vertical_id: int) -> Set[str]:
    product_ids = _validated_product_ids(db, vertical_id)
    if not product_ids:
        return set()
    aliases = db.query(KnowledgeProductAlias.alias).filter(
        KnowledgeProductAlias.product_id.in_(product_ids)
    ).all()
    return _alias_set(aliases)


def _simplify_rejection_reason(reason: str) -> str:
    """Simplify rejection reason for display in prompt."""
    reason_map = {
        "light_filter": "generic term or too short",
        "rejected_at_light_filter": "generic term or too short",
        "rejected_at_normalization": "not a valid brand",
        "rejected_at_validation": "not a valid product",
        "rejected_at_list_filter": "not in primary position",
        "off_vertical": "off-vertical entity",
        "user_rejected": "manually rejected",
        "user_reject": "manually rejected",
    }
    return reason_map.get(reason, reason)


def get_canonical_for_validated_brand(
    db: Session,
    brand_name: str,
    vertical_id: int,
) -> str:
    """Get the canonical name for a validated brand."""
    return _canonical_for_validated_brand(db, brand_name, vertical_id)


def get_canonical_for_validated_product(
    db: Session,
    product_name: str,
    vertical_id: int,
) -> str:
    """Get the canonical name for a validated product."""
    return _canonical_for_validated_product(db, product_name, vertical_id)


def _validated_brands_for_prompt(db: Session, vertical_id: int, limit: int) -> List[Dict]:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        if not knowledge_id:
            return []
        return [_brand_prompt_entry(knowledge_db, b) for b in _validated_brands(knowledge_db, knowledge_id, limit)]


def _validated_products_for_prompt(db: Session, vertical_id: int, limit: int) -> List[Dict]:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        if not knowledge_id:
            return []
        return [_product_prompt_entry(knowledge_db, p) for p in _validated_products(knowledge_db, knowledge_id, limit)]


def _rejected_entities_for_prompt(
    db: Session,
    vertical_id: int,
    entity_type: EntityType,
    limit: int,
) -> List[Dict]:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        if not knowledge_id:
            return []
        rejected = _rejected_entities(knowledge_db, knowledge_id, entity_type, limit)
        return [_rejected_payload(entity) for entity in rejected]


def _validated_entity_names(db: Session, vertical_id: int) -> Tuple[Set[str], Set[str]]:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        return _name_sets(db, knowledge_db, knowledge_id, vertical_id)


def _augmentation_context(db: Session, vertical_id: int) -> Dict:
    return {
        "validated_brands": get_validated_brands_for_prompt(db, vertical_id),
        "validated_products": get_validated_products_for_prompt(db, vertical_id),
        "rejected_brands": get_rejected_brands_for_prompt(db, vertical_id),
        "rejected_products": get_rejected_products_for_prompt(db, vertical_id),
    }


def _knowledge_vertical_id(knowledge_db: Session, db: Session, vertical_id: int) -> int | None:
    name = _vertical_name(db, vertical_id)
    if not name:
        return None
    return resolve_knowledge_vertical_id(knowledge_db, name)


def _vertical_name(db: Session, vertical_id: int) -> str:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    return vertical.name if vertical else ""


def _validated_brands(knowledge_db: Session, vertical_id: int, limit: int) -> List[KnowledgeBrand]:
    return knowledge_db.query(KnowledgeBrand).filter(
        KnowledgeBrand.vertical_id == vertical_id,
        KnowledgeBrand.is_validated == True,
    ).order_by(KnowledgeBrand.updated_at.desc()).limit(limit).all()


def _validated_products(knowledge_db: Session, vertical_id: int, limit: int) -> List[KnowledgeProduct]:
    return knowledge_db.query(KnowledgeProduct).filter(
        KnowledgeProduct.vertical_id == vertical_id,
        KnowledgeProduct.is_validated == True,
    ).order_by(KnowledgeProduct.updated_at.desc()).limit(limit).all()


def _brand_prompt_entry(knowledge_db: Session, brand: KnowledgeBrand) -> Dict:
    return {
        "canonical_name": brand.canonical_name,
        "display_name": brand.display_name,
        "aliases": _get_brand_aliases(knowledge_db, brand.id),
    }


def _product_prompt_entry(knowledge_db: Session, product: KnowledgeProduct) -> Dict:
    return {
        "canonical_name": product.canonical_name,
        "display_name": product.display_name,
        "aliases": _get_product_aliases(knowledge_db, product.id),
    }


def _rejected_entities(
    knowledge_db: Session,
    vertical_id: int,
    entity_type: EntityType,
    limit: int,
) -> List[KnowledgeRejectedEntity]:
    return knowledge_db.query(KnowledgeRejectedEntity).filter(
        KnowledgeRejectedEntity.vertical_id == vertical_id,
        KnowledgeRejectedEntity.entity_type == entity_type,
    ).order_by(KnowledgeRejectedEntity.created_at.desc()).limit(limit).all()


def _rejected_payload(entity: KnowledgeRejectedEntity) -> Dict:
    return {"name": entity.name, "reason": _simplify_rejection_reason(entity.reason)}


def _name_sets(
    db: Session,
    knowledge_db: Session,
    knowledge_vertical_id: int | None,
    vertical_id: int,
) -> Tuple[Set[str], Set[str]]:
    if not knowledge_vertical_id:
        return build_user_brand_variant_set(db, vertical_id), set()
    brand_names = _validated_name_set(knowledge_db, knowledge_vertical_id, KnowledgeBrand)
    product_names = _validated_name_set(knowledge_db, knowledge_vertical_id, KnowledgeProduct)
    brand_names.update(_get_all_brand_aliases(knowledge_db, knowledge_vertical_id))
    product_names.update(_get_all_product_aliases(knowledge_db, knowledge_vertical_id))
    brand_names.update(build_user_brand_variant_set(db, vertical_id))
    return brand_names, product_names


def _validated_name_set(knowledge_db: Session, vertical_id: int, model) -> Set[str]:
    rows = knowledge_db.query(model.canonical_name).filter(
        model.vertical_id == vertical_id,
        model.is_validated == True,
    ).all()
    return _name_set(rows)


def _name_set(rows: List[Tuple[str]]) -> Set[str]:
    result: Set[str] = set()
    for (name,) in rows:
        result.add(name.lower())
        result.add(name)
    return result


def _validated_brand_ids(db: Session, vertical_id: int) -> List[int]:
    return _validated_ids(db, vertical_id, KnowledgeBrand)


def _validated_product_ids(db: Session, vertical_id: int) -> List[int]:
    return _validated_ids(db, vertical_id, KnowledgeProduct)


def _validated_ids(db: Session, vertical_id: int, model) -> List[int]:
    rows = db.query(model.id).filter(
        model.vertical_id == vertical_id,
        model.is_validated == True,
    ).all()
    return [row[0] for row in rows]


def _alias_set(rows: List[Tuple[str]]) -> Set[str]:
    result: Set[str] = set()
    for (alias,) in rows:
        result.add(alias.lower())
        result.add(alias)
    return result


def _canonical_for_validated_brand(db: Session, brand_name: str, vertical_id: int) -> str:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        return _canonical_name_for_entity(
            knowledge_db, knowledge_id, KnowledgeBrand, KnowledgeBrandAlias, brand_name
        )


def _canonical_for_validated_product(db: Session, product_name: str, vertical_id: int) -> str:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        return _canonical_name_for_entity(
            knowledge_db, knowledge_id, KnowledgeProduct, KnowledgeProductAlias, product_name
        )


def _canonical_name_for_entity(
    knowledge_db: Session,
    knowledge_vertical_id: int | None,
    model,
    alias_model,
    name: str,
) -> str:
    if not knowledge_vertical_id:
        return name
    canonical = _find_canonical(knowledge_db, knowledge_vertical_id, model, name)
    if canonical:
        return canonical.canonical_name
    alias = _find_alias_canonical(knowledge_db, knowledge_vertical_id, model, alias_model, name)
    return alias.canonical_name if alias else name


def _find_canonical(knowledge_db: Session, vertical_id: int, model, name: str):
    from sqlalchemy import func

    return knowledge_db.query(model).filter(
        model.vertical_id == vertical_id,
        model.is_validated == True,
        func.lower(model.canonical_name) == name.casefold(),
    ).first()


def _find_alias_canonical(
    knowledge_db: Session,
    vertical_id: int,
    model,
    alias_model,
    name: str,
):
    from sqlalchemy import func

    return knowledge_db.query(model).join(alias_model).filter(
        model.vertical_id == vertical_id,
        model.is_validated == True,
        func.lower(alias_model.alias) == name.casefold(),
    ).first()
