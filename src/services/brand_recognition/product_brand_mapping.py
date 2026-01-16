import json
import logging
import os
from typing import Dict, List, Optional

from sqlalchemy import case, func

from services.canonicalization_metrics import normalize_entity_key
from services.brand_recognition.list_processor import (
    is_list_format,
    split_into_list_items,
)
from services.brand_recognition.prompts import load_prompt
from services.brand_recognition.text_utils import _parse_json_response
from services.knowledge_session import knowledge_session
from services.knowledge_verticals import resolve_knowledge_vertical_id, get_or_create_vertical
from models import EntityType, RejectedEntity, Vertical
from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeProduct,
    KnowledgeProductBrandMapping,
    KnowledgeRejectedEntity,
)

logger = logging.getLogger(__name__)

from config import settings

MIN_CONFIDENCE = float(os.getenv("MAPPING_CONFIDENCE_THRESHOLD", "0.7"))
MIN_PROXIMITY_SHARE = float(os.getenv("MAPPING_PROXIMITY_SHARE", "0.6"))
MIN_PROXIMITY_COUNT = int(os.getenv("MAPPING_MIN_COUNT", "1"))
QWEN_CONFIDENCE = float(os.getenv("MAPPING_QWEN_CONFIDENCE", "0.7"))
KNOWLEDGE_PERSIST_THRESHOLD = settings.knowledge_persist_threshold
KNOWLEDGE_PERSIST_ENABLED = settings.knowledge_persist_enabled
MAX_EXAMPLES = 20
AUTO_VALIDATE_SUPPORT_COUNT = int(os.getenv("MAPPING_AUTO_VALIDATE_SUPPORT_COUNT", "10"))
AUTO_VALIDATE_CONFIDENCE = float(os.getenv("MAPPING_AUTO_VALIDATE_CONFIDENCE", "0.9"))
AUTO_VALIDATE_RUNNER_UP_MIN = int(os.getenv("MAPPING_AUTO_VALIDATE_RUNNER_UP_MIN", "2"))


def map_products_to_brands(answers: List) -> Dict[str, str]:
    """Map products to brands using list proximity evidence."""
    return _select_winners(map_product_brand_counts(answers))


def map_product_brand_counts(answers: List) -> Dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for answer in answers:
        for item in _iter_items(answer.answer_text):
            _accumulate(counts, _map_item(item, answer.raw_brands, answer.raw_products))
    return counts


async def map_products_to_brands_for_run(db, run_id: int) -> Dict[str, str]:
    """Map products to brands after consolidation for a run."""
    input_data = _mapping_input(db, run_id)
    if not input_data:
        return {}
    results = await _map_products_for_input(db, input_data)
    db.flush()
    return results


def parse_product_brand_mapping_response(
    response: str,
    products: List[str],
    allowed_brands: set[str],
) -> Dict[str, str]:
    """Parse mapping response and filter unknown brands."""
    data = _parse_json_response(response) or {}
    items = data.get("mappings") or data.get("mapping") or []
    product_map = {p.lower(): p for p in products}
    allowed = {b.lower(): b for b in allowed_brands}
    return _extract_mapping(items, product_map, allowed)


def select_mapping_examples(mappings: List[dict]) -> List[dict]:
    """Select mapping examples for prompts."""
    filtered = [mapping for mapping in mappings if _is_valid_example(mapping)]
    ranked = sorted(filtered, key=_example_sort_key, reverse=True)
    return ranked[:MAX_EXAMPLES]


def build_mapping_prompt(
    product: str,
    candidate_brands: List[str],
    evidence_snippets: List[str],
    known_mappings: List[dict],
) -> str:
    """Build a mapping prompt for Qwen."""
    return load_prompt(
        "product_brand_mapping_prompt",
        product=product,
        candidate_brands=_json(candidate_brands),
        evidence_snippets=_json(evidence_snippets),
        known_mappings=_json(known_mappings),
    )


def load_mapping_examples(db, vertical_id: int) -> List[dict]:
    """Load stored mappings for prompt examples."""
    legacy = _legacy_mapping_examples(db, vertical_id)
    vertical_name = _vertical_name(db, vertical_id)
    if not vertical_name:
        return legacy
    with knowledge_session() as knowledge_db:
        knowledge_id = resolve_knowledge_vertical_id(knowledge_db, vertical_name)
        if not knowledge_id:
            return legacy
        records = _knowledge_mappings(knowledge_db, knowledge_id)
        examples = [_record_to_example(record) for record in records]
        if examples:
            return select_mapping_examples([example for example in examples if example])
        return legacy


