import json
import os
from typing import Dict, List

from services.canonicalization_metrics import normalize_entity_key
from services.brand_recognition.list_processor import is_list_format, split_into_list_items
from services.brand_recognition.prompts import load_prompt
from services.brand_recognition.text_utils import _parse_json_response

MIN_CONFIDENCE = float(os.getenv("MAPPING_CONFIDENCE_THRESHOLD", "0.7"))
MIN_PROXIMITY_SHARE = float(os.getenv("MAPPING_PROXIMITY_SHARE", "0.6"))
MIN_PROXIMITY_COUNT = int(os.getenv("MAPPING_MIN_COUNT", "1"))
QWEN_CONFIDENCE = float(os.getenv("MAPPING_QWEN_CONFIDENCE", "0.7"))
MAX_EXAMPLES = 20


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
    from models import ProductBrandMapping

    records = db.query(ProductBrandMapping).filter(
        ProductBrandMapping.vertical_id == vertical_id
    ).all()
    examples = [_record_to_example(record) for record in records]
    return select_mapping_examples([example for example in examples if example])


def _iter_items(text: str) -> List[str]:
    items = split_into_list_items(text) if is_list_format(text) else []
    return items if items else [text]


def _mapping_input(db, run_id: int):
    from services.brand_recognition.consolidation_service import gather_consolidation_input

    input_data = gather_consolidation_input(db, run_id)
    if not input_data.all_unique_products:
        return None
    return input_data


async def _map_products_for_input(db, input_data) -> Dict[str, str]:
    brand_lookup = _brand_lookup(db, input_data.vertical_id)
    product_lookup = _product_lookup(db, input_data.vertical_id)
    counts = map_product_brand_counts(input_data.answer_entities)
    known = load_mapping_examples(db, input_data.vertical_id)
    return await _map_products(db, input_data, counts, brand_lookup, product_lookup, known)


async def _map_products(
    db,
    input_data,
    counts: Dict[str, dict[str, int]],
    brand_lookup: Dict[str, int],
    product_lookup: Dict[str, object],
    known: List[dict],
) -> Dict[str, str]:
    results: Dict[str, str] = {}
    for product, brand_counts in counts.items():
        mapping = await _map_single_product(
            db, input_data, product, brand_counts, brand_lookup, product_lookup, known
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
) -> Dict[str, str]:
    product_record = _resolve_product(product, product_lookup)
    if not product_record:
        return {}
    candidate_ids = _candidate_brand_ids(brand_counts, brand_lookup)
    if not candidate_ids:
        return {}
    winner = _top_brand(brand_counts)
    if _is_confident_brand(winner, brand_counts):
        return _apply_mapping(db, input_data.vertical_id, product_record, winner, brand_counts, candidate_ids, "proximity")
    brand = await _qwen_brand(product, list(candidate_ids.keys()), input_data.answer_entities, known)
    if not brand:
        return {}
    return _apply_mapping(db, input_data.vertical_id, product_record, brand, brand_counts, candidate_ids, "qwen")


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
    from models import EntityType, RejectedEntity

    rows = db.query(RejectedEntity.name).filter(
        RejectedEntity.vertical_id == vertical_id,
        RejectedEntity.entity_type == EntityType.BRAND,
    ).all()
    return {name.casefold() for (name,) in rows if name}


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
    return [brand.display_name, brand.original_name, brand.translated_name] + (aliases.get("zh") or []) + (aliases.get("en") or [])


def _add_variant(lookup: Dict[str, int], variant: str | None, brand_id: int) -> None:
    if not variant:
        return
    lookup.setdefault(_name_key(variant), brand_id)
    lookup.setdefault(_norm_key(variant), brand_id)


def _add_product_variant(lookup: Dict[str, object], variant: str | None, product: object) -> None:
    if not variant:
        return
    lookup.setdefault(_name_key(variant), product)
    lookup.setdefault(_norm_key(variant), product)


def _resolve_product(name: str, product_lookup: Dict[str, object]):
    return product_lookup.get(_name_key(name)) or product_lookup.get(_norm_key(name))


def _candidate_brand_ids(brand_counts: dict[str, int], brand_lookup: Dict[str, int]) -> Dict[str, int]:
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
    return bool(total) and top >= MIN_PROXIMITY_COUNT and top / total >= MIN_PROXIMITY_SHARE


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


def _mapping_confidence(source: str, brand_name: str, brand_counts: dict[str, int]) -> float:
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

    return db.query(ProductBrandMapping).filter(
        ProductBrandMapping.vertical_id == vertical_id,
        ProductBrandMapping.product_id == product_id,
    ).first()


def _new_mapping(vertical_id: int, product_id: int, brand_id: int, confidence: float, source: str):
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


async def _qwen_brand(product: str, candidates: List[str], answers: List[object], known: List[dict]) -> str:
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


def _match_brand(text_lower: str, product: str, brand_positions: List[tuple[int, str]]) -> str:
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
    return {"product": product, "brand": brand, "confidence": record.confidence, "is_validated": record.is_validated}


def _record_product_name(record) -> str:
    if record.canonical_product:
        return record.canonical_product.display_name
    if record.product:
        return record.product.display_name
    return ""


def _record_brand_name(record) -> str:
    if record.canonical_brand:
        return record.canonical_brand.display_name
    if record.brand:
        return record.brand.display_name
    return ""
