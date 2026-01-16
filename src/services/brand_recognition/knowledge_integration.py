from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from models.domain import EntityType
from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeProductBrandMapping,
    KnowledgeRejectedEntity,
)
from services.canonicalization_metrics import normalize_entity_key
from services.knowledge_verticals import resolve_knowledge_vertical_id


@dataclass(frozen=True)
class KnowledgeExtractionContext:
    canonical_vertical_id: int
    brand_lookup: dict[str, str]
    product_lookup: dict[str, str]
    rejected_brands: set[str]
    rejected_products: set[str]
    validated_product_brand: dict[str, str]


def build_knowledge_extraction_context(
    knowledge_db: Session,
    vertical_name: str,
) -> KnowledgeExtractionContext | None:
    canonical_id = resolve_knowledge_vertical_id(knowledge_db, vertical_name)
    if not canonical_id:
        return None
    return _context_for_vertical_id(knowledge_db, int(canonical_id))


def apply_knowledge_to_extraction(
    brands: list[str],
    products: list[str],
    relationships: dict[str, str],
    context: KnowledgeExtractionContext,
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, str]]:
    brand_clusters = _brand_clusters(brands, context.brand_lookup, context.rejected_brands)
    product_clusters = _clusters(products, context.product_lookup, context.rejected_products)
    resolved = _relationships(relationships, context, product_clusters, brand_clusters)
    return brand_clusters, product_clusters, resolved


def _context_for_vertical_id(knowledge_db: Session, vertical_id: int) -> KnowledgeExtractionContext:
    brand_lookup = _entity_lookup(knowledge_db, vertical_id, KnowledgeBrand, KnowledgeBrandAlias)
    product_lookup = _entity_lookup(knowledge_db, vertical_id, KnowledgeProduct, KnowledgeProductAlias)
    rejected_brands = _rejected_set(knowledge_db, vertical_id, EntityType.BRAND)
    rejected_products = _rejected_set(knowledge_db, vertical_id, EntityType.PRODUCT)
    validated_product_brand = _validated_mappings(knowledge_db, vertical_id)
    return KnowledgeExtractionContext(
        canonical_vertical_id=vertical_id,
        brand_lookup=brand_lookup,
        product_lookup=product_lookup,
        rejected_brands=rejected_brands,
        rejected_products=rejected_products,
        validated_product_brand=validated_product_brand,
    )


def _entity_lookup(knowledge_db: Session, vertical_id: int, model: Any, alias_model: Any) -> dict[str, str]:
    rows = knowledge_db.query(model.id, model.canonical_name, model.display_name).filter(
        model.vertical_id == vertical_id,
        model.is_validated == True,
    ).all()
    if not rows:
        return {}
    ids = [int(r[0]) for r in rows]
    aliases = knowledge_db.query(alias_model.brand_id if alias_model == KnowledgeBrandAlias else alias_model.product_id, alias_model.alias).filter(
        (alias_model.brand_id.in_(ids) if alias_model == KnowledgeBrandAlias else alias_model.product_id.in_(ids))
    ).all()
    by_id: dict[int, list[str]] = {}
    for entity_id, alias in aliases:
        by_id.setdefault(int(entity_id), []).append(str(alias or ""))
    lookup: dict[str, str] = {}
    for entity_id, canonical, display in rows:
        canonical_name = str(canonical or "").strip()
        if not canonical_name:
            continue
        values = [canonical_name, str(display or "").strip()]
        values.extend([a.strip() for a in by_id.get(int(entity_id), []) if (a or "").strip()])
        _add_lookup(lookup, values, canonical_name)
    return lookup


def _add_lookup(lookup: dict[str, str], values: list[str], canonical: str) -> None:
    for value in values:
        if not (value or "").strip():
            continue
        lookup.setdefault(value.casefold(), canonical)
        lookup.setdefault(normalize_entity_key(value), canonical)


def _rejected_set(knowledge_db: Session, vertical_id: int, entity_type: EntityType) -> set[str]:
    rows = knowledge_db.query(KnowledgeRejectedEntity.name).filter(
        KnowledgeRejectedEntity.vertical_id == vertical_id,
        KnowledgeRejectedEntity.entity_type == entity_type,
    ).all()
    values = [str(name or "").strip() for (name,) in rows]
    return {v for v in values if v}


