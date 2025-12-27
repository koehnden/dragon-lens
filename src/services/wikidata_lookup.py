import json
import logging
from functools import lru_cache

from src.constants.wikidata_industries import find_industry_by_keyword
from src.models.wikidata_cache import WikidataEntity, WikidataIndustry, get_wikidata_session

logger = logging.getLogger(__name__)


def get_entities_for_vertical(vertical: str) -> dict:
    industry_key = find_industry_by_keyword(vertical)
    if not industry_key:
        return {"brands": [], "products": []}

    session = get_wikidata_session()
    try:
        industry = _find_industry_by_key(session, industry_key)
        if not industry:
            return {"brands": [], "products": []}

        brands = _get_entities_by_type(session, industry.id, "brand")
        products = _get_entities_by_type(session, industry.id, "product")

        return {"brands": brands, "products": products}

    finally:
        session.close()


def lookup_brand(name: str, vertical: str = None) -> dict | None:
    session = get_wikidata_session()
    try:
        query = session.query(WikidataEntity).filter(
            WikidataEntity.entity_type == "brand"
        )

        if vertical:
            industry_key = find_industry_by_keyword(vertical)
            if industry_key:
                industry = _find_industry_by_key(session, industry_key)
                if industry:
                    query = query.filter(WikidataEntity.industry_id == industry.id)

        entities = query.all()
        return _find_matching_entity(entities, name)

    finally:
        session.close()


def lookup_product(name: str, vertical: str = None) -> dict | None:
    session = get_wikidata_session()
    try:
        query = session.query(WikidataEntity).filter(
            WikidataEntity.entity_type == "product"
        )

        if vertical:
            industry_key = find_industry_by_keyword(vertical)
            if industry_key:
                industry = _find_industry_by_key(session, industry_key)
                if industry:
                    query = query.filter(WikidataEntity.industry_id == industry.id)

        entities = query.all()
        return _find_matching_entity(entities, name)

    finally:
        session.close()


def get_brand_names_for_vertical(vertical: str) -> set[str]:
    entities = get_entities_for_vertical(vertical)
    names = set()
    for brand in entities["brands"]:
        names.add(brand["name_en"].lower())
        if brand["name_zh"]:
            names.add(brand["name_zh"])
        names.update(a.lower() for a in brand["aliases_en"])
        names.update(brand["aliases_zh"])
    return names


def get_product_names_for_vertical(vertical: str) -> set[str]:
    entities = get_entities_for_vertical(vertical)
    names = set()
    for product in entities["products"]:
        names.add(product["name_en"].lower())
        if product["name_zh"]:
            names.add(product["name_zh"])
        names.update(a.lower() for a in product["aliases_en"])
        names.update(product["aliases_zh"])
    return names


def is_known_brand(name: str, vertical: str) -> bool:
    known_brands = get_brand_names_for_vertical(vertical)
    return name.lower() in known_brands


def is_known_product(name: str, vertical: str) -> bool:
    known_products = get_product_names_for_vertical(vertical)
    return name.lower() in known_products


def get_cache_available() -> bool:
    session = get_wikidata_session()
    try:
        count = session.query(WikidataEntity).limit(1).count()
        return count > 0
    except Exception:
        return False
    finally:
        session.close()


def _find_industry_by_key(session, industry_key: str) -> WikidataIndustry | None:
    from src.constants.wikidata_industries import PREDEFINED_INDUSTRIES

    config = PREDEFINED_INDUSTRIES.get(industry_key)
    if not config:
        return None

    return session.query(WikidataIndustry).filter(
        WikidataIndustry.wikidata_id == config["wikidata_id"]
    ).first()


def _get_entities_by_type(session, industry_id: int, entity_type: str) -> list[dict]:
    entities = session.query(WikidataEntity).filter(
        WikidataEntity.industry_id == industry_id,
        WikidataEntity.entity_type == entity_type,
    ).all()

    return [_entity_to_dict(e) for e in entities]


def _entity_to_dict(entity: WikidataEntity) -> dict:
    return {
        "wikidata_id": entity.wikidata_id,
        "name_en": entity.name_en,
        "name_zh": entity.name_zh,
        "aliases_en": json.loads(entity.aliases_en) if entity.aliases_en else [],
        "aliases_zh": json.loads(entity.aliases_zh) if entity.aliases_zh else [],
        "entity_type": entity.entity_type,
    }


def _find_matching_entity(entities: list[WikidataEntity], name: str) -> dict | None:
    name_lower = name.lower().strip()

    for entity in entities:
        if _matches_entity_name(entity, name_lower):
            return _entity_to_dict(entity)

    return None


def _matches_entity_name(entity: WikidataEntity, name_lower: str) -> bool:
    if entity.name_en.lower() == name_lower:
        return True

    if entity.name_zh and entity.name_zh == name_lower:
        return True

    aliases_en = json.loads(entity.aliases_en) if entity.aliases_en else []
    if any(a.lower() == name_lower for a in aliases_en):
        return True

    aliases_zh = json.loads(entity.aliases_zh) if entity.aliases_zh else []
    if any(a == name_lower for a in aliases_zh):
        return True

    return False