def _iter_items(text: str) -> List[str]:
    items = split_into_list_items(text) if is_list_format(text) else []
    return items if items else [text]


def _mapping_input(db, run_id: int):
    from services.brand_recognition.consolidation_service import (
        gather_consolidation_input,
    )

    input_data = gather_consolidation_input(db, run_id)
    if not input_data.all_unique_products:
        return None
    return input_data


async def _map_products_for_input(db, input_data) -> Dict[str, str]:
    brand_lookup = _brand_lookup(db, input_data.vertical_id)
    product_lookup = _product_lookup(db, input_data.vertical_id)
    counts = map_product_brand_counts(input_data.answer_entities)
    known = load_mapping_examples(db, input_data.vertical_id)
    knowledge_cache = _load_knowledge_cache(db, input_data.vertical_id)
    results = await _map_products(
        db, input_data, counts, brand_lookup, product_lookup, known, knowledge_cache
    )
    _persist_mapping_evidence(db, input_data.vertical_id, counts, brand_lookup, product_lookup)
    return results


async def _map_products(
    db,
    input_data,
    counts: Dict[str, dict[str, int]],
    brand_lookup: Dict[str, int],
    product_lookup: Dict[str, object],
    known: List[dict],
    knowledge_cache: Dict[str, str],
) -> Dict[str, str]:
    results: Dict[str, str] = {}
    for product, brand_counts in counts.items():
        mapping = await _map_single_product(
            db, input_data, product, brand_counts, brand_lookup, product_lookup,
            known, knowledge_cache
        )
        results.update(mapping)
    return results


async def _map_single_product(
    db,
    input_data,
    product: str,
    brand_counts: dict[str, int],
    brand_lookup: Dict[str, int],
    product_lookup: Dict[str, object],
    known: List[dict],
    knowledge_cache: Dict[str, str],
) -> Dict[str, str]:
    product_record = _resolve_product(product, product_lookup)
    if not product_record:
        return {}
    validated = _validated_brand_for_product(
        db, input_data.vertical_id, product_record.original_name
    )
    if validated:
        return _apply_validated_mapping(
            db, input_data.vertical_id, product_record, validated, brand_lookup
        )
    candidate_ids = _candidate_brand_ids(brand_counts, brand_lookup)

    if candidate_ids:
        winner = _top_brand(brand_counts)
        if _is_confident_brand(winner, brand_counts):
            return _apply_mapping(
                db, input_data.vertical_id, product_record, winner,
                brand_counts, candidate_ids, "proximity"
            )
        brand = await _qwen_brand(
            product, list(candidate_ids.keys()), input_data.answer_entities, known
        )
        if brand:
            return _apply_mapping(
                db, input_data.vertical_id, product_record, brand,
                brand_counts, candidate_ids, "qwen"
            )

    knowledge_brand = _lookup_in_knowledge_cache(product, knowledge_cache)
    if knowledge_brand:
        brand_id = _resolve_brand_id(knowledge_brand, brand_lookup)
        if brand_id:
            return _apply_knowledge_mapping(
                db, input_data.vertical_id, product_record, knowledge_brand, brand_id
            )
    return {}


def _validated_brand_for_product(db, vertical_id: int, product_name: str) -> str:
    vertical_name = _vertical_name(db, vertical_id)
    if not vertical_name or not product_name:
        return ""
    with knowledge_session() as knowledge_db:
        knowledge_id = resolve_knowledge_vertical_id(knowledge_db, vertical_name)
        return _knowledge_validated_brand(knowledge_db, knowledge_id, product_name)


def _knowledge_validated_brand(
    knowledge_db, vertical_id: int | None, product_name: str
) -> str:
    if not vertical_id:
        return ""
    product = _knowledge_product(knowledge_db, vertical_id, product_name)
    if not product:
        return ""
    mapping = _knowledge_validated_mapping(knowledge_db, vertical_id, product.id)
    if not mapping:
        return ""
    brand = (
        knowledge_db.query(KnowledgeBrand)
        .filter(KnowledgeBrand.id == mapping.brand_id)
        .first()
    )
    return brand.canonical_name if brand else ""


