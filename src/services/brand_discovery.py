from typing import Dict, List

from sqlalchemy.orm import Session

from models import Brand
from services.brand_recognition import extract_entities


def discover_all_brands(
    text: str,
    vertical_id: int,
    user_brands: List[Brand],
    db: Session,
) -> List[Brand]:
    all_brands_map: Dict[str, Brand] = {}

    for user_brand in user_brands:
        normalized_name = user_brand.display_name.lower().strip()
        all_brands_map[normalized_name] = user_brand

    discovered_entities = extract_entities(text, "", {})

    for canonical_name, surface_forms in discovered_entities.items():
        normalized_name = canonical_name.lower().strip()

        if normalized_name in all_brands_map:
            continue

        if _is_brand_like(canonical_name, surface_forms):
            brand = _get_or_create_discovered_brand(
                db, vertical_id, canonical_name
            )
            all_brands_map[normalized_name] = brand

    return list(all_brands_map.values())


def _is_brand_like(canonical_name: str, surface_forms: List[str]) -> bool:
    if len(canonical_name) < 2:
        return False
    if len(canonical_name) > 50:
        return False
    common_words = {"最好", "推荐", "性能", "价格", "质量", "选择"}
    if canonical_name in common_words:
        return False
    return True


def _get_or_create_discovered_brand(
    db: Session,
    vertical_id: int,
    brand_name: str,
) -> Brand:
    existing = (
        db.query(Brand)
        .filter(
            Brand.vertical_id == vertical_id,
            Brand.display_name == brand_name,
        )
        .first()
    )

    if existing:
        return existing

    brand = Brand(
        vertical_id=vertical_id,
        display_name=brand_name,
        aliases={"zh": [], "en": []},
        is_user_input=False,
    )
    db.add(brand)
    db.flush()

    return brand
