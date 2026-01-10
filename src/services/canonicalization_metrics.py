import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from models import (
    Brand,
    BrandAlias,
    CanonicalBrand,
    CanonicalProduct,
    Product,
    ProductAlias,
    Vertical,
)
from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
)
from services.knowledge_session import knowledge_session
from services.knowledge_verticals import resolve_knowledge_vertical_id


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


def build_user_brand_variant_set(db: Session, vertical_id: int) -> Set[str]:
    result: Set[str] = set()
    for brand in _user_brands(db, vertical_id):
        for variant in _brand_variants(brand):
            _add_variant_set(result, variant)
    return result


def resolve_user_brand_display_name(
    name: str, exact: Dict[str, str], normalized: Dict[str, str]
) -> Optional[str]:
    if key := exact.get((name or "").casefold()):
        return key
    if key := normalized.get(normalize_entity_key(name)):
        return key
    return _check_substring_match(name, exact, normalized)


def _check_substring_match(
    name: str, exact: Dict[str, str], normalized: Dict[str, str]
) -> Optional[str]:
    name_lower = (name or "").casefold()
    if not name_lower:
        return None
    for variant, brand_name in exact.items():
        if name_lower in variant or variant in name_lower:
            return brand_name
    return None


def build_brand_canonical_maps(db: Session, vertical_id: int) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        canon, alias = _brand_maps(knowledge_db, knowledge_id, db, vertical_id)
        return canon, alias, _normalized_brand_map(canon, alias)


def build_product_canonical_maps(db: Session, vertical_id: int) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        canon, alias = _product_maps(knowledge_db, knowledge_id, db, vertical_id)
        return canon, alias, _normalized_brand_map(canon, alias)


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
    if key := _check_substring_match(name, user_exact, user_norm):
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


def _add_variant_set(result: Set[str], variant: str) -> None:
    if not variant:
        return
    result.add(variant)
    result.add(variant.casefold())
    result.add(normalize_entity_key(variant))


def _brand_variants(brand: Brand) -> Iterable[str]:
    aliases = brand.aliases or {}
    yield brand.display_name
    yield brand.original_name
    yield brand.translated_name or ""
    for v in (aliases.get("zh") or []) + (aliases.get("en") or []):
        yield v


def _knowledge_vertical_id(knowledge_db: Session, db: Session, vertical_id: int) -> int | None:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        return None
    return resolve_knowledge_vertical_id(knowledge_db, vertical.name)


def _brand_maps(
    knowledge_db: Session,
    vertical_id: int | None,
    db: Session,
    legacy_vertical_id: int,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    if not vertical_id:
        return _legacy_brand_maps(db, legacy_vertical_id)
    return _canonical_brand_map(knowledge_db, vertical_id), _brand_alias_map(knowledge_db, vertical_id)


def _product_maps(
    knowledge_db: Session,
    vertical_id: int | None,
    db: Session,
    legacy_vertical_id: int,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    if not vertical_id:
        return _legacy_product_maps(db, legacy_vertical_id)
    return _canonical_product_map(knowledge_db, vertical_id), _product_alias_map(knowledge_db, vertical_id)


def _canonical_brand_map(knowledge_db: Session, vertical_id: int) -> Dict[str, str]:
    rows = knowledge_db.query(KnowledgeBrand).filter(
        KnowledgeBrand.vertical_id == vertical_id
    ).all()
    return {r.canonical_name.casefold(): r.canonical_name for r in rows if r.canonical_name}


def _brand_alias_map(knowledge_db: Session, vertical_id: int) -> Dict[str, str]:
    rows = knowledge_db.query(KnowledgeBrandAlias).join(KnowledgeBrand).filter(
        KnowledgeBrand.vertical_id == vertical_id
    ).all()
    return {r.alias.casefold(): r.brand.canonical_name for r in rows if r.alias and r.brand}


def _canonical_product_map(knowledge_db: Session, vertical_id: int) -> Dict[str, str]:
    rows = knowledge_db.query(KnowledgeProduct).filter(
        KnowledgeProduct.vertical_id == vertical_id
    ).all()
    return {r.canonical_name.casefold(): r.canonical_name for r in rows if r.canonical_name}


def _product_alias_map(knowledge_db: Session, vertical_id: int) -> Dict[str, str]:
    rows = knowledge_db.query(KnowledgeProductAlias).join(KnowledgeProduct).filter(
        KnowledgeProduct.vertical_id == vertical_id
    ).all()
    return {r.alias.casefold(): r.product.canonical_name for r in rows if r.alias and r.product}


def _legacy_brand_maps(db: Session, vertical_id: int) -> Tuple[Dict[str, str], Dict[str, str]]:
    return _legacy_canonical_brand_map(db, vertical_id), _legacy_brand_alias_map(db, vertical_id)


def _legacy_product_maps(db: Session, vertical_id: int) -> Tuple[Dict[str, str], Dict[str, str]]:
    return _legacy_canonical_product_map(db, vertical_id), _legacy_product_alias_map(db, vertical_id)


def _legacy_canonical_brand_map(db: Session, vertical_id: int) -> Dict[str, str]:
    rows = db.query(CanonicalBrand).filter(CanonicalBrand.vertical_id == vertical_id).all()
    return {r.canonical_name.casefold(): r.canonical_name for r in rows if r.canonical_name}


def _legacy_brand_alias_map(db: Session, vertical_id: int) -> Dict[str, str]:
    rows = db.query(BrandAlias).join(CanonicalBrand).filter(CanonicalBrand.vertical_id == vertical_id).all()
    return {r.alias.casefold(): r.canonical_brand.canonical_name for r in rows if r.alias and r.canonical_brand}


def _legacy_canonical_product_map(db: Session, vertical_id: int) -> Dict[str, str]:
    rows = db.query(CanonicalProduct).filter(CanonicalProduct.vertical_id == vertical_id).all()
    return {r.canonical_name.casefold(): r.canonical_name for r in rows if r.canonical_name}


def _legacy_product_alias_map(db: Session, vertical_id: int) -> Dict[str, str]:
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