def _knowledge_product(knowledge_db, vertical_id: int, name: str):
    return (
        knowledge_db.query(KnowledgeProduct)
        .filter(
            KnowledgeProduct.vertical_id == vertical_id,
            func.lower(KnowledgeProduct.canonical_name) == name.casefold(),
        )
        .first()
    )


def _knowledge_validated_mapping(knowledge_db, vertical_id: int, product_id: int):
    return (
        knowledge_db.query(KnowledgeProductBrandMapping)
        .filter(
            KnowledgeProductBrandMapping.vertical_id == vertical_id,
            KnowledgeProductBrandMapping.product_id == product_id,
            KnowledgeProductBrandMapping.is_validated.is_(True),
        )
        .order_by(
            case((KnowledgeProductBrandMapping.source == "feedback", 1), else_=0).desc(),
            KnowledgeProductBrandMapping.support_count.desc(),
            KnowledgeProductBrandMapping.confidence.desc(),
            KnowledgeProductBrandMapping.updated_at.desc(),
        )
        .first()
    )


def _apply_validated_mapping(
    db,
    vertical_id: int,
    product,
    brand_name: str,
    brand_lookup: Dict[str, int],
) -> Dict[str, str]:
    brand_id = _resolve_brand_id(brand_name, brand_lookup)
    if not brand_id:
        return {}
    _force_mapping(db, vertical_id, product.id, brand_id, "knowledge_validated")
    product.brand_id = brand_id
    return {product.display_name: brand_name}


def _force_mapping(db, vertical_id: int, product_id: int, brand_id: int, source: str):
    mapping = _existing_mapping(db, vertical_id, product_id)
    if not mapping:
        mapping = _new_mapping(vertical_id, product_id, brand_id, 1.0, source)
        db.add(mapping)
        return mapping
    return _update_mapping(mapping, brand_id, 1.0, source)


def _brand_lookup(db, vertical_id: int) -> Dict[str, int]:
    from models import Brand

    brands = db.query(Brand).filter(Brand.vertical_id == vertical_id).all()
    rejected = _rejected_brand_names(db, vertical_id)
    return _brand_variant_map(brands, rejected)


def _product_lookup(db, vertical_id: int) -> Dict[str, object]:
    from models import Product

    products = db.query(Product).filter(Product.vertical_id == vertical_id).all()
    lookup: Dict[str, object] = {}
    for product in products:
        _add_product_variant(lookup, product.display_name, product)
        _add_product_variant(lookup, product.original_name, product)
    return lookup


def _rejected_brand_names(db, vertical_id: int) -> set[str]:
    local = _local_rejected_brand_names(db, vertical_id)
    remote = _knowledge_rejected_brand_names(db, vertical_id)
    return local | remote


def _local_rejected_brand_names(db, vertical_id: int) -> set[str]:
    rows = (
        db.query(RejectedEntity.name)
        .filter(
            RejectedEntity.vertical_id == vertical_id,
            RejectedEntity.entity_type == EntityType.BRAND,
        )
        .all()
    )
    return {name.casefold() for (name,) in rows if name}


def _knowledge_rejected_brand_names(db, vertical_id: int) -> set[str]:
    vertical_name = _vertical_name(db, vertical_id)
    if not vertical_name:
        return set()
    try:
        with knowledge_session() as knowledge_db:
            knowledge_id = resolve_knowledge_vertical_id(knowledge_db, vertical_name)
            if not knowledge_id:
                return set()
            rows = knowledge_db.query(KnowledgeRejectedEntity.name).filter(
                KnowledgeRejectedEntity.vertical_id == knowledge_id,
                KnowledgeRejectedEntity.entity_type == EntityType.BRAND,
            ).all()
            return {name.casefold() for (name,) in rows if name}
    except Exception as e:
        logger.debug(f"[PostHocMapping] Could not load rejected brands: {e}")
        return set()


def _brand_variant_map(brands: List[object], rejected: set[str]) -> Dict[str, int]:
    lookup: Dict[str, int] = {}
    for brand in brands:
        if _brand_is_rejected(brand, rejected):
            continue
        for variant in _brand_variants(brand):
            _add_variant(lookup, variant, brand.id)
    return lookup


def _brand_is_rejected(brand, rejected: set[str]) -> bool:
    for name in _brand_variants(brand):
        if name and _name_key(name) in rejected:
            return True
    return False


