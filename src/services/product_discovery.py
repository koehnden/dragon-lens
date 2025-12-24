from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from models import Brand, Product
from services.brand_recognition import (
    KNOWN_BRANDS,
    KNOWN_PRODUCTS,
    GENERIC_TERMS,
    extract_primary_entities_from_list_item,
    is_list_format,
    split_into_list_items,
)


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


def _find_parent_brand(product_name: str, context_brand: str | None) -> str:
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

    product = Product(
        vertical_id=vertical_id,
        brand_id=brand_id,
        display_name=display_name,
        original_name=product_name,
        is_user_input=False,
    )
    db.add(product)
    db.flush()
    return product


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
) -> List[Product]:
    discovered = discover_products_in_text(text)
    products: List[Product] = []

    brand_name_to_id = {b.display_name.lower(): b.id for b in brands}
    for b in brands:
        if b.original_name:
            brand_name_to_id[b.original_name.lower()] = b.id
        if b.translated_name:
            brand_name_to_id[b.translated_name.lower()] = b.id

    for item in discovered:
        product_name = item["name"]
        parent_brand = item["parent_brand"]

        brand_id = None
        if parent_brand:
            brand_id = brand_name_to_id.get(parent_brand.lower())

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
