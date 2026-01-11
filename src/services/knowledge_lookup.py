from typing import Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeProductBrandMapping,
)
from services.knowledge_session import knowledge_session
from services.knowledge_verticals import normalize_entity_key, resolve_knowledge_vertical_id


def lookup_product_brand(product_name: str, vertical_name: str) -> Optional[str]:
    with knowledge_session(write=False) as db:
        vertical_id = resolve_knowledge_vertical_id(db, vertical_name)
        if not vertical_id:
            return None
        return _lookup_brand_for_product(db, vertical_id, product_name)


def build_mapping_cache(vertical_name: str) -> Dict[str, str]:
    with knowledge_session(write=False) as db:
        vertical_id = resolve_knowledge_vertical_id(db, vertical_name)
        if not vertical_id:
            return {}
        return _build_cache_for_vertical(db, vertical_id)


def _lookup_brand_for_product(
    db: Session,
    vertical_id: int,
    product_name: str,
) -> Optional[str]:
    product_key = normalize_entity_key(product_name)
    mapping = _find_mapping_by_product_key(db, vertical_id, product_key)
    if mapping and mapping.brand:
        return mapping.brand.display_name
    return None


def _find_mapping_by_product_key(
    db: Session,
    vertical_id: int,
    product_key: str,
) -> Optional[KnowledgeProductBrandMapping]:
    product = _find_product_by_key(db, vertical_id, product_key)
    if not product:
        return None
    return _find_mapping_for_product(db, vertical_id, product.id)


def _find_product_by_key(
    db: Session,
    vertical_id: int,
    product_key: str,
) -> Optional[KnowledgeProduct]:
    product = db.query(KnowledgeProduct).filter(
        KnowledgeProduct.vertical_id == vertical_id,
        func.lower(KnowledgeProduct.canonical_name) == product_key,
    ).first()
    if product:
        return product

    alias = db.query(KnowledgeProductAlias).join(KnowledgeProduct).filter(
        KnowledgeProduct.vertical_id == vertical_id,
        func.lower(KnowledgeProductAlias.alias) == product_key,
    ).first()
    if alias:
        return alias.product

    return None


def _find_mapping_for_product(
    db: Session,
    vertical_id: int,
    product_id: int,
) -> Optional[KnowledgeProductBrandMapping]:
    return db.query(KnowledgeProductBrandMapping).filter(
        KnowledgeProductBrandMapping.vertical_id == vertical_id,
        KnowledgeProductBrandMapping.product_id == product_id,
    ).first()


def _build_cache_for_vertical(db: Session, vertical_id: int) -> Dict[str, str]:
    cache: Dict[str, str] = {}
    mappings = _load_all_mappings(db, vertical_id)

    for mapping in mappings:
        brand_name = mapping.brand.display_name if mapping.brand else None
        if not brand_name:
            continue

        product = mapping.product
        if product:
            _add_product_to_cache(cache, product, brand_name)

    return cache


def _load_all_mappings(
    db: Session,
    vertical_id: int,
) -> list[KnowledgeProductBrandMapping]:
    return db.query(KnowledgeProductBrandMapping).filter(
        KnowledgeProductBrandMapping.vertical_id == vertical_id,
    ).all()


def _add_product_to_cache(
    cache: Dict[str, str],
    product: KnowledgeProduct,
    brand_name: str,
) -> None:
    cache[product.canonical_name.lower()] = brand_name
    cache[product.display_name.lower()] = brand_name

    for alias in product.aliases:
        cache[alias.alias.lower()] = brand_name