def _brand_variants(brand) -> List[str]:
    aliases = brand.aliases or {}
    return (
        [brand.display_name, brand.original_name, brand.translated_name]
        + (aliases.get("zh") or [])
        + (aliases.get("en") or [])
    )


def _add_variant(lookup: Dict[str, int], variant: str | None, brand_id: int) -> None:
    if not variant:
        return
    lookup.setdefault(_name_key(variant), brand_id)
    lookup.setdefault(_norm_key(variant), brand_id)


def _add_product_variant(
    lookup: Dict[str, object], variant: str | None, product: object
) -> None:
    if not variant:
        return
    lookup.setdefault(_name_key(variant), product)
    lookup.setdefault(_norm_key(variant), product)


def _resolve_product(name: str, product_lookup: Dict[str, object]):
    return product_lookup.get(_name_key(name)) or product_lookup.get(_norm_key(name))


def _candidate_brand_ids(
    brand_counts: dict[str, int], brand_lookup: Dict[str, int]
) -> Dict[str, int]:
    candidate_ids: Dict[str, int] = {}
    for name in brand_counts:
        brand_id = _resolve_brand_id(name, brand_lookup)
        if brand_id:
            candidate_ids[name] = brand_id
    return candidate_ids


def _resolve_brand_id(name: str, brand_lookup: Dict[str, int]) -> int | None:
    return brand_lookup.get(_name_key(name)) or brand_lookup.get(_norm_key(name))


def _top_brand(brand_counts: dict[str, int]) -> str:
    return max(brand_counts, key=lambda name: (brand_counts[name], name))


def _is_confident_brand(brand: str, brand_counts: dict[str, int]) -> bool:
    total = sum(brand_counts.values())
    top = brand_counts.get(brand, 0)
    return (
        bool(total)
        and top >= MIN_PROXIMITY_COUNT
        and top / total >= MIN_PROXIMITY_SHARE
    )


def _apply_mapping(
    db,
    vertical_id: int,
    product,
    brand_name: str,
    brand_counts: dict[str, int],
    candidate_ids: Dict[str, int],
    source: str,
) -> Dict[str, str]:
    brand_id = candidate_ids.get(brand_name)
    if not brand_id:
        return {}
    confidence = _mapping_confidence(source, brand_name, brand_counts)
    _upsert_mapping(db, vertical_id, product.id, brand_id, confidence, source)
    if _should_update_product(product, brand_id, confidence):
        product.brand_id = brand_id

    return {product.display_name: brand_name}


def _mapping_confidence(
    source: str, brand_name: str, brand_counts: dict[str, int]
) -> float:
    if source == "qwen":
        return QWEN_CONFIDENCE
    return _brand_confidence(brand_name, brand_counts)


def _brand_confidence(brand: str, brand_counts: dict[str, int]) -> float:
    total = sum(brand_counts.values())
    return brand_counts.get(brand, 0) / total if total else 0.0


def _should_update_product(product, brand_id: int, confidence: float) -> bool:
    if product.brand_id is None:
        return True
    if product.brand_id == brand_id:
        return False
    return confidence >= MIN_CONFIDENCE


def _upsert_mapping(
    db,
    vertical_id: int,
    product_id: int,
    brand_id: int,
    confidence: float,
    source: str,
):
    mapping = _existing_mapping(db, vertical_id, product_id)
    if mapping and confidence <= mapping.confidence:
        return mapping
    if not mapping:
        mapping = _new_mapping(vertical_id, product_id, brand_id, confidence, source)
        db.add(mapping)
        return mapping
    return _update_mapping(mapping, brand_id, confidence, source)


def _existing_mapping(db, vertical_id: int, product_id: int):
    from models import ProductBrandMapping

    return (
        db.query(ProductBrandMapping)
        .filter(
            ProductBrandMapping.vertical_id == vertical_id,
            ProductBrandMapping.product_id == product_id,
        )
        .first()
    )


def _new_mapping(
    vertical_id: int, product_id: int, brand_id: int, confidence: float, source: str
):
    from models import ProductBrandMapping

    return ProductBrandMapping(
        vertical_id=vertical_id,
        product_id=product_id,
        brand_id=brand_id,
        confidence=confidence,
        is_validated=False,
        source=source,
    )


