from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Brand, Vertical
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
        canonical_name = _canonicalize_brand_name(
            user_brand.display_name, vertical_name or ""
        )
        normalized_key = canonical_name.lower().strip()
        all_brands_map[normalized_key] = user_brand
        original_key = user_brand.display_name.lower().strip()
        if original_key != normalized_key:
            all_brands_map[original_key] = user_brand
        for alias in _collect_brand_variants(user_brand):
            alias_key = alias.lower().strip()
            if alias_key and alias_key not in all_brands_map:
                all_brands_map[alias_key] = user_brand

    extraction_result = extract_entities(
        text, "", {},
        vertical=vertical_name or "",
        vertical_description=vertical_description or "",
        db=db,
        vertical_id=vertical_id,
    )

    for brand_name in extraction_result.brands.keys():
        canonical_name = _canonicalize_brand_name(brand_name, vertical_name or "")
        normalized_key = canonical_name.lower().strip()

        if normalized_key in all_brands_map:
            continue

        original_key = brand_name.lower().strip()
        if original_key in all_brands_map:
            continue

        brand = _get_or_create_discovered_brand(
            db, vertical_id, brand_name, vertical_name or ""
        )
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
        db=db,
        vertical_id=vertical_id,
    )

    all_brands_map: Dict[str, Brand] = {}

    for user_brand in user_brands:
        canonical_name = _canonicalize_brand_name(
            user_brand.display_name, vertical_name or ""
        )
        normalized_key = canonical_name.lower().strip()
        all_brands_map[normalized_key] = user_brand
        original_key = user_brand.display_name.lower().strip()
        if original_key != normalized_key:
            all_brands_map[original_key] = user_brand
        for alias in _collect_brand_variants(user_brand):
            alias_key = alias.lower().strip()
            if alias_key and alias_key not in all_brands_map:
                all_brands_map[alias_key] = user_brand

    for brand_name in extraction_result.brands.keys():
        canonical_name = _canonicalize_brand_name(brand_name, vertical_name or "")
        normalized_key = canonical_name.lower().strip()

        if normalized_key in all_brands_map:
            continue

        original_key = brand_name.lower().strip()
        if original_key in all_brands_map:
            continue

        brand = _get_or_create_discovered_brand(
            db, vertical_id, brand_name, vertical_name or ""
        )
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


def _find_brand_by_alias(
    db: Session,
    vertical_id: int,
    name: str,
) -> Optional[Brand]:
    from services.canonicalization_metrics import normalize_entity_key

    name_normalized = normalize_entity_key(name)
    if not name_normalized:
        return None
    brands = db.query(Brand).filter(Brand.vertical_id == vertical_id).all()
    for brand in brands:
        variants = _collect_brand_variants(brand)
        for variant in variants:
            variant_normalized = normalize_entity_key(variant)
            if not variant_normalized:
                continue
            if variant_normalized == name_normalized:
                return brand
            if _is_substring_match(name_normalized, variant_normalized):
                return brand
    return None


def _collect_brand_variants(brand: Brand) -> List[str]:
    variants = [brand.display_name, brand.original_name]
    if brand.translated_name:
        variants.append(brand.translated_name)
    aliases = brand.aliases or {}
    variants.extend(aliases.get("en", []))
    variants.extend(aliases.get("zh", []))
    return [v for v in variants if v]


def _is_substring_match(name1: str, name2: str) -> bool:
    if len(name1) < 2 or len(name2) < 2:
        return False
    shorter = min(name1, name2, key=len)
    longer = max(name1, name2, key=len)
    if shorter not in longer:
        return False
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in shorter)
    min_len = 2 if has_cjk else 3
    if len(shorter) < min_len:
        return False
    if longer.startswith(shorter):
        return True
    min_ratio = 0.3 if has_cjk else 0.5
    if len(shorter) / len(longer) < min_ratio:
        return False
    return True


def _get_or_create_discovered_brand(
    db: Session,
    vertical_id: int,
    brand_name: str,
    vertical_name: str = "",
) -> Brand:
    from src.services.wikidata_lookup import lookup_brand
    from src.services.translater import format_entity_label

    normalized_name = brand_name.strip()
    canonical_name = _canonicalize_brand_name(normalized_name, vertical_name)

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

    existing_by_alias = _find_brand_by_alias(db, vertical_id, normalized_name)
    if existing_by_alias:
        return existing_by_alias

    wikidata_info = lookup_brand(normalized_name, vertical_name) if vertical_name else None

    if wikidata_info:
        english_name = wikidata_info.get("name_en", canonical_name)
        chinese_name = wikidata_info.get("name_zh", "")
        display_name = format_entity_label(chinese_name, english_name)
        aliases = {
            "zh": wikidata_info.get("aliases_zh", []),
            "en": wikidata_info.get("aliases_en", []),
        }
    else:
        display_name = canonical_name
        aliases = {"zh": [], "en": []}

    return _insert_or_get_brand(
        db=db,
        vertical_id=vertical_id,
        display_name=display_name,
        original_name=normalized_name,
        translated_name=canonical_name if canonical_name != normalized_name else None,
        aliases=aliases,
    )


def _insert_or_get_brand(
    db: Session,
    vertical_id: int,
    display_name: str,
    original_name: str,
    translated_name: str | None,
    aliases: dict,
) -> Brand:
    existing = db.query(Brand).filter(
        Brand.vertical_id == vertical_id,
        func.lower(Brand.display_name) == display_name.lower(),
    ).first()
    if existing:
        return existing
    _upsert_brand(db, vertical_id, display_name, original_name, translated_name, aliases)
    existing = db.query(Brand).filter(
        Brand.vertical_id == vertical_id,
        func.lower(Brand.display_name) == display_name.lower(),
    ).first()
    if existing:
        return existing
    brand = Brand(vertical_id=vertical_id, display_name=display_name, original_name=original_name, translated_name=translated_name, aliases=aliases, is_user_input=False)
    db.add(brand)
    db.flush()
    return brand


def _upsert_brand(
    db: Session,
    vertical_id: int,
    display_name: str,
    original_name: str,
    translated_name: str | None,
    aliases: dict,
) -> None:
    if db.get_bind().dialect.name != "postgresql":
        db.add(Brand(
            vertical_id=vertical_id,
            display_name=display_name,
            original_name=original_name,
            translated_name=translated_name,
            aliases=aliases,
            is_user_input=False,
        ))
        db.flush()
        return
    from sqlalchemy.dialects.postgresql import insert

    stmt = insert(Brand).values(
        vertical_id=vertical_id,
        display_name=display_name,
        original_name=original_name,
        translated_name=translated_name,
        aliases=aliases,
        is_user_input=False,
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["vertical_id", "display_name"])
    db.execute(stmt)
    db.flush()


def _canonicalize_brand_name(name: str, vertical: str = "") -> str:
    from src.services.wikidata_lookup import get_canonical_brand_name

    name = name.strip()
    if not name:
        return name

    if vertical:
        canonical = get_canonical_brand_name(name, vertical)
        if canonical:
            return canonical

    if name.isupper() and len(name) <= 4:
        return name.upper()

    if name.isascii() and name.islower():
        return name.title()

    return name


def _get_canonical_lookup_name(name: str, vertical: str = "") -> str:
    from src.services.wikidata_lookup import get_canonical_brand_name

    name_lower = name.lower().strip()

    if vertical:
        canonical = get_canonical_brand_name(name_lower, vertical)
        if canonical:
            return canonical

    return name.strip()
