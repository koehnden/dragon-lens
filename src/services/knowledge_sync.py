from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from models.admin_schemas import (
    KnowledgeAliasPayload,
    KnowledgeBrandPayload,
    KnowledgeMappingPayload,
    KnowledgeProductPayload,
    KnowledgeRejectedEntityPayload,
    KnowledgeSyncRequest,
    KnowledgeTranslationOverridePayload,
)
from models.domain import EntityType
from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeProductBrandMapping,
    KnowledgeRejectedEntity,
    KnowledgeTranslationOverride,
    KnowledgeVertical,
    KnowledgeVerticalAlias,
)
from services.knowledge_verticals import (
    ensure_vertical_alias,
    get_or_create_vertical,
    resolve_knowledge_vertical_id,
)


def build_knowledge_sync_request(
    knowledge_db: Session,
    vertical_name: str,
    submission_id: str,
    source_app_version: str | None = None,
) -> KnowledgeSyncRequest:
    vertical = _knowledge_vertical(knowledge_db, vertical_name)
    return KnowledgeSyncRequest(
        submission_id=submission_id,
        source_app_version=source_app_version,
        submitted_at=datetime.now(timezone.utc),
        vertical_name=vertical.name,
        vertical_description=vertical.description,
        vertical_aliases=_vertical_aliases(knowledge_db, vertical.id),
        brands=_brand_payloads(knowledge_db, vertical.id),
        products=_product_payloads(knowledge_db, vertical.id),
        mappings=_mapping_payloads(knowledge_db, vertical.id),
        rejected_entities=_rejected_payloads(knowledge_db, vertical.id),
        translation_overrides=_translation_payloads(knowledge_db, vertical.id),
    )


def ingest_knowledge_sync_submission(
    knowledge_db: Session,
    payload: KnowledgeSyncRequest,
) -> tuple[int, dict[str, int], dict[str, int]]:
    created, updated = _counter_map(), _counter_map()
    vertical = get_or_create_vertical(knowledge_db, payload.vertical_name.strip())
    _sync_vertical_description(vertical, payload.vertical_description, updated)
    _sync_vertical_aliases(knowledge_db, vertical.id, payload)
    brands = _sync_brands(knowledge_db, vertical.id, payload.brands, created, updated)
    products = _sync_products(
        knowledge_db,
        vertical.id,
        payload.products,
        brands,
        created,
        updated,
    )
    _sync_mappings(
        knowledge_db, vertical.id, payload.mappings, brands, products, created, updated
    )
    _sync_rejections(
        knowledge_db, vertical.id, payload.rejected_entities, created, updated
    )
    _sync_translations(
        knowledge_db,
        vertical.id,
        payload.translation_overrides,
        created,
        updated,
    )
    return vertical.id, created, updated


def _counter_map() -> dict[str, int]:
    return {
        "verticals": 0,
        "brands": 0,
        "brand_aliases": 0,
        "products": 0,
        "product_aliases": 0,
        "mappings": 0,
        "rejections": 0,
        "translations": 0,
    }


def _knowledge_vertical(knowledge_db: Session, vertical_name: str) -> KnowledgeVertical:
    vertical_id = resolve_knowledge_vertical_id(knowledge_db, vertical_name)
    if vertical_id:
        vertical = (
            knowledge_db.query(KnowledgeVertical)
            .filter(KnowledgeVertical.id == vertical_id)
            .first()
        )
        if vertical:
            return vertical
    vertical = (
        knowledge_db.query(KnowledgeVertical)
        .filter(func.lower(KnowledgeVertical.name) == vertical_name.casefold())
        .first()
    )
    if not vertical:
        raise ValueError(f"Knowledge vertical not found: {vertical_name}")
    return vertical


def _vertical_aliases(knowledge_db: Session, vertical_id: int) -> list[str]:
    rows = (
        knowledge_db.query(KnowledgeVerticalAlias.alias)
        .filter(KnowledgeVerticalAlias.vertical_id == vertical_id)
        .order_by(KnowledgeVerticalAlias.alias.asc())
        .all()
    )
    return [alias for (alias,) in rows if alias]


def _brand_payloads(
    knowledge_db: Session, vertical_id: int
) -> list[KnowledgeBrandPayload]:
    rows = (
        knowledge_db.query(KnowledgeBrand)
        .options(selectinload(KnowledgeBrand.aliases))
        .filter(KnowledgeBrand.vertical_id == vertical_id)
        .order_by(KnowledgeBrand.canonical_name.asc())
        .all()
    )
    return [
        KnowledgeBrandPayload(
            canonical_name=row.canonical_name,
            display_name=row.display_name,
            is_validated=row.is_validated,
            validation_source=row.validation_source,
            mention_count=row.mention_count,
            aliases=[
                KnowledgeAliasPayload(alias=alias.alias, language=alias.language)
                for alias in row.aliases
            ],
        )
        for row in rows
    ]