def _update_mapping(mapping, brand_id: int, confidence: float, source: str):
    mapping.brand_id = brand_id
    mapping.confidence = confidence
    mapping.source = source
    return mapping


async def _qwen_brand(
    product: str, candidates: List[str], answers: List[object], known: List[dict]
) -> str:
    from services.ollama import OllamaService

    snippets = _evidence_snippets(product, answers)
    prompt = build_mapping_prompt(product, candidates, snippets, known)
    ollama = OllamaService()
    response = await ollama._call_ollama(
        model=ollama.ner_model,
        prompt=prompt,
        temperature=0.0,
    )
    mapping = parse_product_brand_mapping_response(response, [product], set(candidates))
    return mapping.get(product, "")


def _evidence_snippets(product: str, answers: List[object]) -> List[str]:
    snippets: List[str] = []
    product_lower = product.lower()
    for answer in answers:
        for item in _iter_items(answer.answer_text):
            if product_lower in item.lower():
                snippets.append(item.strip())
                if len(snippets) >= 3:
                    return snippets
    return snippets


def _map_item(item: str, brands: List[str], products: List[str]) -> Dict[str, str]:
    item_lower = item.lower()
    brand_positions = _positions(item_lower, brands)
    if not brand_positions:
        return {}
    mapping: Dict[str, str] = {}
    for product in products:
        brand = _match_brand(item_lower, product, brand_positions)
        if brand:
            mapping[product] = brand
    return mapping


def _positions(text_lower: str, names: List[str]) -> List[tuple[int, str]]:
    positions = []
    for name in names:
        pos = text_lower.find(name.lower())
        if pos != -1:
            positions.append((pos, name))
    return positions


def _match_brand(
    text_lower: str, product: str, brand_positions: List[tuple[int, str]]
) -> str:
    pos = text_lower.find(product.lower())
    if pos == -1:
        return ""
    return _closest_brand(pos, brand_positions)


def _closest_brand(pos: int, brand_positions: List[tuple[int, str]]) -> str:
    return min(brand_positions, key=lambda item: abs(item[0] - pos))[1]


def _accumulate(counts: dict, mapping: Dict[str, str]) -> None:
    for product, brand in mapping.items():
        counts.setdefault(product, {})
        counts[product][brand] = counts[product].get(brand, 0) + 1


def _select_winners(counts: dict) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for product, brand_counts in counts.items():
        result[product] = max(brand_counts, key=lambda b: (brand_counts[b], b))
    return result


