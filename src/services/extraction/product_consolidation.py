"""Product consolidation: brand prefix stripping, suffix variant merging, partitioning."""

from __future__ import annotations

import re

from services.extraction.normalizer import parse_json_response

PRODUCT_SUFFIX_TOKENS = frozenset({
    "gtx", "wp", "waterproof", "mid", "low", "all-wthr",
    "pro", "plus", "max", "evo", "lite",
})

MIN_BRAND_LENGTH = 2
MIN_STRIPPED_LENGTH = 2
MIN_REMAINDER_LENGTH = 3


def build_reverse_brand_map(brand_aliases: dict[str, str]) -> dict[str, str]:
    reverse: dict[str, str] = {}
    for alias, canonical in brand_aliases.items():
        reverse[alias] = canonical
        reverse[canonical] = canonical
    return reverse


def strip_brand_prefixes(
    product_aliases: dict[str, str],
    product_brand_map: dict[str, str],
    reverse_brand_map: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    updated_aliases = dict(product_aliases)
    updated_map = dict(product_brand_map)
    brand_names = sorted(reverse_brand_map.keys(), key=len, reverse=True)

    for product in set(updated_aliases.values()):
        stripped, brand = try_strip_brand(product, brand_names, reverse_brand_map)
        if stripped and len(stripped) >= MIN_STRIPPED_LENGTH:
            updated_aliases[product] = stripped
            updated_map.setdefault(stripped, brand)

    return updated_aliases, updated_map


def try_strip_brand(
    product: str,
    brand_names: list[str],
    reverse_brand_map: dict[str, str],
) -> tuple[str | None, str | None]:
    for brand_name in brand_names:
        if len(brand_name) < MIN_BRAND_LENGTH:
            continue
        if not product.startswith(brand_name):
            continue
        remainder = product[len(brand_name):].lstrip(" -·")
        if remainder and remainder != product and _is_valid_remainder(remainder):
            return remainder, reverse_brand_map[brand_name]
    return None, None


def _is_valid_remainder(remainder: str) -> bool:
    if len(remainder) < MIN_REMAINDER_LENGTH:
        return False
    return any(c.isalpha() for c in remainder[:3])


def strip_product_suffix(name: str) -> str | None:
    parts = re.split(r'\s+', name.strip())
    if len(parts) < 2:
        return None
    while len(parts) > 1 and parts[-1].lower() in PRODUCT_SUFFIX_TOKENS:
        parts.pop()
    result = " ".join(parts)
    if result == name.strip() or len(result) < MIN_STRIPPED_LENGTH:
        return None
    return result


def merge_suffix_variants(product_aliases: dict[str, str]) -> dict[str, str]:
    updated = dict(product_aliases)
    canonical_set = set(updated.values())
    base_to_canonical = _build_base_to_canonical(canonical_set)
    remap = _build_suffix_remap(base_to_canonical, canonical_set)
    if not remap:
        return updated
    for alias, canonical in updated.items():
        if canonical in remap:
            updated[alias] = remap[canonical]
    return updated


def _build_base_to_canonical(canonical_set: set[str]) -> dict[str, str]:
    base_to_canonical: dict[str, str] = {}
    for canonical in sorted(canonical_set, key=len):
        base = strip_product_suffix(canonical)
        if not base:
            continue
        if base in canonical_set:
            base_to_canonical[canonical] = base
        elif base in base_to_canonical:
            base_to_canonical[canonical] = base_to_canonical[base]
        else:
            base_to_canonical.setdefault(base, canonical)
    return base_to_canonical


def _build_suffix_remap(
    base_to_canonical: dict[str, str],
    canonical_set: set[str],
) -> dict[str, str]:
    return {
        variant: target
        for variant, target in base_to_canonical.items()
        if variant != target and target in canonical_set
    }


def partition_products_by_brand(
    product_aliases: dict[str, str],
    product_brand_map: dict[str, str],
) -> tuple[dict[str, list[str]], list[str]]:
    canonical_products = sorted(set(product_aliases.values()))
    by_brand: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for product in canonical_products:
        brand = product_brand_map.get(product)
        if brand:
            by_brand.setdefault(brand, []).append(product)
        else:
            unmapped.append(product)
    return by_brand, unmapped


def merge_variant_results(
    response: str,
    product_aliases: dict[str, str],
    product_brand_map: dict[str, str],
    brand_aliases: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    parsed = parse_json_response(response) or {}
    updated_aliases = dict(product_aliases)
    updated_map = dict(product_brand_map)

    for alias, canonical in (parsed.get("product_aliases") or {}).items():
        if alias and canonical:
            updated_aliases[alias] = str(canonical)
    for product, brand in (parsed.get("product_brand_map") or {}).items():
        if product and brand:
            updated_map[product] = brand_aliases.get(brand, brand)

    return updated_aliases, updated_map
