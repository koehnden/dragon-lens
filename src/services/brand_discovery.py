import re
from dataclasses import dataclass
from typing import Dict, List

from sqlalchemy.orm import Session

from models import Brand, Product
from models.domain import EntityType
from services.brand_recognition import extract_entities


PRODUCT_INDICATORS = [
    r"\d+",
    r"(PLUS|Plus|PRO|Pro|MAX|Max|Ultra|Mini|Lite|SE|GT|RS|Sport)",
    r"(Model\s?[A-ZX0-9])",
    r"([A-Z]{1,2}\d{1,3})",
    r"(宋|汉|唐|秦|元|海豚|海鸥|仰望)",
    r"(L\d|ES\d|EC\d|ET\d|G\d|P\d)",
]

GENERIC_TERMS = {
    "suv", "car", "sedan", "truck", "van", "coupe", "hatchback",
    "phone", "smartphone", "tablet", "laptop", "computer",
    "轿车", "越野车", "跑车", "电动车", "新能源",
    "手机", "电脑", "平板",
    "best", "top", "good", "great", "new", "old",
    "最好", "推荐", "选择", "品牌", "产品",
}


@dataclass
class EntityCollection:
    brands: List[Brand]
    products: List[Product]


@dataclass
class EntityTarget:
    name: str
    brand_id: int
    entity_type: EntityType


def _has_model_token(name: str) -> bool:
    parts = name.split()
    if len(parts) < 2:
        return False
    tail = parts[1:]
    return any(any(char.isdigit() for char in token) or token.isupper() for token in tail)


def classify_entity_type(name: str) -> EntityType:
    if not name or len(name) < 2:
        return EntityType.UNKNOWN

    normalized = name.lower().strip()

    if normalized in GENERIC_TERMS:
        return EntityType.UNKNOWN

    if re.match(r"^\d+$", normalized):
        return EntityType.UNKNOWN

    if re.match(r"^(suv|car|auto)\d*$", normalized):
        return EntityType.UNKNOWN

    feature_patterns = [
        r"(性|度|率|感|力)$",
        r"(效果|功能|特点|配置|体验|表现)",
        r"(安全|舒适|豪华|高端|入门)",
        r"(丰富|优秀|良好)",
        r"(性价比|可靠性|实用性|经济性)",
    ]
    for pattern in feature_patterns:
        if re.search(pattern, name):
            return EntityType.UNKNOWN

    for pattern in PRODUCT_INDICATORS:
        if re.search(pattern, name, re.IGNORECASE):
            return EntityType.PRODUCT

    if _has_model_token(name):
        return EntityType.PRODUCT

    if re.search(r"[\u4e00-\u9fff]", name):
        if len(name) <= 4 and not re.search(r"\d", name):
            return EntityType.BRAND

    if re.match(r"^[A-Z][a-z]*$", name) and len(name) >= 2:
        return EntityType.BRAND

    if re.match(r"^[A-Z][a-z]+(\s+[A-Z][a-z]+)?$", name):
        return EntityType.BRAND

    if re.match(r"^[A-Z]{2,}$", name) and len(name) <= 6:
        return EntityType.BRAND

    return EntityType.UNKNOWN


def discover_all_brands(
    text: str,
    vertical_id: int,
    user_brands: List[Brand],
    db: Session,
) -> EntityCollection:
    collection = EntityCollection(brands=list(user_brands), products=[])
    brand_map: Dict[str, Brand] = {
        brand.display_name.lower().strip(): brand for brand in collection.brands
    }

    discovered_entities = extract_entities(text, "", {})

    for canonical_name, surface_forms in discovered_entities.items():
        normalized_name = canonical_name.lower().strip()
        if normalized_name in brand_map:
            continue

        entity_type = classify_entity_type(canonical_name)
        if entity_type == EntityType.PRODUCT:
            product = _register_product(canonical_name, collection.brands, db)
            if product:
                collection.products.append(product)
            continue

        if _is_brand_like(canonical_name, surface_forms):
            brand = _get_or_create_discovered_brand(
                db, vertical_id, canonical_name
            )
            brand_map[normalized_name] = brand
            collection.brands.append(brand)

    return collection


def _find_matching_brand(name: str, brands: List[Brand]) -> Brand | None:
    lowered = name.lower()
    for brand in brands:
        translated = (brand.translated_name or "").lower()
        aliases = brand.aliases.get("zh", []) + brand.aliases.get("en", [])
        has_alias = any(alias.lower() in lowered for alias in aliases)
        if (
            brand.display_name.lower() in lowered
            or translated in lowered
            or has_alias
        ):
            return brand
    return None


def _get_or_create_product(db: Session, brand_id: int, name: str) -> Product:
    product = db.query(Product).filter(
        Product.brand_id == brand_id, Product.original_name == name
    ).first()
    if product:
        return product
    product = Product(brand_id=brand_id, original_name=name, translated_name=None)
    db.add(product)
    db.flush()
    return product


def _register_product(name: str, brands: List[Brand], db: Session) -> Product | None:
    brand = _find_matching_brand(name, brands)
    if not brand:
        return None
    return _get_or_create_product(db, brand.id, name)


def build_entity_targets(brands: List[Brand], products: List[Product]) -> List[EntityTarget]:
    targets = [
        EntityTarget(
            name=brand.display_name,
            brand_id=brand.id,
            entity_type=EntityType.BRAND,
        )
        for brand in brands
    ]
    product_targets = [
        EntityTarget(
            name=product.original_name,
            brand_id=product.brand_id,
            entity_type=EntityType.PRODUCT,
        )
        for product in products
        if product.brand_id
    ]
    return targets + product_targets


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
        original_name=brand_name,
        translated_name=None,
        aliases={"zh": [], "en": []},
        is_user_input=False,
        entity_type=EntityType.BRAND,
    )
    db.add(brand)
    db.flush()

    return brand
