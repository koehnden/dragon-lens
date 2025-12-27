from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from constants.brand_aliases import BRAND_ALIAS_MAP
from models import Brand, Product, Vertical
from services.brand_recognition import extract_entities, ExtractionResult


def discover_all_brands(
    text: str,
    vertical_id: int,
    user_brands: List[Brand],
    db: Session,
    vertical_name: Optional[str] = None,
    vertical_description: Optional[str] = None,
) -> List[Brand]:
    all_brands_map: Dict[str, Brand] = {}

    if not vertical_name:
        vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
        if vertical:
            vertical_name = vertical.name
            vertical_description = vertical.description

    for user_brand in user_brands:
        canonical_name = _canonicalize_brand_name(user_brand.display_name)
        normalized_key = canonical_name.lower().strip()
        all_brands_map[normalized_key] = user_brand
        original_key = user_brand.display_name.lower().strip()
        if original_key != normalized_key:
            all_brands_map[original_key] = user_brand

    extraction_result = extract_entities(
        text, "", {},
        vertical=vertical_name or "",
        vertical_description=vertical_description or "",
    )

    for brand_name in extraction_result.brands.keys():
        canonical_name = _canonicalize_brand_name(brand_name)
        normalized_key = canonical_name.lower().strip()

        if normalized_key in all_brands_map:
            continue

        original_key = brand_name.lower().strip()
        if original_key in all_brands_map:
            continue

        brand = _get_or_create_discovered_brand(db, vertical_id, brand_name)
        all_brands_map[normalized_key] = brand

    return list(all_brands_map.values())


def discover_brands_and_products(
    text: str,
    vertical_id: int,
    user_brands: List[Brand],
    db: Session,
    vertical_name: Optional[str] = None,
    vertical_description: Optional[str] = None,
) -> Tuple[List[Brand], ExtractionResult]:
    if not vertical_name:
        vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
        if vertical:
            vertical_name = vertical.name
            vertical_description = vertical.description

    extraction_result = extract_entities(
        text, "", {},
        vertical=vertical_name or "",
        vertical_description=vertical_description or "",
    )

    all_brands_map: Dict[str, Brand] = {}

    for user_brand in user_brands:
        canonical_name = _canonicalize_brand_name(user_brand.display_name)
        normalized_key = canonical_name.lower().strip()
        all_brands_map[normalized_key] = user_brand
        original_key = user_brand.display_name.lower().strip()
        if original_key != normalized_key:
            all_brands_map[original_key] = user_brand

    for brand_name in extraction_result.brands.keys():
        canonical_name = _canonicalize_brand_name(brand_name)
        normalized_key = canonical_name.lower().strip()

        if normalized_key in all_brands_map:
            continue

        original_key = brand_name.lower().strip()
        if original_key in all_brands_map:
            continue

        brand = _get_or_create_discovered_brand(db, vertical_id, brand_name)
        all_brands_map[normalized_key] = brand

    return list(all_brands_map.values()), extraction_result


def _is_brand_like(canonical_name: str, surface_forms: List[str]) -> bool:
    import re

    if len(canonical_name) < 2:
        return False
    if len(canonical_name) > 30:
        return False

    feature_descriptor_patterns = [
        r"等$",
        r"[\u4e00-\u9fff]+度$",
        r"[\u4e00-\u9fff]+性$",
        r"[\u4e00-\u9fff]+率$",
        r"[\u4e00-\u9fff]+感$",
        r"[\u4e00-\u9fff]+力$",
        r"(效果|功能|特点|优点|缺点|成分|配置|体验|表现|质地|口感|触感)",
        r"(空间|时间|速度|距离|重量|容量|尺寸)",
        r"(良好|优秀|出色|卓越|强劲|轻薄|厚重|柔软|坚固)",
        r"^[\u4e00-\u9fff]{5,}$",
    ]

    for pattern in feature_descriptor_patterns:
        if re.search(pattern, canonical_name):
            return False

    generic_stop_words = {
        "最好", "推荐", "性能", "价格", "质量", "选择",
        "品牌", "产品", "类型", "种类", "系列",
        "国产", "进口", "豪华", "高端", "入门",
        "安全性", "可靠性", "舒适性", "性价比",
    }
    if canonical_name in generic_stop_words:
        return False

    if re.search(r"[、，。！？：；]", canonical_name):
        return False

    brand_product_patterns = [
        r"^[A-Z]{2,}[\-]?[A-Z0-9]*$",
        r"[A-Za-z]+\d+",
        r"\d+[A-Za-z]+",
        r"Model\s?[A-ZX0-9]",
        r"ID\.",
        r"[\u4e00-\u9fff]{1,6}(PLUS|Plus|Pro|Max|Ultra|Mini)",
        r"[\u4e00-\u9fff]{2,6}[A-Z]\d{1,2}",
        r"^[\u4e00-\u9fff]{2,6}$",
        r"^[A-Za-z]{2,}$",
    ]

    for pattern in brand_product_patterns:
        if re.search(pattern, canonical_name):
            return True

    return False


def _get_or_create_discovered_brand(
    db: Session,
    vertical_id: int,
    brand_name: str,
) -> Brand:
    normalized_name = brand_name.strip()
    canonical_name = _canonicalize_brand_name(normalized_name)

    existing = (
        db.query(Brand)
        .filter(
            Brand.vertical_id == vertical_id,
            func.lower(Brand.display_name) == canonical_name.lower(),
        )
        .first()
    )

    if existing:
        return existing

    existing_by_original = (
        db.query(Brand)
        .filter(
            Brand.vertical_id == vertical_id,
            func.lower(Brand.display_name) == normalized_name.lower(),
        )
        .first()
    )

    if existing_by_original:
        return existing_by_original

    brand = Brand(
        vertical_id=vertical_id,
        display_name=canonical_name,
        original_name=normalized_name,
        translated_name=None,
        aliases={"zh": [], "en": []},
        is_user_input=False,
    )
    db.add(brand)
    db.flush()

    return brand


def _canonicalize_brand_name(name: str) -> str:
    name = name.strip()
    if not name:
        return name

    name_lower = name.lower()
    if name_lower in BRAND_ALIAS_MAP:
        return BRAND_ALIAS_MAP[name_lower]

    if name.isupper() and len(name) <= 4:
        return name.upper()

    if name.isascii() and name.islower():
        return name.title()

    return name


def _get_canonical_lookup_name(name: str) -> str:
    name_lower = name.lower().strip()
    if name_lower in BRAND_ALIAS_MAP:
        return BRAND_ALIAS_MAP[name_lower]
    return name.strip()