def _extract_mapping(
    items: List[dict],
    product_map: Dict[str, str],
    allowed: Dict[str, str],
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for item in items:
        product = _resolve_name(item.get("product"), product_map)
        brand = _resolve_name(item.get("brand"), allowed)
        if product and brand:
            mapping[product] = brand
    return mapping


def _resolve_name(value: str | None, name_map: Dict[str, str]) -> str:
    if not value:
        return ""
    return name_map.get(value.lower(), "")


def _is_valid_example(mapping: dict) -> bool:
    if mapping.get("is_validated"):
        return True
    return (mapping.get("confidence") or 0.0) >= MIN_CONFIDENCE


def _example_sort_key(mapping: dict) -> tuple[int, float]:
    return (1 if mapping.get("is_validated") else 0, mapping.get("confidence") or 0.0)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _name_key(value: str) -> str:
    return value.casefold()


def _norm_key(value: str) -> str:
    return normalize_entity_key(value)


def _record_to_example(record) -> dict:
    product = _record_product_name(record)
    brand = _record_brand_name(record)
    if not product or not brand:
        return {}
    confidence = _record_confidence(record)
    return {
        "product": product,
        "brand": brand,
        "confidence": confidence,
        "is_validated": record.is_validated,
    }


def _record_product_name(record) -> str:
    canonical = getattr(record, "canonical_product", None)
    if canonical:
        return canonical.display_name
    product = getattr(record, "product", None)
    return product.display_name if product else ""


def _record_brand_name(record) -> str:
    canonical = getattr(record, "canonical_brand", None)
    if canonical:
        return canonical.display_name
    brand = getattr(record, "brand", None)
    return brand.display_name if brand else ""


def _record_confidence(record) -> float:
    value = getattr(record, "confidence", None)
    if value is None:
        return 1.0 if record.is_validated else 0.0
    return value


def _vertical_name(db, vertical_id: int) -> str:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    return vertical.name if vertical else ""


def _load_knowledge_cache(db, vertical_id: int) -> Dict[str, str]:
    vertical_name = _vertical_name(db, vertical_id)
    if not vertical_name:
        return {}
    try:
        from services.knowledge_lookup import build_mapping_cache
        return build_mapping_cache(vertical_name)
    except Exception as e:
        logger.warning(f"[PostHocMapping] Failed to load knowledge cache: {e}")
        return {}


def _lookup_in_knowledge_cache(product: str, cache: Dict[str, str]) -> Optional[str]:
    if not cache:
        return None
    product_lower = product.lower()
    if product_lower in cache:
        return cache[product_lower]
    product_key = normalize_entity_key(product)
    if product_key in cache:
        return cache[product_key]
    return None


def _apply_knowledge_mapping(
    db,
    vertical_id: int,
    product,
    brand_name: str,
    brand_id: int,
) -> Dict[str, str]:
    _upsert_mapping(db, vertical_id, product.id, brand_id, 0.75, "knowledge")
    if product.brand_id is None:
        product.brand_id = brand_id
    logger.info(
        f"[PostHocMapping] Applied knowledge mapping: {product.display_name} -> {brand_name}"
    )
    return {product.display_name: brand_name}


def _knowledge_mappings(
    knowledge_db,
    vertical_id: int,
) -> List[KnowledgeProductBrandMapping]:
    return (
        knowledge_db.query(KnowledgeProductBrandMapping)
        .filter(
            KnowledgeProductBrandMapping.vertical_id == vertical_id,
            KnowledgeProductBrandMapping.is_validated.is_(True),
        )
        .order_by(
            case((KnowledgeProductBrandMapping.source == "feedback", 1), else_=0).desc(),
            KnowledgeProductBrandMapping.support_count.desc(),
            KnowledgeProductBrandMapping.confidence.desc(),
            KnowledgeProductBrandMapping.updated_at.desc(),
        )
        .all()
    )


def _legacy_mapping_examples(db, vertical_id: int) -> List[dict]:
    from models import ProductBrandMapping

    records = (
        db.query(ProductBrandMapping)
        .filter(ProductBrandMapping.vertical_id == vertical_id)
        .all()
    )
    examples = [_record_to_example(record) for record in records]
    return select_mapping_examples([example for example in examples if example])


def _persist_to_knowledge_base(
    vertical_name: str,
    product_name: str,
    brand_name: str,
    confidence: float,
    source: str,
) -> None:
    try:
        with knowledge_session(write=True) as knowledge_db:
            vertical_id = _get_or_create_knowledge_vertical_id(knowledge_db, vertical_name)
            brand = _get_or_create_knowledge_brand(knowledge_db, vertical_id, brand_name)
            product = _get_or_create_knowledge_product(knowledge_db, vertical_id, product_name)
            _upsert_knowledge_mapping(
                knowledge_db, vertical_id, product.id, brand.id, f"auto_{source}", 1
            )
            _recompute_mapping_confidence(knowledge_db, vertical_id, product.id)
            _apply_auto_validation_policy(knowledge_db, vertical_id, product.id)
            logger.debug(
                f"[KnowledgePersist] Stored mapping: {product_name} -> {brand_name} "
                f"(confidence={confidence:.2f}, source={source})"
            )
    except Exception as e:
        logger.warning(f"[KnowledgePersist] Failed to persist mapping: {e}")


def _get_or_create_knowledge_brand(
    db,
    vertical_id: int,
    brand_name: str,
) -> KnowledgeBrand:
    canonical = normalize_entity_key(brand_name)
    existing = db.query(KnowledgeBrand).filter(
        KnowledgeBrand.vertical_id == vertical_id,
        func.lower(KnowledgeBrand.canonical_name) == canonical,
    ).first()
    if existing:
        return existing

    brand = KnowledgeBrand(
        vertical_id=vertical_id,
        canonical_name=canonical,
        display_name=brand_name,
        is_validated=False,
        validation_source="auto",
    )
    db.add(brand)
    db.flush()
    return brand


def _get_or_create_knowledge_product(
    db,
    vertical_id: int,
    product_name: str,
) -> KnowledgeProduct:
    canonical = normalize_entity_key(product_name)
    existing = db.query(KnowledgeProduct).filter(
        KnowledgeProduct.vertical_id == vertical_id,
        func.lower(KnowledgeProduct.canonical_name) == canonical,
    ).first()
    if existing:
        return existing

    product = KnowledgeProduct(
        vertical_id=vertical_id,
        canonical_name=canonical,
        display_name=product_name,
        is_validated=False,
        validation_source="auto",
    )
    db.add(product)
    db.flush()
    return product


def _upsert_knowledge_mapping(
    db,
    vertical_id: int,
    product_id: int,
    brand_id: int,
    source: str,
    support_increment: int = 0,
) -> KnowledgeProductBrandMapping:
    existing = db.query(KnowledgeProductBrandMapping).filter(
        KnowledgeProductBrandMapping.vertical_id == vertical_id,
        KnowledgeProductBrandMapping.product_id == product_id,
        KnowledgeProductBrandMapping.brand_id == brand_id,
    ).first()

    if existing:
        existing.support_count = (existing.support_count or 0) + max(support_increment, 0)
        if _should_update_knowledge_source(existing.source, source):
            existing.source = source
        return existing

    mapping = KnowledgeProductBrandMapping(
        vertical_id=vertical_id,
        product_id=product_id,
        brand_id=brand_id,
        support_count=max(support_increment, 0),
        confidence=0.0,
        is_validated=False,
        source=source,
    )
    db.add(mapping)
    db.flush()
    return mapping


def _persist_mapping_evidence(
    db,
    vertical_id: int,
    counts: Dict[str, dict[str, int]],
    brand_lookup: Dict[str, int],
    product_lookup: Dict[str, object],
) -> None:
    if not KNOWLEDGE_PERSIST_ENABLED:
        return
    vertical_name = _vertical_name(db, vertical_id)
    if not vertical_name or not counts:
        return
    brand_names = _brand_display_names(db, vertical_id)
    _persist_counts_to_knowledge(vertical_name, counts, brand_lookup, product_lookup, brand_names)


def _persist_counts_to_knowledge(
    vertical_name: str,
    counts: Dict[str, dict[str, int]],
    brand_lookup: Dict[str, int],
    product_lookup: Dict[str, object],
    brand_names: Dict[int, str],
) -> None:
    try:
        with knowledge_session(write=True) as knowledge_db:
            _persist_counts_in_session(
                knowledge_db, vertical_name, counts, brand_lookup, product_lookup, brand_names
            )
    except Exception as e:
        logger.warning(f"[KnowledgePersist] Failed to persist evidence: {e}")


def _persist_counts_in_session(
    knowledge_db,
    vertical_name: str,
    counts: Dict[str, dict[str, int]],
    brand_lookup: Dict[str, int],
    product_lookup: Dict[str, object],
    brand_names: Dict[int, str],
) -> None:
    vertical_id = _get_or_create_knowledge_vertical_id(knowledge_db, vertical_name)
    for product_name, brand_counts in counts.items():
        _persist_product_evidence(
            knowledge_db,
            vertical_id,
            _resolved_product_name(product_name, product_lookup),
            _support_by_brand_id(brand_counts, brand_lookup),
            brand_names,
        )


def _persist_product_evidence(
    knowledge_db,
    vertical_id: int,
    product_name: str,
    support: Dict[int, int],
    brand_names: Dict[int, str],
) -> None:
    if not product_name or not support:
        return
    product = _get_or_create_knowledge_product(knowledge_db, vertical_id, product_name)
    _persist_product_support(knowledge_db, vertical_id, product.id, support, brand_names)
    _recompute_mapping_confidence(knowledge_db, vertical_id, product.id)
    _apply_auto_validation_policy(knowledge_db, vertical_id, product.id)


def _persist_product_support(
    knowledge_db,
    vertical_id: int,
    product_id: int,
    support: Dict[int, int],
    brand_names: Dict[int, str],
) -> None:
    for brand_id, increment in support.items():
        _persist_mapping_edge(knowledge_db, vertical_id, product_id, brand_id, increment, brand_names)


def _persist_mapping_edge(
    knowledge_db,
    vertical_id: int,
    product_id: int,
    brand_id: int,
    increment: int,
    brand_names: Dict[int, str],
) -> None:
    brand_name = brand_names.get(brand_id, "")
    if not brand_name or increment <= 0:
        return
    brand = _get_or_create_knowledge_brand(knowledge_db, vertical_id, brand_name)
    _upsert_knowledge_mapping(
        knowledge_db, vertical_id, product_id, brand.id, "auto_list_evidence", increment
    )


def _recompute_mapping_confidence(knowledge_db, vertical_id: int, product_id: int) -> None:
    mappings = _product_mappings(knowledge_db, vertical_id, product_id)
    total = sum((m.support_count or 0) for m in mappings)
    for mapping in mappings:
        mapping.confidence = (mapping.support_count or 0) / total if total else 0.0


def _apply_auto_validation_policy(knowledge_db, vertical_id: int, product_id: int) -> None:
    mappings = _product_mappings(knowledge_db, vertical_id, product_id)
    if not mappings:
        return
    decision = _auto_validation_decision(mappings)
    if decision is None:
        _revoke_auto_support(mappings)
        return
    _set_single_auto_support(mappings, decision)


def _auto_validation_decision(
    mappings: list[KnowledgeProductBrandMapping],
) -> KnowledgeProductBrandMapping | None:
    if _has_feedback_validated(mappings):
        return None
    top, runner_up = _top_two_support(mappings)
    if runner_up >= AUTO_VALIDATE_RUNNER_UP_MIN:
        return None
    return top if _meets_auto_validation_threshold(top) else None


def _top_two_support(mappings: list[KnowledgeProductBrandMapping]) -> tuple[KnowledgeProductBrandMapping, int]:
    ordered = sorted(mappings, key=lambda m: (m.support_count or 0, m.id), reverse=True)
    runner = ordered[1].support_count or 0 if len(ordered) > 1 else 0
    return ordered[0], runner


def _meets_auto_validation_threshold(mapping: KnowledgeProductBrandMapping) -> bool:
    if (mapping.source or "") == "user_reject":
        return False
    return (
        (mapping.support_count or 0) >= AUTO_VALIDATE_SUPPORT_COUNT
        and (mapping.confidence or 0.0) >= AUTO_VALIDATE_CONFIDENCE
    )


def _set_single_auto_support(
    mappings: list[KnowledgeProductBrandMapping],
    winner: KnowledgeProductBrandMapping,
) -> None:
    _revoke_auto_support(mappings)
    if winner.is_validated and winner.source == "feedback":
        return
    winner.is_validated = True
    winner.source = "auto_support"


def _revoke_auto_support(mappings: list[KnowledgeProductBrandMapping]) -> None:
    for mapping in mappings:
        if mapping.is_validated and (mapping.source or "") == "auto_support":
            mapping.is_validated = False


def _has_feedback_validated(mappings: list[KnowledgeProductBrandMapping]) -> bool:
    return any(m.is_validated and (m.source or "") == "feedback" for m in mappings)


def _product_mappings(
    knowledge_db,
    vertical_id: int,
    product_id: int,
) -> list[KnowledgeProductBrandMapping]:
    return knowledge_db.query(KnowledgeProductBrandMapping).filter(
        KnowledgeProductBrandMapping.vertical_id == vertical_id,
        KnowledgeProductBrandMapping.product_id == product_id,
    ).all()


def _should_update_knowledge_source(existing: str | None, incoming: str) -> bool:
    return (existing or "") not in ("feedback", "user_reject", "auto_support") and bool(incoming)


def _get_or_create_knowledge_vertical_id(knowledge_db, vertical_name: str) -> int:
    resolved = resolve_knowledge_vertical_id(knowledge_db, vertical_name)
    if resolved:
        return resolved
    return get_or_create_vertical(knowledge_db, vertical_name).id


def _resolved_product_name(name: str, product_lookup: Dict[str, object]) -> str:
    product = _resolve_product(name, product_lookup)
    return product.display_name if product else name


def _support_by_brand_id(
    brand_counts: dict[str, int],
    brand_lookup: Dict[str, int],
) -> Dict[int, int]:
    support: Dict[int, int] = {}
    for brand_name, count in (brand_counts or {}).items():
        brand_id = _resolve_brand_id(brand_name, brand_lookup)
        if brand_id and count:
            support[brand_id] = support.get(brand_id, 0) + count
    return support


def _brand_display_names(db, vertical_id: int) -> Dict[int, str]:
    from models import Brand

    rows = db.query(Brand.id, Brand.display_name).filter(Brand.vertical_id == vertical_id).all()
    return {brand_id: name for brand_id, name in rows if brand_id and name}