def _product_payloads(
    knowledge_db: Session, vertical_id: int
) -> list[KnowledgeProductPayload]:
    rows = (
        knowledge_db.query(KnowledgeProduct)
        .options(selectinload(KnowledgeProduct.aliases))
        .filter(KnowledgeProduct.vertical_id == vertical_id)
        .order_by(KnowledgeProduct.canonical_name.asc())
        .all()
    )
    brand_names = _brand_name_map(knowledge_db, vertical_id)
    return [
        KnowledgeProductPayload(
            canonical_name=row.canonical_name,
            display_name=row.display_name,
            brand_canonical_name=brand_names.get(row.brand_id),
            is_validated=row.is_validated,
            validation_source=row.validation_source,
            mention_count=row.mention_count,
            aliases=[
                KnowledgeAliasPayload(alias=alias.alias, language=alias.language)
                for alias in row.aliases
            ],
        )
        for row in rows
    ]


def _brand_name_map(knowledge_db: Session, vertical_id: int) -> dict[int, str]:
    rows = (
        knowledge_db.query(KnowledgeBrand.id, KnowledgeBrand.canonical_name)
        .filter(KnowledgeBrand.vertical_id == vertical_id)
        .all()
    )
    return {brand_id: canonical_name for brand_id, canonical_name in rows}


def _mapping_payloads(
    knowledge_db: Session, vertical_id: int
) -> list[KnowledgeMappingPayload]:
    brand_names = _brand_name_map(knowledge_db, vertical_id)
    product_names = _product_name_map(knowledge_db, vertical_id)
    rows = (
        knowledge_db.query(KnowledgeProductBrandMapping)
        .filter(KnowledgeProductBrandMapping.vertical_id == vertical_id)
        .all()
    )
    return [
        KnowledgeMappingPayload(
            product_canonical_name=product_names.get(row.product_id, ""),
            brand_canonical_name=brand_names.get(row.brand_id, ""),
            is_validated=row.is_validated,
            source=row.source,
        )
        for row in rows
        if row.product_id in product_names and row.brand_id in brand_names
    ]


def _product_name_map(knowledge_db: Session, vertical_id: int) -> dict[int, str]:
    rows = (
        knowledge_db.query(KnowledgeProduct.id, KnowledgeProduct.canonical_name)
        .filter(KnowledgeProduct.vertical_id == vertical_id)
        .all()
    )
    return {product_id: canonical_name for product_id, canonical_name in rows}


def _rejected_payloads(
    knowledge_db: Session,
    vertical_id: int,
) -> list[KnowledgeRejectedEntityPayload]:
    rows = (
        knowledge_db.query(KnowledgeRejectedEntity)
        .filter(KnowledgeRejectedEntity.vertical_id == vertical_id)
        .order_by(KnowledgeRejectedEntity.name.asc())
        .all()
    )
    return [
        KnowledgeRejectedEntityPayload(
            entity_type=row.entity_type.value,
            name=row.name,
            reason=row.reason,
        )
        for row in rows
    ]


def _translation_payloads(
    knowledge_db: Session,
    vertical_id: int,
) -> list[KnowledgeTranslationOverridePayload]:
    rows = (
        knowledge_db.query(KnowledgeTranslationOverride)
        .filter(KnowledgeTranslationOverride.vertical_id == vertical_id)
        .order_by(KnowledgeTranslationOverride.canonical_name.asc())
        .all()
    )
    return [
        KnowledgeTranslationOverridePayload(
            entity_type=row.entity_type.value,
            canonical_name=row.canonical_name,
            language=row.language,
            override_text=row.override_text,
            reason=row.reason,
        )
        for row in rows
    ]


def _sync_vertical_description(
    vertical: KnowledgeVertical,
    description: str | None,
    updated: dict[str, int],
) -> None:
    if description and description != vertical.description:
        vertical.description = description
        updated["verticals"] += 1


def _sync_vertical_aliases(
    knowledge_db: Session,
    vertical_id: int,
    payload: KnowledgeSyncRequest,
) -> None:
    aliases = {payload.vertical_name, *payload.vertical_aliases}
    for alias in sorted(a.strip() for a in aliases if a and a.strip()):
        ensure_vertical_alias(knowledge_db, vertical_id, alias)


def _sync_brands(
    knowledge_db: Session,
    vertical_id: int,
    payloads: list[KnowledgeBrandPayload],
    created: dict[str, int],
    updated: dict[str, int],
) -> dict[str, KnowledgeBrand]:
    synced: dict[str, KnowledgeBrand] = {}
    for payload in payloads:
        brand = _brand_by_canonical_name(
            knowledge_db, vertical_id, payload.canonical_name
        )
        if brand is None:
            brand = KnowledgeBrand(
                vertical_id=vertical_id,
                canonical_name=payload.canonical_name,
                display_name=payload.display_name,
            )
            knowledge_db.add(brand)
            knowledge_db.flush()
            created["brands"] += 1
        elif _update_brand(brand, payload):
            updated["brands"] += 1
        _sync_brand_aliases(knowledge_db, brand.id, payload.aliases, created)
        synced[payload.canonical_name] = brand
    return synced


