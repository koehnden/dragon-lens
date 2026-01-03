"""
Extraction augmentation with validated entities and previous mistakes.

This module provides functions to fetch validated brands/products and
previous rejection mistakes to augment the extraction prompt for
improved accuracy over time.
"""

import logging
from typing import Dict, List, Set, Tuple

from sqlalchemy.orm import Session

from models import (
    BrandAlias,
    CanonicalBrand,
    CanonicalProduct,
    EntityType,
    ProductAlias,
    RejectedEntity,
)
from services.canonicalization_metrics import build_user_brand_variant_set

logger = logging.getLogger(__name__)

POSITIVE_EXAMPLES_LIMIT = 20
NEGATIVE_EXAMPLES_LIMIT = 100


def get_validated_brands_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = POSITIVE_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get validated brands to include as positive examples in extraction prompt."""
    brands = db.query(CanonicalBrand).filter(
        CanonicalBrand.vertical_id == vertical_id,
        CanonicalBrand.is_validated == True,
    ).order_by(CanonicalBrand.mention_count.desc()).limit(limit).all()

    result = []
    for brand in brands:
        aliases = _get_brand_aliases(db, brand.id)
        result.append({
            "canonical_name": brand.canonical_name,
            "display_name": brand.display_name,
            "aliases": aliases,
        })

    logger.debug(f"Found {len(result)} validated brands for prompt augmentation")
    return result


def get_validated_products_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = POSITIVE_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get validated products to include as positive examples in extraction prompt."""
    products = db.query(CanonicalProduct).filter(
        CanonicalProduct.vertical_id == vertical_id,
        CanonicalProduct.is_validated == True,
    ).order_by(CanonicalProduct.mention_count.desc()).limit(limit).all()

    result = []
    for product in products:
        aliases = _get_product_aliases(db, product.id)
        result.append({
            "canonical_name": product.canonical_name,
            "display_name": product.display_name,
            "aliases": aliases,
        })

    logger.debug(f"Found {len(result)} validated products for prompt augmentation")
    return result


def get_rejected_brands_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = NEGATIVE_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get rejected brands to include as negative examples in extraction prompt."""
    rejected = db.query(RejectedEntity).filter(
        RejectedEntity.vertical_id == vertical_id,
        RejectedEntity.entity_type == EntityType.BRAND,
    ).order_by(RejectedEntity.created_at.desc()).limit(limit).all()

    result = []
    for entity in rejected:
        result.append({
            "name": entity.name,
            "reason": _simplify_rejection_reason(entity.rejection_reason),
        })

    logger.debug(f"Found {len(result)} rejected brands for prompt augmentation")
    return result


def get_rejected_products_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = NEGATIVE_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get rejected products to include as negative examples in extraction prompt."""
    rejected = db.query(RejectedEntity).filter(
        RejectedEntity.vertical_id == vertical_id,
        RejectedEntity.entity_type == EntityType.PRODUCT,
    ).order_by(RejectedEntity.created_at.desc()).limit(limit).all()

    result = []
    for entity in rejected:
        result.append({
            "name": entity.name,
            "reason": _simplify_rejection_reason(entity.rejection_reason),
        })

    logger.debug(f"Found {len(result)} rejected products for prompt augmentation")
    return result


def get_validated_entity_names(
    db: Session,
    vertical_id: int,
) -> Tuple[Set[str], Set[str]]:
    """Get sets of validated brand and product names for bypass checking.

    Returns:
        Tuple of (validated_brand_names, validated_product_names) as lowercase sets
    """
    validated_brands = db.query(CanonicalBrand.canonical_name).filter(
        CanonicalBrand.vertical_id == vertical_id,
        CanonicalBrand.is_validated == True,
    ).all()

    validated_products = db.query(CanonicalProduct.canonical_name).filter(
        CanonicalProduct.vertical_id == vertical_id,
        CanonicalProduct.is_validated == True,
    ).all()

    brand_names: Set[str] = set()
    for (name,) in validated_brands:
        brand_names.add(name.lower())
        brand_names.add(name)

    product_names: Set[str] = set()
    for (name,) in validated_products:
        product_names.add(name.lower())
        product_names.add(name)

    brand_aliases = _get_all_brand_aliases(db, vertical_id)
    product_aliases = _get_all_product_aliases(db, vertical_id)

    brand_names.update(brand_aliases)
    brand_names.update(build_user_brand_variant_set(db, vertical_id))
    product_names.update(product_aliases)

    logger.debug(
        f"Loaded {len(brand_names)} validated brand names, "
        f"{len(product_names)} validated product names for bypass checking"
    )

    return brand_names, product_names


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
    return {
        "validated_brands": get_validated_brands_for_prompt(db, vertical_id),
        "validated_products": get_validated_products_for_prompt(db, vertical_id),
        "rejected_brands": get_rejected_brands_for_prompt(db, vertical_id),
        "rejected_products": get_rejected_products_for_prompt(db, vertical_id),
    }


