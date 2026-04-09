import re
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
        canonical_name = _canonicalize_brand_name(user_brand.display_name)
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

    for brand_name, surface_forms in extraction_result.brands.items():
        canonical_name = _canonicalize_brand_name(brand_name)
        normalized_key = canonical_name.lower().strip()

        if normalized_key in all_brands_map:
            _merge_surface_forms(all_brands_map[normalized_key], surface_forms)
            continue

        original_key = brand_name.lower().strip()
        if original_key in all_brands_map:
            _merge_surface_forms(all_brands_map[original_key], surface_forms)
            continue

        brand = _get_or_create_discovered_brand(
            db, vertical_id, brand_name, vertical_name or "",
            surface_forms=surface_forms,
        )
        all_brands_map[normalized_key] = brand

    return _deduplicate_brands(list(all_brands_map.values()))


def discover_brands_and_products(
    text: str,
    vertical_id: int,
    user_brands: List[Brand],
    db: Session,
    vertical_name: Optional[str] = None,
    vertical_description: Optional[str] = None,
    skip_finalize: bool = False,
) -> Tuple[List[Brand], ExtractionResult]:
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[DISCOVERY] discover_brands_and_products starting, vertical_id={vertical_id}")

    logger.info(f"[DISCOVERY] calling _extract_for_discovery")
    extraction_result = _extract_for_discovery(
        text=text,
        db=db,
        vertical_id=vertical_id,
        vertical_name=vertical_name,
        vertical_description=vertical_description,
        skip_finalize=skip_finalize,
    )
    logger.info(f"[DISCOVERY] _extract_for_discovery completed")

    logger.info(f"[DISCOVERY] calling discover_brands_and_products_from_result")
    result = discover_brands_and_products_from_result(
        text,
        vertical_id,
        user_brands,
        db,
        extraction_result,
        vertical_name=vertical_name,
        vertical_description=vertical_description,
    )
    logger.info(f"[DISCOVERY] discover_brands_and_products_from_result completed, returning")
    return result


def discover_brands_and_products_from_result(
    text: str,
    vertical_id: int,
    user_brands: List[Brand],
    db: Session,
    extraction_result: ExtractionResult,
    vertical_name: Optional[str] = None,
    vertical_description: Optional[str] = None,
) -> Tuple[List[Brand], ExtractionResult]:
    if not vertical_name:
        vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
        if vertical:
            vertical_name = vertical.name

    all_brands_map: Dict[str, Brand] = {}

    for user_brand in user_brands:
        canonical_name = _canonicalize_brand_name(user_brand.display_name)
        normalized_key = canonical_name.lower().strip()
        all_brands_map[normalized_key] = user_brand
        original_key = user_brand.display_name.lower().strip()
        if original_key != normalized_key:
            all_brands_map[original_key] = user_brand
        for alias in _collect_brand_variants(user_brand):
            alias_key = alias.lower().strip()
            if alias_key and alias_key not in all_brands_map:
                all_brands_map[alias_key] = user_brand

    for brand_name, surface_forms in extraction_result.brands.items():
        canonical_name = _canonicalize_brand_name(brand_name)
        normalized_key = canonical_name.lower().strip()

        if normalized_key in all_brands_map:
            _merge_surface_forms(all_brands_map[normalized_key], surface_forms)
            continue

        original_key = brand_name.lower().strip()
        if original_key in all_brands_map:
            _merge_surface_forms(all_brands_map[original_key], surface_forms)
            continue

        brand = _get_or_create_discovered_brand(
            db, vertical_id, brand_name, vertical_name or "",
            surface_forms=surface_forms,
        )
        all_brands_map[normalized_key] = brand

    return _deduplicate_brands(list(all_brands_map.values())), extraction_result


