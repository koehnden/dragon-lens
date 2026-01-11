import logging
from typing import Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Brand, Product, Vertical
from services.brand_recognition import (
    KNOWN_PRODUCTS,
    extract_primary_entities_from_list_item,
    is_list_format,
    split_into_list_items,
)

logger = logging.getLogger(__name__)


BRAND_PRODUCT_MAP: Dict[str, str] = {
    "rav4": "toyota",
    "rav-4": "toyota",
    "camry": "toyota",
    "corolla": "toyota",
    "highlander": "toyota",
    "prado": "toyota",
    "land cruiser": "toyota",
    "crv": "honda",
    "cr-v": "honda",
    "accord": "honda",
    "civic": "honda",
    "odyssey": "honda",
    "pilot": "honda",
    "hr-v": "honda",
    "model y": "tesla",
    "model 3": "tesla",
    "model s": "tesla",
    "model x": "tesla",
    "cybertruck": "tesla",
    "宋plus": "比亚迪",
    "宋pro": "比亚迪",
    "宋": "比亚迪",
    "汉ev": "比亚迪",
    "汉dm": "比亚迪",
    "汉": "比亚迪",
    "唐dm": "比亚迪",
    "唐": "比亚迪",
    "秦plus": "比亚迪",
    "秦": "比亚迪",
    "元plus": "比亚迪",
    "元": "比亚迪",
    "海豚": "比亚迪",
    "海鸥": "比亚迪",
    "id.4": "volkswagen",
    "id.6": "volkswagen",
    "tiguan": "volkswagen",
    "passat": "volkswagen",
    "golf": "volkswagen",
    "polo": "volkswagen",
    "tuareg": "volkswagen",
    "tuareq": "volkswagen",
    "x3": "bmw",
    "x5": "bmw",
    "x7": "bmw",
    "3 series": "bmw",
    "5 series": "bmw",
    "7 series": "bmw",
    "i4": "bmw",
    "ix": "bmw",
    "a4": "audi",
    "a6": "audi",
    "a8": "audi",
    "q3": "audi",
    "q5": "audi",
    "q7": "audi",
    "q8": "audi",
    "e-tron": "audi",
    "gle": "mercedes-benz",
    "glc": "mercedes-benz",
    "gls": "mercedes-benz",
    "c-class": "mercedes-benz",
    "e-class": "mercedes-benz",
    "s-class": "mercedes-benz",
    "eqe": "mercedes-benz",
    "eqs": "mercedes-benz",
    "cayenne": "porsche",
    "macan": "porsche",
    "panamera": "porsche",
    "911": "porsche",
    "taycan": "porsche",
    "mustang": "ford",
    "f-150": "ford",
    "explorer": "ford",
    "escape": "ford",
    "bronco": "ford",
    "l9": "理想",
    "l8": "理想",
    "l7": "理想",
    "l6": "理想",
    "理想one": "理想",
    "et7": "nio",
    "et5": "nio",
    "es6": "nio",
    "es8": "nio",
    "ec6": "nio",
    "p7": "xpeng",
    "g9": "xpeng",
    "g6": "xpeng",
    "p5": "xpeng",
    "iphone": "apple",
    "iphone 14": "apple",
    "iphone 15": "apple",
    "ipad": "apple",
    "macbook": "apple",
    "galaxy": "samsung",
    "galaxy s24": "samsung",
    "mate": "huawei",
    "p50": "huawei",
    "p60": "huawei",
    "mi 14": "xiaomi",
    "redmi": "xiaomi",
}


def discover_products_in_text(
    text: str,
    vertical: str = "",
) -> List[Dict[str, str]]:
    products: List[Dict[str, str]] = []
    seen_products: set = set()

    if is_list_format(text):
        items = split_into_list_items(text)
        for item in items:
            extracted = extract_primary_entities_from_list_item(item)
            product_name = extracted.get("primary_product")
            brand_name = extracted.get("primary_brand")
            if product_name and product_name.lower() not in seen_products:
                parent_brand = _find_parent_brand(product_name, brand_name)
                products.append({
                    "name": product_name,
                    "parent_brand": parent_brand,
                })
                seen_products.add(product_name.lower())
    else:
        for product in KNOWN_PRODUCTS:
            if product.lower() in text.lower() and product.lower() not in seen_products:
                parent_brand = _find_parent_brand(product, None)
                display_name = _format_product_name(product)
                products.append({
                    "name": display_name,
                    "parent_brand": parent_brand,
                })
                seen_products.add(product.lower())

    return products


def _find_parent_brand(
    product_name: str,
    context_brand: str | None,
    extraction_relationships: Optional[Dict[str, str]] = None,
) -> str:
    if extraction_relationships:
        if product_name in extraction_relationships:
            return extraction_relationships[product_name]
        product_lower = product_name.lower()
        for product, brand in extraction_relationships.items():
            if product.lower() == product_lower:
                return brand

    product_lower = product_name.lower()
    if product_lower in BRAND_PRODUCT_MAP:
        return BRAND_PRODUCT_MAP[product_lower]
    if context_brand:
        return context_brand
    return ""


