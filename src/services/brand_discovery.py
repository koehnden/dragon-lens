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
    import re

    if len(canonical_name) < 2:
        return False
    if len(canonical_name) > 30:
        return False

    non_brand_patterns = [
        r"等$",
        r"^等",
        r"配置",
        r"功能",
        r"系统",
        r"技术",
        r"性能",
        r"价格",
        r"方面",
        r"维度",
        r"角度",
        r"优点",
        r"缺点",
        r"优势",
        r"劣势",
        r"特点",
        r"丰富",
        r"高端",
        r"顶级",
        r"中端",
        r"入门",
        r"全景",
        r"天窗",
        r"座椅",
        r"仪表",
        r"屏幕",
        r"车机",
        r"智能",
        r"舒适",
        r"空间",
        r"后排",
        r"后备箱",
        r"油耗",
        r"能耗",
    ]

    for pattern in non_brand_patterns:
        if re.search(pattern, canonical_name):
            return False

    common_words = {
        "最好", "推荐", "性能", "价格", "质量", "选择",
        "车型", "品牌", "汽车", "SUV", "轿车", "MPV",
        "合资", "自主", "国产", "进口", "豪华",
    }
    if canonical_name in common_words:
        return False

    brand_patterns = [
        r"[A-Z]{2,}",
        r"[A-Za-z]+\d+",
        r"\d+[A-Za-z]+",
        r"[\u4e00-\u9fff]{1,4}PLUS",
        r"[\u4e00-\u9fff]{1,4}Plus",
        r"[\u4e00-\u9fff]{1,4}Pro",
        r"[\u4e00-\u9fff]{1,4}Max",
        r"[\u4e00-\u9fff]{1,4}DM-i",
        r"Model\s?[A-Z0-9]",
        r"ID\.",
    ]

    for pattern in brand_patterns:
        if re.search(pattern, canonical_name):
            return True

    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", canonical_name))
    if 2 <= chinese_chars <= 6 and not re.search(r"[、，。！？：；]", canonical_name):
        return True

    return False


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