def _get_brand_aliases(db: Session, canonical_brand_id: int) -> List[str]:
    """Get aliases for a canonical brand."""
    aliases = db.query(BrandAlias.alias).filter(
        BrandAlias.canonical_brand_id == canonical_brand_id
    ).all()
    return [alias for (alias,) in aliases]


def _get_product_aliases(db: Session, canonical_product_id: int) -> List[str]:
    """Get aliases for a canonical product."""
    aliases = db.query(ProductAlias.alias).filter(
        ProductAlias.canonical_product_id == canonical_product_id
    ).all()
    return [alias for (alias,) in aliases]


def _get_all_brand_aliases(db: Session, vertical_id: int) -> Set[str]:
    """Get all aliases for validated brands in a vertical."""
    validated_brand_ids = db.query(CanonicalBrand.id).filter(
        CanonicalBrand.vertical_id == vertical_id,
        CanonicalBrand.is_validated == True,
    ).all()

    brand_ids = [bid for (bid,) in validated_brand_ids]
    if not brand_ids:
        return set()

    aliases = db.query(BrandAlias.alias).filter(
        BrandAlias.canonical_brand_id.in_(brand_ids)
    ).all()

    result: Set[str] = set()
    for (alias,) in aliases:
        result.add(alias.lower())
        result.add(alias)

    return result


def _get_all_product_aliases(db: Session, vertical_id: int) -> Set[str]:
    """Get all aliases for validated products in a vertical."""
    validated_product_ids = db.query(CanonicalProduct.id).filter(
        CanonicalProduct.vertical_id == vertical_id,
        CanonicalProduct.is_validated == True,
    ).all()

    product_ids = [pid for (pid,) in validated_product_ids]
    if not product_ids:
        return set()

    aliases = db.query(ProductAlias.alias).filter(
        ProductAlias.canonical_product_id.in_(product_ids)
    ).all()

    result: Set[str] = set()
    for (alias,) in aliases:
        result.add(alias.lower())
        result.add(alias)

    return result


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
    }
    return reason_map.get(reason, reason)


def get_canonical_for_validated_brand(
    db: Session,
    brand_name: str,
    vertical_id: int,
) -> str:
    """Get the canonical name for a validated brand."""
    from sqlalchemy import func

    brand_lower = brand_name.lower()

    canonical = db.query(CanonicalBrand).filter(
        CanonicalBrand.vertical_id == vertical_id,
        CanonicalBrand.is_validated == True,
        func.lower(CanonicalBrand.canonical_name) == brand_lower,
    ).first()

    if canonical:
        return canonical.canonical_name

    alias = db.query(BrandAlias).join(CanonicalBrand).filter(
        CanonicalBrand.vertical_id == vertical_id,
        CanonicalBrand.is_validated == True,
        func.lower(BrandAlias.alias) == brand_lower,
    ).first()

    if alias:
        return alias.canonical_brand.canonical_name

    return brand_name


def get_canonical_for_validated_product(
    db: Session,
    product_name: str,
    vertical_id: int,
) -> str:
    """Get the canonical name for a validated product."""
    from sqlalchemy import func

    product_lower = product_name.lower()

    canonical = db.query(CanonicalProduct).filter(
        CanonicalProduct.vertical_id == vertical_id,
        CanonicalProduct.is_validated == True,
        func.lower(CanonicalProduct.canonical_name) == product_lower,
    ).first()

    if canonical:
        return canonical.canonical_name

    alias = db.query(ProductAlias).join(CanonicalProduct).filter(
        CanonicalProduct.vertical_id == vertical_id,
        CanonicalProduct.is_validated == True,
        func.lower(ProductAlias.alias) == product_lower,
    ).first()

    if alias:
        return alias.canonical_product.canonical_name

    return product_name
