"""Pre-filter entities by common word / material suffix heuristics."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

COMMON_WORD_BLOCKLIST = frozenset({
    "features", "protection", "design", "comfort", "ultra", "size", "premium",
    "natural", "soft", "thin", "classic", "plus", "pro", "max", "mini", "new",
    "super", "extra", "light", "air", "dry", "fresh", "pure", "gold", "silver",
    "black", "white", "blue", "red", "green", "keeps", "original", "basic",
    "advanced", "series", "model", "type", "style", "version", "edition",
    "standard", "special", "select", "active", "outdoor", "indoor", "sport",
    "performance", "technology", "material", "quality", "value", "price",
    "waterproof", "breathable", "lightweight", "durable", "flexible",
    "absorbent", "sensitive", "gentle", "hypoallergenic", "organic",
    "high", "low", "mid", "top", "best", "good", "great", "excellent",
    "recommended", "popular", "famous", "leading", "major",
    "suitable", "available", "compatible", "reliable", "power", "strong",
    "comfortable", "smooth", "stable", "hybrid", "electric", "driving",
    "terrain", "grip", "traction", "ankle", "cushioning", "support",
    "range", "space", "interior", "exterior", "safety", "fuel",
    "distance", "speed", "weight", "capacity", "coverage", "system",
    "overall", "summary", "comparison", "review", "rating", "analysis",
    "option", "choice", "alternative", "preference", "category",
    "on", "gtx", "wp", "scenarios", "outsole", "membrane", "midsole",
    "insole", "upper", "sole", "lining", "footbed", "shank",
})

MATERIAL_SUFFIX_BLOCKLIST = frozenset({
    "outsole", "membrane", "midsole", "insole", "upper", "sole",
    "lining", "footbed", "shank", "foam", "rubber", "mesh",
    "technology", "system", "material", "compound", "cushioning",
})

MIN_ENTITY_LENGTH = 2
MAX_SHORT_ALPHA_LENGTH = 2


def has_cjk(text: str) -> bool:
    return any('\u4e00' <= c <= '\u9fff' for c in text)


def is_likely_common_word(entity: str) -> bool:
    cleaned = entity.strip()
    if not cleaned or len(cleaned) < MIN_ENTITY_LENGTH:
        return True
    if has_cjk(cleaned):
        return False
    if any(c.isdigit() for c in cleaned):
        return False
    if cleaned.lower() in COMMON_WORD_BLOCKLIST:
        return True
    if len(cleaned) <= MAX_SHORT_ALPHA_LENGTH and cleaned.isalpha():
        return True
    if _ends_with_material_suffix(cleaned):
        return True
    return not any(c.isupper() for c in cleaned)


def _ends_with_material_suffix(text: str) -> bool:
    parts = text.lower().split()
    return len(parts) >= 2 and parts[-1] in MATERIAL_SUFFIX_BLOCKLIST


def pre_filter_entities(entities: list[str]) -> tuple[list[str], set[str]]:
    candidates, rejected = [], set()
    for entity in entities:
        if is_likely_common_word(entity):
            rejected.add(entity)
        else:
            candidates.append(entity)
    return candidates, rejected


def apply_pre_filter(
    brands: list[str],
    products: list[str],
) -> tuple[list[str], list[str], set[str], set[str], dict[str, str]]:
    brand_candidates, rej_brands = pre_filter_entities(brands)
    product_candidates, rej_products = pre_filter_entities(products)
    reasons = {name: "common_word" for name in rej_brands | rej_products}
    logger.info(
        "[CONSULTANT] Pre-filter rejected: %d brands, %d products",
        len(rej_brands), len(rej_products),
    )
    return brand_candidates, product_candidates, rej_brands, rej_products, reasons