def _extract_for_discovery(
    text: str,
    db: Session,
    vertical_id: int,
    vertical_name: Optional[str],
    vertical_description: Optional[str],
    skip_finalize: bool = False,
) -> ExtractionResult:
    # Fetch vertical context from DB if not provided
    if not vertical_name:
        vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
        if vertical:
            vertical_name = vertical.name
            vertical_description = vertical.description

    return extract_entities(
        text,
        "",
        {},
        vertical=vertical_name or "",
        vertical_description=vertical_description or "",
        db=db,
        vertical_id=vertical_id,
        skip_finalize=skip_finalize,
    )


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
            if _is_substring_match(name, variant):
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
    from services.canonicalization_metrics import normalize_entity_key

    raw1 = (name1 or "").strip()
    raw2 = (name2 or "").strip()
    if len(raw1) < 2 or len(raw2) < 2:
        return False

    normalized1 = normalize_entity_key(raw1)
    normalized2 = normalize_entity_key(raw2)
    if len(normalized1) < 2 or len(normalized2) < 2 or normalized1 == normalized2:
        return False

    if len(normalized1) == len(normalized2):
        return False

    if len(normalized1) < len(normalized2):
        shorter_raw, longer_raw = raw1, raw2
        shorter, longer = normalized1, normalized2
    else:
        shorter_raw, longer_raw = raw2, raw1
        shorter, longer = normalized2, normalized1

    if shorter not in longer:
        return False

    has_cjk = _has_cjk(shorter) or _has_cjk(longer)
    min_len = 2 if has_cjk else 3
    if len(shorter) < min_len:
        return False

    min_ratio = 0.3
    if len(shorter) / len(longer) < min_ratio:
        return False

    if has_cjk:
        return True

    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(shorter_raw.casefold())}(?![a-z0-9])")
    return bool(pattern.search(longer_raw.casefold()))


def _get_or_create_discovered_brand(
    db: Session,
    vertical_id: int,
    brand_name: str,
    vertical_name: str = "",
    surface_forms: Optional[List[str]] = None,
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
        _merge_surface_forms(existing, surface_forms or [])
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
        _merge_surface_forms(existing_by_original, surface_forms or [])
        return existing_by_original

    existing_by_alias = _find_brand_by_alias(db, vertical_id, normalized_name)
    if existing_by_alias:
        _merge_surface_forms(existing_by_alias, surface_forms or [])
        return existing_by_alias

    display_name = canonical_name
    aliases = _build_aliases_from_surface_forms(canonical_name, surface_forms or [])

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


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in text)


def _build_aliases_from_surface_forms(
    canonical_name: str, surface_forms: List[str]
) -> Dict[str, List[str]]:
    zh: List[str] = []
    en: List[str] = []
    seen: set[str] = {canonical_name.lower()}
    for form in surface_forms:
        form = form.strip()
        if not form or form.lower() in seen:
            continue
        seen.add(form.lower())
        if _has_cjk(form):
            zh.append(form)
        else:
            en.append(form)
    return {"zh": zh, "en": en}


def _merge_surface_forms(brand: Brand, surface_forms: List[str]) -> None:
    if not surface_forms:
        return
    aliases = brand.aliases or {"zh": [], "en": []}
    existing_lower = {v.lower() for v in aliases.get("zh", []) + aliases.get("en", [])}
    existing_lower.add(brand.display_name.lower())
    if brand.original_name:
        existing_lower.add(brand.original_name.lower())
    changed = False
    for form in surface_forms:
        form = form.strip()
        if not form or form.lower() in existing_lower:
            continue
        existing_lower.add(form.lower())
        if _has_cjk(form):
            aliases.setdefault("zh", []).append(form)
        else:
            aliases.setdefault("en", []).append(form)
        changed = True
    if changed:
        brand.aliases = dict(aliases)


def _deduplicate_brands(brands: List[Brand]) -> List[Brand]:
    seen: set[int] = set()
    result: List[Brand] = []
    for b in brands:
        if b.id not in seen:
            seen.add(b.id)
            result.append(b)
    return result


def _canonicalize_brand_name(name: str) -> str:
    name = name.strip()
    if not name:
        return name

    if name.isupper() and len(name) <= 4:
        return name.upper()

    if name.isascii() and name.islower():
        return name.title()

    return name


def _get_canonical_lookup_name(name: str) -> str:
    return name.strip()