def _brand_by_canonical_name(
    knowledge_db: Session,
    vertical_id: int,
    canonical_name: str,
) -> KnowledgeBrand | None:
    return (
        knowledge_db.query(KnowledgeBrand)
        .filter(
            KnowledgeBrand.vertical_id == vertical_id,
            func.lower(KnowledgeBrand.canonical_name) == canonical_name.casefold(),
        )
        .first()
    )


def _update_brand(brand: KnowledgeBrand, payload: KnowledgeBrandPayload) -> bool:
    changed = False
    if (
        payload.display_name
        and brand.display_name != payload.display_name
        and not brand.is_validated
    ):
        brand.display_name = payload.display_name
        changed = True
    if payload.mention_count > brand.mention_count:
        brand.mention_count = payload.mention_count
        changed = True
    if payload.is_validated and not brand.is_validated:
        brand.is_validated = True
        changed = True
    if (
        payload.validation_source
        and brand.validation_source != payload.validation_source
    ):
        brand.validation_source = payload.validation_source
        changed = True
    return changed


def _sync_brand_aliases(
    knowledge_db: Session,
    brand_id: int,
    aliases: list[KnowledgeAliasPayload],
    created: dict[str, int],
) -> None:
    existing = _brand_alias_set(knowledge_db, brand_id)
    for alias in aliases:
        if alias.alias in existing:
            continue
        knowledge_db.add(
            KnowledgeBrandAlias(
                brand_id=brand_id,
                alias=alias.alias,
                language=alias.language,
            )
        )
        created["brand_aliases"] += 1


def _brand_alias_set(knowledge_db: Session, brand_id: int) -> set[str]:
    rows = (
        knowledge_db.query(KnowledgeBrandAlias.alias)
        .filter(KnowledgeBrandAlias.brand_id == brand_id)
        .all()
    )
    return {alias for (alias,) in rows if alias}


def _sync_products(
    knowledge_db: Session,
    vertical_id: int,
    payloads: list[KnowledgeProductPayload],
    brands: dict[str, KnowledgeBrand],
    created: dict[str, int],
    updated: dict[str, int],
) -> dict[str, KnowledgeProduct]:
    synced: dict[str, KnowledgeProduct] = {}
    for payload in payloads:
        product = _product_by_canonical_name(
            knowledge_db, vertical_id, payload.canonical_name
        )
        brand = brands.get(payload.brand_canonical_name or "")
        if product is None:
            product = KnowledgeProduct(
                vertical_id=vertical_id,
                brand_id=brand.id if brand else None,
                canonical_name=payload.canonical_name,
                display_name=payload.display_name,
            )
            knowledge_db.add(product)
            knowledge_db.flush()
            created["products"] += 1
        elif _update_product(product, payload, brand):
            updated["products"] += 1
        _sync_product_aliases(knowledge_db, product.id, payload.aliases, created)
        synced[payload.canonical_name] = product
    return synced


def _product_by_canonical_name(
    knowledge_db: Session,
    vertical_id: int,
    canonical_name: str,
) -> KnowledgeProduct | None:
    return (
        knowledge_db.query(KnowledgeProduct)
        .filter(
            KnowledgeProduct.vertical_id == vertical_id,
            func.lower(KnowledgeProduct.canonical_name) == canonical_name.casefold(),
        )
        .first()
    )


def _update_product(
    product: KnowledgeProduct,
    payload: KnowledgeProductPayload,
    brand: KnowledgeBrand | None,
) -> bool:
    changed = False
    if (
        payload.display_name
        and product.display_name != payload.display_name
        and not product.is_validated
    ):
        product.display_name = payload.display_name
        changed = True
    if payload.mention_count > product.mention_count:
        product.mention_count = payload.mention_count
        changed = True
    if payload.is_validated and not product.is_validated:
        product.is_validated = True
        changed = True
    if (
        payload.validation_source
        and product.validation_source != payload.validation_source
    ):
        product.validation_source = payload.validation_source
        changed = True
    if brand and product.brand_id != brand.id and not product.is_validated:
        product.brand_id = brand.id
        changed = True
    return changed


def _sync_product_aliases(
    knowledge_db: Session,
    product_id: int,
    aliases: list[KnowledgeAliasPayload],
    created: dict[str, int],
) -> None:
    existing = _product_alias_set(knowledge_db, product_id)
    for alias in aliases:
        if alias.alias in existing:
            continue
        knowledge_db.add(
            KnowledgeProductAlias(
                product_id=product_id,
                alias=alias.alias,
                language=alias.language,
            )
        )
        created["product_aliases"] += 1