def _validated_mappings(knowledge_db: Session, vertical_id: int) -> dict[str, str]:
    rows = knowledge_db.query(
        KnowledgeProduct.canonical_name,
        KnowledgeBrand.canonical_name,
    ).join(
        KnowledgeProductBrandMapping, KnowledgeProductBrandMapping.product_id == KnowledgeProduct.id
    ).join(
        KnowledgeBrand, KnowledgeProductBrandMapping.brand_id == KnowledgeBrand.id
    ).filter(
        KnowledgeProductBrandMapping.vertical_id == vertical_id,
        KnowledgeProductBrandMapping.is_validated == True,
    ).all()
    result: dict[str, str] = {}
    for product, brand in rows:
        p = str(product or "").strip()
        b = str(brand or "").strip()
        if p and b:
            result[p] = b
    return result


def _clusters(entities: list[str], lookup: dict[str, str], rejected: set[str]) -> dict[str, list[str]]:
    clusters: dict[str, list[str]] = {}
    rejected_keys = _rejected_keys(rejected)
    for surface in entities:
        value = str(surface or "").strip()
        if not value:
            continue
        if _is_rejected(value, rejected_keys):
            continue
        canonical = _canonical(value, lookup)
        _append_surface(clusters, canonical, value)
    return clusters


def _append_surface(clusters: dict[str, list[str]], canonical: str, surface: str) -> None:
    if canonical not in clusters:
        clusters[canonical] = []
    if surface not in clusters[canonical]:
        clusters[canonical].append(surface)


def _canonical(name: str, lookup: dict[str, str]) -> str:
    return lookup.get(name.casefold()) or lookup.get(normalize_entity_key(name)) or name


def _brand_clusters(entities: list[str], lookup: dict[str, str], rejected: set[str]) -> dict[str, list[str]]:
    clusters: dict[str, list[str]] = {}
    rejected_keys = _rejected_keys(rejected)
    for surface in entities:
        value = str(surface or "").strip()
        if not value or _is_rejected(value, rejected_keys):
            continue
        canonical = _canonical_brand(value, lookup)
        _append_surface(clusters, canonical, value)
    return clusters


def _canonical_brand(name: str, lookup: dict[str, str]) -> str:
    resolved = _canonical(name, lookup)
    if resolved != name:
        return resolved
    stripped = _strip_brand_suffix(name)
    return _canonical(stripped, lookup) if stripped and stripped != name else name


def _strip_brand_suffix(name: str) -> str:
    value = (name or "").strip()
    if not value:
        return ""
    shortened = _strip_brand_suffix_chinese(value)
    return _strip_brand_suffix_english(shortened)


def _strip_brand_suffix_chinese(value: str) -> str:
    suffixes = ("有限责任公司", "有限公司", "集团", "公司", "汽车", "控股")
    lowered = value.casefold()
    for suffix in suffixes:
        if lowered.endswith(suffix.casefold()):
            return value[: -len(suffix)].strip()
    return value


def _strip_brand_suffix_english(value: str) -> str:
    parts = [p for p in (value or "").replace(".", " ").split() if p]
    suffixes = {"auto", "automotive", "group", "inc", "ltd", "co", "company", "corp", "holdings", "limited"}
    while parts and parts[-1].casefold() in suffixes:
        parts.pop()
    return " ".join(parts).strip()


def _rejected_keys(values: set[str]) -> set[str]:
    keys: set[str] = set()
    for value in values:
        v = (value or "").strip()
        if not v:
            continue
        keys.add(v.casefold())
        keys.add(normalize_entity_key(v))
    return keys


def _is_rejected(name: str, rejected_keys: set[str]) -> bool:
    return name.casefold() in rejected_keys or normalize_entity_key(name) in rejected_keys


def _relationships(
    relationships: dict[str, str],
    context: KnowledgeExtractionContext,
    products: dict[str, list[str]],
    brands: dict[str, list[str]],
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    product_keys = set(products.keys())
    for raw_product, raw_brand in (relationships or {}).items():
        product = _canonical(str(raw_product or ""), context.product_lookup).strip()
        brand = _canonical_brand(str(raw_brand or ""), context.brand_lookup).strip()
        if not product or not brand:
            continue
        if product not in product_keys:
            continue
        resolved[product] = brand
        if brand and brand not in brands:
            brands[brand] = []
    for product in product_keys:
        if product in context.validated_product_brand:
            brand = context.validated_product_brand[product]
            resolved[product] = brand
            if brand not in brands:
                brands[brand] = []
    return resolved