def _format_product_name(name: str) -> str:
    chinese_display = {
        "宋plus": "宋PLUS", "汉ev": "汉EV", "秦plus": "秦PLUS",
        "元plus": "元PLUS", "宋pro": "宋Pro", "唐dm": "唐DM", "汉dm": "汉DM",
    }
    if name.lower() in chinese_display:
        return chinese_display[name.lower()]
    if len(name) <= 4 and name.isascii():
        return name.upper()
    return name.title()


def get_or_create_product(
    db: Session,
    vertical_id: int,
    product_name: str,
    brand_id: Optional[int] = None,
) -> Product:
    display_name = _format_product_name(product_name)
    existing = (
        db.query(Product)
        .filter(
            Product.vertical_id == vertical_id,
            Product.display_name == display_name,
        )
        .first()
    )
    if existing:
        if brand_id and not existing.brand_id:
            existing.brand_id = brand_id
            db.flush()
        return existing

    product = _upsert_product(db, vertical_id, display_name, product_name, brand_id)
    if product:
        return product
    try:
        created = Product(
            vertical_id=vertical_id,
            brand_id=brand_id,
            display_name=display_name,
            original_name=product_name,
            is_user_input=False,
        )
        db.add(created)
        db.flush()
        return created
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(Product)
            .filter(Product.vertical_id == vertical_id, Product.display_name == display_name)
            .first()
        )
        if not existing:
            raise
        if brand_id and not existing.brand_id:
            existing.brand_id = brand_id
            db.flush()
        return existing


def _upsert_product(
    db: Session,
    vertical_id: int,
    display_name: str,
    original_name: str,
    brand_id: Optional[int],
) -> Product | None:
    if db.get_bind().dialect.name != "postgresql":
        return None
    from sqlalchemy.dialects.postgresql import insert

    stmt = insert(Product).values(
        vertical_id=vertical_id,
        display_name=display_name,
        original_name=original_name,
        brand_id=brand_id,
        is_user_input=False,
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["vertical_id", "display_name"])
    db.execute(stmt)
    db.flush()
    existing = (
        db.query(Product)
        .filter(Product.vertical_id == vertical_id, Product.display_name == display_name)
        .first()
    )
    if not existing:
        return None
    if brand_id and not existing.brand_id:
        existing.brand_id = brand_id
        db.flush()
    return existing


def link_product_to_brand(db: Session, product_id: int, brand_id: int) -> None:
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        product.brand_id = brand_id
        db.flush()


def find_brand_for_product(
    db: Session,
    vertical_id: int,
    product_name: str,
) -> Optional[Brand]:
    parent_brand_name = _find_parent_brand(product_name, None)
    if not parent_brand_name:
        return None

    brand = (
        db.query(Brand)
        .filter(
            Brand.vertical_id == vertical_id,
            Brand.display_name.ilike(f"%{parent_brand_name}%"),
        )
        .first()
    )
    return brand


def discover_and_store_products(
    db: Session,
    vertical_id: int,
    text: str,
    brands: List[Brand],
    extraction_relationships: Optional[Dict[str, str]] = None,
    knowledge_cache: Optional[Dict[str, str]] = None,
) -> List[Product]:
    discovered = discover_products_in_text(text)
    products: List[Product] = []

    if knowledge_cache is None:
        knowledge_cache = _load_knowledge_cache(db, vertical_id)

    brand_name_to_id = {b.display_name.lower(): b.id for b in brands}
    for b in brands:
        if b.original_name:
            brand_name_to_id[b.original_name.lower()] = b.id
        aliases = b.aliases or {}
        for alias in aliases.get("en", []) + aliases.get("zh", []):
            if alias:
                brand_name_to_id[alias.lower()] = b.id

    for item in discovered:
        product_name = item["name"]
        parent_brand = item["parent_brand"]

        brand_id = None
        if parent_brand:
            brand_id = brand_name_to_id.get(parent_brand.lower())

        if not brand_id and extraction_relationships:
            extracted_brand = _lookup_relationship(product_name, extraction_relationships)
            if extracted_brand:
                brand_id = brand_name_to_id.get(extracted_brand.lower())

        if not brand_id and knowledge_cache:
            knowledge_brand = _lookup_relationship(product_name, knowledge_cache)
            if knowledge_brand:
                brand_id = brand_name_to_id.get(knowledge_brand.lower())
                if brand_id:
                    logger.debug(f"[ProductDiscovery] Matched {product_name} to {knowledge_brand} from knowledge base")

        if not brand_id and parent_brand:
            brand = find_brand_for_product(db, vertical_id, product_name)
            if brand:
                brand_id = brand.id

        product = get_or_create_product(
            db=db,
            vertical_id=vertical_id,
            product_name=product_name,
            brand_id=brand_id,
        )
        products.append(product)

    return products


def _load_knowledge_cache(db: Session, vertical_id: int) -> Dict[str, str]:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        return {}
    try:
        from services.knowledge_lookup import build_mapping_cache
        return build_mapping_cache(vertical.name)
    except Exception as e:
        logger.warning(f"[ProductDiscovery] Failed to load knowledge cache: {e}")
        return {}


def _lookup_relationship(
    product_name: str,
    extraction_relationships: Dict[str, str],
) -> Optional[str]:
    if product_name in extraction_relationships:
        return extraction_relationships[product_name]
    product_lower = product_name.lower()
    for product, brand in extraction_relationships.items():
        if product.lower() == product_lower:
            return brand
    return None
