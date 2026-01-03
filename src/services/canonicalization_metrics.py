import re
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from models import (
    Brand,
    BrandAlias,
    CanonicalBrand,
    CanonicalProduct,
    Product,
    ProductAlias,
)


def normalize_entity_key(text: str) -> str:
    cleaned = _drop_parenthetical((text or "").strip())
    cleaned = re.sub(r"[\s\W_]+", "", cleaned, flags=re.UNICODE)
    return cleaned.casefold()


def build_user_brand_variant_maps(db: Session, vertical_id: int) -> Tuple[Dict[str, str], Dict[str, str]]:
    brands = _user_brands(db, vertical_id)
    exact: Dict[str, str] = {}
    normalized: Dict[str, str] = {}
    for b in brands:
        _add_user_brand_variants(exact, normalized, b)
    return exact, normalized


def build_brand_canonical_maps(db: Session, vertical_id: int) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    canon = _canonical_brand_map(db, vertical_id)
    alias = _brand_alias_map(db, vertical_id)
    norm = _normalized_brand_map(canon, alias)
    return canon, alias, norm


def build_product_canonical_maps(db: Session, vertical_id: int) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    canon = _canonical_product_map(db, vertical_id)
    alias = _product_alias_map(db, vertical_id)
    norm = _normalized_brand_map(canon, alias)
    return canon, alias, norm


def resolve_brand_key(
    name: str,
    user_exact: Dict[str, str],
    user_norm: Dict[str, str],
    canonical_lower: Dict[str, str],
    alias_lower: Dict[str, str],
    canonical_norm: Dict[str, str],
) -> Optional[str]:
    if key := user_exact.get((name or "").casefold()):
        return key
    if key := user_norm.get(normalize_entity_key(name)):
        return key
    return resolve_canonical_key(name, canonical_lower, alias_lower, canonical_norm)


def resolve_canonical_key(
    name: str,
    canonical_lower: Dict[str, str],
    alias_lower: Dict[str, str],
    canonical_norm: Dict[str, str],
) -> Optional[str]:
    lowered = (name or "").casefold()
    if key := canonical_lower.get(lowered):
        return key
    if key := alias_lower.get(lowered):
        return key
    return canonical_norm.get(normalize_entity_key(name))


def choose_brand_rep(brands: List[Brand]) -> Brand:
    if not brands:
        raise ValueError("brands must not be empty")
    return sorted(brands, key=_brand_rep_sort_key)[0]


def choose_product_rep(products: List[Product]) -> Product:
    if not products:
        raise ValueError("products must not be empty")
    return sorted(products, key=_product_rep_sort_key)[0]


def _drop_parenthetical(text: str) -> str:
    text = re.sub(r"\(.*?\)", "", text)
    return re.sub(r"（.*?）", "", text)


def _user_brands(db: Session, vertical_id: int) -> List[Brand]:
    return db.query(Brand).filter(Brand.vertical_id == vertical_id, Brand.is_user_input == True).all()


def _add_user_brand_variants(exact: Dict[str, str], normalized: Dict[str, str], brand: Brand) -> None:
    for v in _brand_variants(brand):
        if not v:
            continue
        exact.setdefault(v.casefold(), brand.display_name)
        normalized.setdefault(normalize_entity_key(v), brand.display_name)


def _brand_variants(brand: Brand) -> Iterable[str]:
    aliases = brand.aliases or {}
    yield brand.display_name
    yield brand.original_name
    yield brand.translated_name or ""
    for v in (aliases.get("zh") or []) + (aliases.get("en") or []):
        yield v


def _canonical_brand_map(db: Session, vertical_id: int) -> Dict[str, str]:
    rows = db.query(CanonicalBrand).filter(CanonicalBrand.vertical_id == vertical_id).all()
    return {r.canonical_name.casefold(): r.canonical_name for r in rows if r.canonical_name}


def _brand_alias_map(db: Session, vertical_id: int) -> Dict[str, str]:
    rows = db.query(BrandAlias).join(CanonicalBrand).filter(CanonicalBrand.vertical_id == vertical_id).all()
    return {r.alias.casefold(): r.canonical_brand.canonical_name for r in rows if r.alias and r.canonical_brand}


def _canonical_product_map(db: Session, vertical_id: int) -> Dict[str, str]:
    rows = db.query(CanonicalProduct).filter(CanonicalProduct.vertical_id == vertical_id).all()
    return {r.canonical_name.casefold(): r.canonical_name for r in rows if r.canonical_name}


def _product_alias_map(db: Session, vertical_id: int) -> Dict[str, str]:
    rows = db.query(ProductAlias).join(CanonicalProduct).filter(CanonicalProduct.vertical_id == vertical_id).all()
    return {r.alias.casefold(): r.canonical_product.canonical_name for r in rows if r.alias and r.canonical_product}


def _normalized_brand_map(canon: Dict[str, str], alias: Dict[str, str]) -> Dict[str, str]:
    norm: Dict[str, str] = {}
    for v in canon.values():
        norm.setdefault(normalize_entity_key(v), v)
    for a, c in alias.items():
        norm.setdefault(normalize_entity_key(a), c)
    return norm


def _brand_rep_sort_key(brand: Brand) -> tuple:
    return (not brand.is_user_input, len(brand.display_name or ""), brand.display_name or "")


def _product_rep_sort_key(product: Product) -> tuple:
    return (not product.is_user_input, len(product.display_name or ""), product.display_name or "")
