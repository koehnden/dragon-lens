import json
import logging
from datetime import datetime
from typing import Callable

from src.constants.wikidata_industries import PREDEFINED_INDUSTRIES
from src.models.wikidata_cache import (
    WikidataEntity,
    WikidataIndustry,
    WikidataLoadStatus,
    get_wikidata_session,
)
from src.services.wikidata_sparql import (
    query_automobile_manufacturers,
    query_automobile_models,
    query_brands_for_industry,
    query_cosmetics_brands,
    query_luxury_brands,
    query_products_for_brand,
    query_smartphone_brands,
    query_sportswear_brands,
    search_industries,
)

logger = logging.getLogger(__name__)


def load_industry(
    industry_key: str,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    if industry_key not in PREDEFINED_INDUSTRIES:
        return {"success": False, "error": f"Unknown industry: {industry_key}"}

    industry_config = PREDEFINED_INDUSTRIES[industry_key]
    session = get_wikidata_session()

    try:
        industry = _get_or_create_industry(session, industry_key, industry_config)
        _update_load_status(session, industry.id, "loading")

        if progress_callback:
            progress_callback(f"Loading brands for {industry_config['name_en']}...")

        brands = _load_brands_for_industry(session, industry, industry_key)

        if progress_callback:
            progress_callback(f"Loaded {len(brands)} brands, now loading products...")

        products = _load_products_for_industry(session, industry, industry_key, brands)

        _update_load_status(
            session, industry.id, "complete",
            brands_count=len(brands), products_count=len(products)
        )

        session.commit()

        return {
            "success": True,
            "industry": industry_config["name_en"],
            "brands_count": len(brands),
            "products_count": len(products),
        }

    except Exception as e:
        logger.error(f"Failed to load industry {industry_key}: {e}")
        session.rollback()
        if industry:
            _update_load_status(session, industry.id, "error", error_message=str(e))
            session.commit()
        return {"success": False, "error": str(e)}

    finally:
        session.close()


def load_all_predefined_industries(
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    results = {}
    for industry_key in PREDEFINED_INDUSTRIES.keys():
        if progress_callback:
            progress_callback(f"\n=== Loading {industry_key} ===")
        result = load_industry(industry_key, progress_callback)
        results[industry_key] = result
    return results


def load_custom_industry(
    wikidata_id: str,
    name_en: str,
    name_zh: str = "",
    keywords: list[str] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    session = get_wikidata_session()

    try:
        existing = session.query(WikidataIndustry).filter(
            WikidataIndustry.wikidata_id == wikidata_id
        ).first()

        if existing:
            return {"success": False, "error": f"Industry {wikidata_id} already loaded"}

        industry = WikidataIndustry(
            wikidata_id=wikidata_id,
            name_en=name_en,
            name_zh=name_zh,
            keywords=",".join(keywords) if keywords else "",
        )
        session.add(industry)
        session.flush()

        load_status = WikidataLoadStatus(
            industry_id=industry.id,
            status="loading",
            started_at=datetime.utcnow(),
        )
        session.add(load_status)
        session.flush()

        if progress_callback:
            progress_callback(f"Loading brands for {name_en}...")

        brands_data = query_brands_for_industry(wikidata_id)
        brands = _save_entities(session, brands_data, industry.id)

        if progress_callback:
            progress_callback(f"Loaded {len(brands)} brands")

        load_status.status = "complete"
        load_status.brands_count = len(brands)
        load_status.completed_at = datetime.utcnow()

        session.commit()

        return {
            "success": True,
            "industry": name_en,
            "brands_count": len(brands),
            "products_count": 0,
        }

    except Exception as e:
        logger.error(f"Failed to load custom industry {wikidata_id}: {e}")
        session.rollback()
        return {"success": False, "error": str(e)}

    finally:
        session.close()


def search_wikidata_industries(search_term: str) -> list[dict]:
    return search_industries(search_term)


def get_load_status() -> list[dict]:
    session = get_wikidata_session()
    try:
        statuses = session.query(WikidataLoadStatus).join(WikidataIndustry).all()

        results = []
        for status in statuses:
            results.append({
                "industry": status.industry.name_en,
                "wikidata_id": status.industry.wikidata_id,
                "status": status.status,
                "brands_count": status.brands_count,
                "products_count": status.products_count,
                "completed_at": status.completed_at.isoformat() if status.completed_at else None,
                "error_message": status.error_message,
            })

        for key, config in PREDEFINED_INDUSTRIES.items():
            if not any(r["wikidata_id"] == config["wikidata_id"] for r in results):
                results.append({
                    "industry": config["name_en"],
                    "wikidata_id": config["wikidata_id"],
                    "status": "not_loaded",
                    "brands_count": 0,
                    "products_count": 0,
                    "completed_at": None,
                    "error_message": None,
                })

        return results

    finally:
        session.close()


def _get_or_create_industry(session, industry_key: str, config: dict) -> WikidataIndustry:
    industry = session.query(WikidataIndustry).filter(
        WikidataIndustry.wikidata_id == config["wikidata_id"]
    ).first()

    if not industry:
        industry = WikidataIndustry(
            wikidata_id=config["wikidata_id"],
            name_en=config["name_en"],
            name_zh=config.get("name_zh", ""),
            keywords=",".join(config.get("keywords", [])),
        )
        session.add(industry)
        session.flush()

    return industry


def _update_load_status(
    session,
    industry_id: int,
    status: str,
    brands_count: int = 0,
    products_count: int = 0,
    error_message: str = None,
):
    load_status = session.query(WikidataLoadStatus).filter(
        WikidataLoadStatus.industry_id == industry_id
    ).first()

    if not load_status:
        load_status = WikidataLoadStatus(industry_id=industry_id)
        session.add(load_status)

    load_status.status = status

    if status == "loading":
        load_status.started_at = datetime.utcnow()
    elif status == "complete":
        load_status.completed_at = datetime.utcnow()
        load_status.brands_count = brands_count
        load_status.products_count = products_count
    elif status == "error":
        load_status.error_message = error_message

    session.flush()


def _load_brands_for_industry(session, industry: WikidataIndustry, industry_key: str) -> list:
    if industry_key == "automotive":
        brands_data = query_automobile_manufacturers()
    elif industry_key == "consumer_electronics":
        brands_data = query_smartphone_brands()
    elif industry_key == "cosmetics":
        brands_data = query_cosmetics_brands()
    elif industry_key == "sportswear":
        brands_data = query_sportswear_brands()
    elif industry_key == "luxury_goods":
        brands_data = query_luxury_brands()
    else:
        brands_data = query_brands_for_industry(industry.wikidata_id)

    return _save_entities(session, brands_data, industry.id)


def _load_products_for_industry(
    session,
    industry: WikidataIndustry,
    industry_key: str,
    brands: list[WikidataEntity],
) -> list:
    if industry_key == "automotive":
        products_data = query_automobile_models()
        return _save_products_with_parent_lookup(session, products_data, industry.id)

    return []


def _save_entities(session, entities_data: list[dict], industry_id: int) -> list[WikidataEntity]:
    saved = []
    seen_ids = set()

    for data in entities_data:
        wikidata_id = data["wikidata_id"]

        if wikidata_id in seen_ids:
            continue

        existing = session.query(WikidataEntity).filter(
            WikidataEntity.wikidata_id == wikidata_id
        ).first()

        if existing:
            seen_ids.add(wikidata_id)
            continue

        entity = WikidataEntity(
            wikidata_id=wikidata_id,
            entity_type=data["entity_type"],
            industry_id=industry_id,
            name_en=data.get("name_en", ""),
            name_zh=data.get("name_zh", ""),
            aliases_en=json.dumps(data.get("aliases_en", [])),
            aliases_zh=json.dumps(data.get("aliases_zh", [])),
        )
        session.add(entity)
        saved.append(entity)
        seen_ids.add(wikidata_id)

    session.flush()
    return saved


def _save_products_with_parent_lookup(
    session,
    products_data: list[dict],
    industry_id: int,
) -> list[WikidataEntity]:
    saved = []
    seen_ids = set()

    brand_cache = {}
    brands = session.query(WikidataEntity).filter(
        WikidataEntity.industry_id == industry_id,
        WikidataEntity.entity_type == "brand",
    ).all()
    for brand in brands:
        brand_cache[brand.wikidata_id] = brand.id

    for data in products_data:
        wikidata_id = data["wikidata_id"]

        if wikidata_id in seen_ids:
            continue

        existing = session.query(WikidataEntity).filter(
            WikidataEntity.wikidata_id == wikidata_id
        ).first()

        if existing:
            seen_ids.add(wikidata_id)
            continue

        parent_brand_id = None
        parent_wikidata_id = data.get("parent_brand_wikidata_id")
        if parent_wikidata_id and parent_wikidata_id in brand_cache:
            parent_brand_id = brand_cache[parent_wikidata_id]

        entity = WikidataEntity(
            wikidata_id=wikidata_id,
            entity_type="product",
            industry_id=industry_id,
            parent_brand_id=parent_brand_id,
            name_en=data.get("name_en", ""),
            name_zh=data.get("name_zh", ""),
            aliases_en="[]",
            aliases_zh="[]",
        )
        session.add(entity)
        saved.append(entity)
        seen_ids.add(wikidata_id)

    session.flush()
    return saved