def _product_alias_set(knowledge_db: Session, product_id: int) -> set[str]:
    rows = (
        knowledge_db.query(KnowledgeProductAlias.alias)
        .filter(KnowledgeProductAlias.product_id == product_id)
        .all()
    )
    return {alias for (alias,) in rows if alias}


def _sync_mappings(
    knowledge_db: Session,
    vertical_id: int,
    payloads: list[KnowledgeMappingPayload],
    brands: dict[str, KnowledgeBrand],
    products: dict[str, KnowledgeProduct],
    created: dict[str, int],
    updated: dict[str, int],
) -> None:
    for payload in payloads:
        brand = brands.get(payload.brand_canonical_name)
        product = products.get(payload.product_canonical_name)
        if not brand or not product:
            continue
        mapping = _mapping_for_product(knowledge_db, vertical_id, product.id)
        if mapping is None:
            knowledge_db.add(
                KnowledgeProductBrandMapping(
                    vertical_id=vertical_id,
                    product_id=product.id,
                    brand_id=brand.id,
                    is_validated=payload.is_validated,
                    source=payload.source,
                )
            )
            created["mappings"] += 1
            continue
        if _update_mapping(mapping, brand.id, payload):
            updated["mappings"] += 1


def _mapping_for_product(
    knowledge_db: Session,
    vertical_id: int,
    product_id: int,
) -> KnowledgeProductBrandMapping | None:
    return (
        knowledge_db.query(KnowledgeProductBrandMapping)
        .filter(
            KnowledgeProductBrandMapping.vertical_id == vertical_id,
            KnowledgeProductBrandMapping.product_id == product_id,
        )
        .first()
    )


def _update_mapping(
    mapping: KnowledgeProductBrandMapping,
    brand_id: int,
    payload: KnowledgeMappingPayload,
) -> bool:
    if mapping.is_validated and not payload.is_validated:
        return False
    changed = False
    if mapping.brand_id != brand_id:
        mapping.brand_id = brand_id
        changed = True
    if payload.is_validated and not mapping.is_validated:
        mapping.is_validated = True
        changed = True
    if payload.source and mapping.source != payload.source:
        mapping.source = payload.source
        changed = True
    return changed


def _sync_rejections(
    knowledge_db: Session,
    vertical_id: int,
    payloads: list[KnowledgeRejectedEntityPayload],
    created: dict[str, int],
    updated: dict[str, int],
) -> None:
    for payload in payloads:
        entity_type = EntityType(payload.entity_type)
        existing = (
            knowledge_db.query(KnowledgeRejectedEntity)
            .filter(
                KnowledgeRejectedEntity.vertical_id == vertical_id,
                KnowledgeRejectedEntity.entity_type == entity_type,
                func.lower(KnowledgeRejectedEntity.name) == payload.name.casefold(),
            )
            .first()
        )
        if existing is None:
            knowledge_db.add(
                KnowledgeRejectedEntity(
                    vertical_id=vertical_id,
                    entity_type=entity_type,
                    name=payload.name,
                    reason=payload.reason,
                )
            )
            created["rejections"] += 1
            continue
        if existing.reason != payload.reason:
            existing.reason = payload.reason
            updated["rejections"] += 1


def _sync_translations(
    knowledge_db: Session,
    vertical_id: int,
    payloads: list[KnowledgeTranslationOverridePayload],
    created: dict[str, int],
    updated: dict[str, int],
) -> None:
    for payload in payloads:
        entity_type = EntityType(payload.entity_type)
        existing = (
            knowledge_db.query(KnowledgeTranslationOverride)
            .filter(
                KnowledgeTranslationOverride.vertical_id == vertical_id,
                KnowledgeTranslationOverride.entity_type == entity_type,
                func.lower(KnowledgeTranslationOverride.canonical_name)
                == payload.canonical_name.casefold(),
                KnowledgeTranslationOverride.language == payload.language,
            )
            .first()
        )
        if existing is None:
            knowledge_db.add(
                KnowledgeTranslationOverride(
                    vertical_id=vertical_id,
                    entity_type=entity_type,
                    canonical_name=payload.canonical_name,
                    language=payload.language,
                    override_text=payload.override_text,
                    reason=payload.reason,
                )
            )
            created["translations"] += 1
            continue
        if _update_translation(existing, payload):
            updated["translations"] += 1


def _update_translation(
    override: KnowledgeTranslationOverride,
    payload: KnowledgeTranslationOverridePayload,
) -> bool:
    changed = False
    if override.override_text != payload.override_text:
        override.override_text = payload.override_text
        changed = True
    if override.reason != payload.reason:
        override.reason = payload.reason
        changed = True
    return changed
