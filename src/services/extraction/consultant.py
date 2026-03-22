"""LLM-backed normalization and relevance validation via OpenRouter."""

from __future__ import annotations

import json
import logging
from collections import OrderedDict

from sqlalchemy.orm import Session

from models.domain import EntityType
from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeProductBrandMapping,
    KnowledgeRejectedEntity,
)
from prompts.loader import load_prompt
from services.extraction.vertical_seeder import _parse_json_response
from services.knowledge_verticals import normalize_entity_key

logger = logging.getLogger(__name__)

OPENROUTER_PRIMARY_MODEL = "qwen/qwen3.5-397b-a17b"
OPENROUTER_BACKUP_MODEL = "baidu/ernie-4.5-300b-a47b"
VALIDATION_BATCH_SIZE = 200


class ExtractionConsultant:
    """Normalize brands/products and validate relevance for a full run."""

    def __init__(
        self,
        vertical: str,
        vertical_description: str,
        vertical_id: int | None = None,
        knowledge_db: Session | None = None,
    ):
        self.vertical = vertical
        self.vertical_description = vertical_description
        self.vertical_id = vertical_id
        self.knowledge_db = knowledge_db

    async def normalize_and_map(
        self,
        brands: list[str],
        products: list[str],
        item_pairs: list[tuple[str | None, str | None]],
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[CONSULTANT] normalize_and_map starting: {len(brands)} brands, {len(products)} products")

        logger.info(f"[CONSULTANT] Normalizing entities...")
        brand_aliases = self._normalize_entities(brands, entity_type="brand")
        product_aliases = self._normalize_entities(products, entity_type="product")
        brand_aliases = _apply_parenthetical_aliases(brand_aliases, brands)
        product_aliases = _apply_parenthetical_aliases(product_aliases, products)
        logger.info(f"[CONSULTANT] Entities normalized")

        logger.info(f"[CONSULTANT] Building proximity map...")
        product_brand_map = self._build_proximity_map(item_pairs, brand_aliases, product_aliases)
        logger.info(f"[CONSULTANT] Proximity map built: {len(product_brand_map)} mappings")

        logger.info(f"[CONSULTANT] Loading existing product-brand map from KB...")
        product_brand_map.update(self._existing_product_brand_map())
        logger.info(f"[CONSULTANT] Existing map loaded")

        logger.info(f"[CONSULTANT] Checking if remote normalization needed...")
        needs_remote = self._has_remote_llm() and (
            _has_collisions(brand_aliases) or _has_collisions(product_aliases) or any(
                product_aliases.get(product, product) not in product_brand_map for product in products
            )
        )
        logger.info(f"[CONSULTANT] Remote normalization needed: {needs_remote}")
        if not needs_remote:
            logger.info(f"[CONSULTANT] normalize_and_map completed (local only)")
            return brand_aliases, product_aliases, product_brand_map

        logger.info(f"[CONSULTANT] Loading prompt...")
        prompt = load_prompt(
            "extraction/consolidation_normalize_map",
            vertical=self.vertical,
            vertical_description=self.vertical_description,
            brands_json=json.dumps(brands, ensure_ascii=False),
            products_json=json.dumps(products, ensure_ascii=False),
            item_pairs_json=json.dumps(item_pairs, ensure_ascii=False),
            existing_product_brand_map_json=json.dumps(product_brand_map, ensure_ascii=False),
        )
        logger.info(f"[CONSULTANT] Calling remote LLM for normalization...")
        try:
            response = await self._call_llm(prompt)
        except Exception as e:
            logger.error(f"[CONSULTANT] Remote normalization failed, using local only: {e}")
            return brand_aliases, product_aliases, product_brand_map
        logger.info(f"[CONSULTANT] Remote LLM returned, parsing response...")
        parsed = _parse_json_response(response) or {}
        logger.info(f"[CONSULTANT] Response parsed")

        logger.info(f"[CONSULTANT] Merging remote normalization results...")
        for alias, canonical in (parsed.get("brand_aliases") or {}).items():
            if alias:
                brand_aliases[alias] = _ensure_str(canonical) or alias
        for alias, canonical in (parsed.get("product_aliases") or {}).items():
            if alias:
                product_aliases[alias] = _ensure_str(canonical) or alias
        for product, brand in (parsed.get("product_brand_map") or {}).items():
            if product and brand:
                product_brand_map[product_aliases.get(product, product)] = brand_aliases.get(brand, brand)

        logger.info(f"[CONSULTANT] normalize_and_map completed successfully")
        return brand_aliases, product_aliases, product_brand_map

    async def consolidate_products(
        self,
        product_aliases: dict[str, str],
        product_brand_map: dict[str, str],
        brand_aliases: dict[str, str],
    ) -> tuple[dict[str, str], dict[str, str]]:
        reverse_brand_map = _build_reverse_brand_map(brand_aliases)
        product_aliases, product_brand_map = _strip_brand_prefixes(
            product_aliases, product_brand_map, reverse_brand_map,
        )
        product_aliases = _merge_suffix_variants(product_aliases)
        if self._has_remote_llm():
            product_aliases, product_brand_map = await self._group_product_variants(
                product_aliases, product_brand_map, brand_aliases,
            )
        return product_aliases, product_brand_map

    async def _group_product_variants(
        self,
        product_aliases: dict[str, str],
        product_brand_map: dict[str, str],
        brand_aliases: dict[str, str],
    ) -> tuple[dict[str, str], dict[str, str]]:
        products_by_brand, unmapped = _partition_products_by_brand(
            product_aliases, product_brand_map,
        )
        if not products_by_brand and not unmapped:
            return product_aliases, product_brand_map
        prompt = load_prompt(
            "extraction/consolidation_group_variants",
            vertical=self.vertical,
            vertical_description=self.vertical_description,
            products_by_brand_json=json.dumps(products_by_brand, ensure_ascii=False),
            unmapped_products_json=json.dumps(unmapped, ensure_ascii=False),
        )
        try:
            response = await self._call_llm(prompt)
        except Exception as e:
            logger.error(f"[CONSULTANT] Variant grouping failed: {e}")
            return product_aliases, product_brand_map
        return _merge_variant_results(
            response, product_aliases, product_brand_map, brand_aliases,
        )

    async def validate_relevance(
        self,
        brands: list[str],
        products: list[str],
    ) -> tuple[set[str], set[str], set[str], set[str], dict[str, str]]:
        logger.info(f"[CONSULTANT] validate_relevance: {len(brands)} brands, {len(products)} products")
        brand_candidates, product_candidates, rej_brands, rej_products, rej_reasons = (
            _apply_pre_filter(brands, products)
        )
        if not self._has_remote_llm():
            logger.info("[CONSULTANT] No remote LLM available, accepting pre-filtered entities")
            return set(brand_candidates), set(product_candidates), rej_brands, rej_products, rej_reasons
        known = self._load_validation_context(brands, products)
        v_brands, v_products, r_brands, r_products, reasons = await self._validate_in_batches(
            brand_candidates, product_candidates, *known,
        )
        rej_brands.update(r_brands)
        rej_products.update(r_products)
        rej_reasons.update(reasons)
        v_brands -= rej_brands
        v_products -= rej_products
        logger.info(f"[CONSULTANT] validate_relevance done: {len(v_brands)} valid brands, {len(v_products)} valid products")
        return v_brands, v_products, rej_brands, rej_products, rej_reasons

    async def _validate_in_batches(
        self,
        brands: list[str],
        products: list[str],
        known_brands: list[str],
        known_products: list[str],
        known_rejected: list[dict],
    ) -> tuple[set[str], set[str], set[str], set[str], dict[str, str]]:
        brand_batches = _chunk_list(brands, VALIDATION_BATCH_SIZE)
        product_batches = _chunk_list(products, VALIDATION_BATCH_SIZE)
        n_batches = max(len(brand_batches), len(product_batches))
        if n_batches == 0:
            return set(), set(), set(), set(), {}
        return await self._run_validation_pass(
            brand_batches, product_batches, n_batches,
            known_brands, known_products, known_rejected, pass_num=1,
        )

    async def _run_validation_pass(
        self,
        brand_batches: list[list[str]],
        product_batches: list[list[str]],
        n_batches: int,
        known_brands: list[str],
        known_products: list[str],
        known_rejected: list[dict],
        pass_num: int,
    ) -> tuple[set[str], set[str], set[str], set[str], dict[str, str]]:
        results = []
        for i in range(n_batches):
            b = brand_batches[i] if i < len(brand_batches) else []
            p = product_batches[i] if i < len(product_batches) else []
            logger.info(f"[CONSULTANT] Pass {pass_num} batch {i+1}/{n_batches}: {len(b)} brands, {len(p)} products")
            results.append(await self._validate_single_batch(b, p, known_brands, known_products, known_rejected))
        return _merge_validation_results(results)

    async def _validate_single_batch(
        self,
        brands: list[str],
        products: list[str],
        known_brands: list[str],
        known_products: list[str],
        known_rejected: list[dict],
    ) -> tuple[set[str], set[str], set[str], set[str], dict[str, str]]:
        prompt = load_prompt(
            "extraction/consolidation_validate",
            vertical=self.vertical,
            vertical_description=self.vertical_description,
            brands_json=json.dumps(sorted(set(brands)), ensure_ascii=False),
            products_json=json.dumps(sorted(set(products)), ensure_ascii=False),
            known_brands=known_brands,
            known_products=known_products,
            known_rejected=known_rejected,
        )
        try:
            response = await self._call_llm(prompt)
        except Exception as e:
            logger.error(f"[CONSULTANT] Batch validation API call failed: {e}")
            return set(), set(), set(brands), set(products), {n: "api_error" for n in brands + products}
        return _parse_batch_validation(response, brands, products)

    def store_rejections(
        self,
        rejected_brands: set[str],
        rejected_products: set[str],
        rejection_reasons: dict[str, str],
    ) -> None:
        if self.knowledge_db is None or self.vertical_id is None:
            return

        for entity_type, names in (
            (EntityType.BRAND, rejected_brands),
            (EntityType.PRODUCT, rejected_products),
        ):
            for name in names:
                alias_key = normalize_entity_key(name)
                existing = (
                    self.knowledge_db.query(KnowledgeRejectedEntity)
                    .filter(
                        KnowledgeRejectedEntity.vertical_id == self.vertical_id,
                        KnowledgeRejectedEntity.entity_type == entity_type,
                        KnowledgeRejectedEntity.alias_key == alias_key,
                    )
                    .first()
                )
                if existing:
                    continue
                self.knowledge_db.add(
                    KnowledgeRejectedEntity(
                        vertical_id=self.vertical_id,
                        entity_type=entity_type,
                        name=name,
                        reason=rejection_reasons.get(name, "not relevant to vertical"),
                    )
                )

    def _load_validation_context(
        self,
        candidate_brands: list[str],
        candidate_products: list[str],
    ) -> tuple[list[str], list[str], list[dict]]:
        if self.knowledge_db is None or self.vertical_id is None:
            return [], [], []

        candidate_brand_keys = {normalize_entity_key(b) for b in candidate_brands}
        candidate_product_keys = {normalize_entity_key(p) for p in candidate_products}

        known_brands = [
            row.display_name
            for row in self.knowledge_db.query(KnowledgeBrand)
            .filter(
                KnowledgeBrand.vertical_id == self.vertical_id,
                KnowledgeBrand.is_validated == True,
            )
            .limit(30)
            .all()
            if normalize_entity_key(row.display_name) not in candidate_brand_keys
        ]

        known_products = [
            row.display_name
            for row in self.knowledge_db.query(KnowledgeProduct)
            .filter(
                KnowledgeProduct.vertical_id == self.vertical_id,
                KnowledgeProduct.is_validated == True,
            )
            .limit(30)
            .all()
            if normalize_entity_key(row.display_name) not in candidate_product_keys
        ]

        known_rejected = [
            {"name": row.name, "reason": row.reason}
            for row in self.knowledge_db.query(KnowledgeRejectedEntity)
            .filter(KnowledgeRejectedEntity.vertical_id == self.vertical_id)
            .order_by(KnowledgeRejectedEntity.created_at.desc())
            .limit(20)
            .all()
        ]

        return known_brands, known_products, known_rejected

    def _normalize_entities(
        self,
        entities: list[str],
        *,
        entity_type: str,
    ) -> dict[str, str]:
        existing_map = (
            self._existing_brand_alias_map()
            if entity_type == "brand"
            else self._existing_product_alias_map()
        )
        canonical_by_key: OrderedDict[str, str] = OrderedDict()
        normalized: dict[str, str] = {}

        for entity in entities:
            entity = (entity or "").strip()
            if not entity:
                continue
            cleaned = _strip_possessive(entity)
            alias_key = normalize_entity_key(cleaned)
            canonical = existing_map.get(alias_key)
            if not canonical:
                canonical = canonical_by_key.setdefault(alias_key, cleaned)
            normalized[entity] = canonical
        return normalized

    def _build_proximity_map(
        self,
        item_pairs: list[tuple[str | None, str | None]],
        brand_aliases: dict[str, str],
        product_aliases: dict[str, str],
    ) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for brand, product in item_pairs:
            if not brand or not product:
                continue
            canonical_brand = brand_aliases.get(brand, brand)
            canonical_product = product_aliases.get(product, product)
            mapping.setdefault(canonical_product, canonical_brand)
        return mapping

    def _existing_brand_alias_map(self) -> dict[str, str]:
        if self.knowledge_db is None or self.vertical_id is None:
            return {}
        mapping = {
            normalize_entity_key(row.canonical_name): row.canonical_name
            for row in self.knowledge_db.query(KnowledgeBrand)
            .filter(KnowledgeBrand.vertical_id == self.vertical_id)
            .all()
        }
        alias_rows = (
            self.knowledge_db.query(KnowledgeBrandAlias.alias, KnowledgeBrand.canonical_name)
            .join(KnowledgeBrand, KnowledgeBrand.id == KnowledgeBrandAlias.brand_id)
            .filter(KnowledgeBrand.vertical_id == self.vertical_id)
            .all()
        )
        for alias, canonical in alias_rows:
            mapping[normalize_entity_key(alias)] = canonical
        return mapping

    def _existing_product_alias_map(self) -> dict[str, str]:
        if self.knowledge_db is None or self.vertical_id is None:
            return {}
        mapping = {
            normalize_entity_key(row.canonical_name): row.canonical_name
            for row in self.knowledge_db.query(KnowledgeProduct)
            .filter(KnowledgeProduct.vertical_id == self.vertical_id)
            .all()
        }
        alias_rows = (
            self.knowledge_db.query(KnowledgeProductAlias.alias, KnowledgeProduct.canonical_name)
            .join(KnowledgeProduct, KnowledgeProduct.id == KnowledgeProductAlias.product_id)
            .filter(KnowledgeProduct.vertical_id == self.vertical_id)
            .all()
        )
        for alias, canonical in alias_rows:
            mapping[normalize_entity_key(alias)] = canonical
        return mapping

    def _existing_product_brand_map(self) -> dict[str, str]:
        if self.knowledge_db is None or self.vertical_id is None:
            return {}
        rows = (
            self.knowledge_db.query(KnowledgeProduct.canonical_name, KnowledgeBrand.canonical_name)
            .join(KnowledgeProductBrandMapping, KnowledgeProductBrandMapping.product_id == KnowledgeProduct.id)
            .join(KnowledgeBrand, KnowledgeBrand.id == KnowledgeProductBrandMapping.brand_id)
            .filter(KnowledgeProductBrandMapping.vertical_id == self.vertical_id)
            .all()
        )
        return {product: brand for product, brand in rows if product and brand}

    def _has_remote_llm(self) -> bool:
        try:
            from services.remote_llms import OpenRouterService
        except ImportError:
            return False
        return OpenRouterService(db=None).has_api_key()

    async def _call_llm(self, prompt: str, retries: int = 2, temperature: float | None = None) -> str:
        from services.remote_llms import OpenRouterService
        last_error = None
        for model in [OPENROUTER_PRIMARY_MODEL, OPENROUTER_BACKUP_MODEL]:
            for attempt in range(retries):
                try:
                    service = OpenRouterService(db=None)
                    if temperature is not None:
                        service.temperature = temperature
                    answer, _, _, _ = await service.query(prompt, model_name=model)
                    return answer
                except Exception as e:
                    logger.warning(f"OpenRouter {model} failed (attempt {attempt+1}): {e}")
                    last_error = e
        raise RuntimeError(f"All LLM attempts failed: {last_error}")


def _strip_possessive(name: str) -> str:
    import re
    return re.sub(r"[''']s$", "", name.strip())


def _ensure_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return str(value)


def _has_collisions(alias_map: dict[str, str]) -> bool:
    collisions: dict[str, set[str]] = {}
    for alias, canonical in alias_map.items():
        collisions.setdefault(canonical, set()).add(alias)
    return any(len(aliases) > 1 for aliases in collisions.values())


def _extract_parenthetical_aliases(entities: list[str]) -> dict[str, str]:
    import re
    aliases: dict[str, str] = {}
    for entity in entities:
        match = re.match(r'^(.+?)\s*[（(](.+?)[）)]$', entity.strip())
        if not match:
            continue
        outside, inside = match.group(1).strip(), match.group(2).strip()
        if not outside or not inside:
            continue
        outside_is_latin = bool(re.match(r'^[A-Za-z]', outside))
        inside_is_latin = bool(re.match(r'^[A-Za-z]', inside))
        if outside_is_latin and not inside_is_latin:
            aliases[normalize_entity_key(inside)] = outside
        elif inside_is_latin and not outside_is_latin:
            aliases[normalize_entity_key(outside)] = inside
    return aliases


def _apply_parenthetical_aliases(
    normalized: dict[str, str],
    entities: list[str],
) -> dict[str, str]:
    paren_aliases = _extract_parenthetical_aliases(entities)
    if not paren_aliases:
        return normalized
    updated = dict(normalized)
    for entity, canonical in updated.items():
        alias_key = normalize_entity_key(canonical)
        if alias_key in paren_aliases:
            new_canonical = paren_aliases[alias_key]
            updated[entity] = new_canonical
    return updated


def _has_cjk(text: str) -> bool:
    return any('\u4e00' <= c <= '\u9fff' for c in text)


COMMON_WORD_BLOCKLIST = {
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
}


def _is_likely_common_word(entity: str) -> bool:
    cleaned = entity.strip()
    if not cleaned or len(cleaned) < 2:
        return True
    if _has_cjk(cleaned):
        return False
    if any(c.isdigit() for c in cleaned):
        return False
    if cleaned.lower() in COMMON_WORD_BLOCKLIST:
        return True
    if len(cleaned) <= 2 and cleaned.isalpha():
        return True
    if _ends_with_material_suffix(cleaned):
        return True
    return not any(c.isupper() for c in cleaned)


MATERIAL_SUFFIX_BLOCKLIST = {
    "outsole", "membrane", "midsole", "insole", "upper", "sole",
    "lining", "footbed", "shank", "foam", "rubber", "mesh",
    "technology", "system", "material", "compound", "cushioning",
}


def _ends_with_material_suffix(text: str) -> bool:
    parts = text.lower().split()
    return len(parts) >= 2 and parts[-1] in MATERIAL_SUFFIX_BLOCKLIST


def _pre_filter_entities(entities: list[str]) -> tuple[list[str], set[str]]:
    candidates, rejected = [], set()
    for entity in entities:
        if _is_likely_common_word(entity):
            rejected.add(entity)
        else:
            candidates.append(entity)
    return candidates, rejected


def _apply_pre_filter(
    brands: list[str],
    products: list[str],
) -> tuple[list[str], list[str], set[str], set[str], dict[str, str]]:
    brand_candidates, pre_rej_brands = _pre_filter_entities(brands)
    product_candidates, pre_rej_products = _pre_filter_entities(products)
    reasons = {name: "common_word" for name in pre_rej_brands | pre_rej_products}
    logger.info(f"[CONSULTANT] Pre-filter rejected: {len(pre_rej_brands)} brands, {len(pre_rej_products)} products")
    return brand_candidates, product_candidates, pre_rej_brands, pre_rej_products, reasons


def _chunk_list(items: list, size: int) -> list[list]:
    if not items:
        return []
    return [items[i:i + size] for i in range(0, len(items), size)]


def _parse_batch_validation(
    response: str,
    batch_brands: list[str],
    batch_products: list[str],
) -> tuple[set[str], set[str], set[str], set[str], dict[str, str]]:
    parsed = _parse_json_response(response) or {}
    if not parsed:
        logger.warning("[CONSULTANT] Batch validation parsing failed, accepting batch (pre-filter already applied)")
        return set(batch_brands), set(batch_products), set(), set(), {}
    llm_valid_brands = {name for name in parsed.get("valid_brands") or [] if name}
    llm_valid_products = {name for name in parsed.get("valid_products") or [] if name}
    kept_brands = _match_valid_to_input(batch_brands, llm_valid_brands)
    kept_products = _match_valid_to_input(batch_products, llm_valid_products)
    rej_brands = set(batch_brands) - kept_brands
    rej_products = set(batch_products) - kept_products
    logger.info(
        f"[CONSULTANT] Batch result: sent {len(batch_brands)} brands, "
        f"LLM returned {len(llm_valid_brands)} valid, matched {len(kept_brands)}, rejected {len(rej_brands)}"
    )
    if rej_brands:
        logger.info(f"[CONSULTANT] Rejected brands sample: {sorted(rej_brands)[:20]}")
    reasons = {name: "not_relevant_to_vertical" for name in rej_brands | rej_products}
    return kept_brands, kept_products, rej_brands, rej_products, reasons


def _match_valid_to_input(input_entities: list[str], llm_valid: set[str]) -> set[str]:
    llm_valid_lower = {name.lower() for name in llm_valid}
    return {entity for entity in input_entities if entity.lower() in llm_valid_lower}



def _merge_validation_results(
    results: list[tuple[set[str], set[str], set[str], set[str], dict[str, str]]],
) -> tuple[set[str], set[str], set[str], set[str], dict[str, str]]:
    v_brands, v_products, r_brands, r_products, reasons = set(), set(), set(), set(), {}
    for vb, vp, rb, rp, r in results:
        v_brands.update(vb)
        v_products.update(vp)
        r_brands.update(rb)
        r_products.update(rp)
        reasons.update(r)
    return v_brands, v_products, r_brands, r_products, reasons


def _build_reverse_brand_map(brand_aliases: dict[str, str]) -> dict[str, str]:
    reverse: dict[str, str] = {}
    for alias, canonical in brand_aliases.items():
        reverse[alias] = canonical
        reverse[canonical] = canonical
    return reverse


def _strip_brand_prefixes(
    product_aliases: dict[str, str],
    product_brand_map: dict[str, str],
    reverse_brand_map: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    updated_aliases = dict(product_aliases)
    updated_map = dict(product_brand_map)
    brand_names = sorted(reverse_brand_map.keys(), key=len, reverse=True)

    canonical_products = set(updated_aliases.values())
    for product in canonical_products:
        stripped, brand = _try_strip_brand(product, brand_names, reverse_brand_map)
        if not stripped:
            continue
        if len(stripped) < 2:
            continue
        updated_aliases[product] = stripped
        updated_map.setdefault(stripped, brand)

    return updated_aliases, updated_map


def _try_strip_brand(
    product: str,
    brand_names: list[str],
    reverse_brand_map: dict[str, str],
) -> tuple[str | None, str | None]:
    for brand_name in brand_names:
        if len(brand_name) < 2:
            continue
        if not product.startswith(brand_name):
            continue
        remainder = product[len(brand_name):].lstrip(" -·")
        if not remainder or remainder == product:
            continue
        if not _is_valid_product_remainder(remainder):
            continue
        return remainder, reverse_brand_map[brand_name]
    return None, None


def _is_valid_product_remainder(remainder: str) -> bool:
    if len(remainder) < 3:
        return False
    return any(c.isalpha() for c in remainder[:3])


PRODUCT_SUFFIX_TOKENS = {
    "gtx", "wp", "waterproof", "mid", "low", "all-wthr",
    "pro", "plus", "max", "evo", "lite",
}


def _strip_product_suffix(name: str) -> str | None:
    import re
    parts = re.split(r'\s+', name.strip())
    if len(parts) < 2:
        return None
    while len(parts) > 1 and parts[-1].lower() in PRODUCT_SUFFIX_TOKENS:
        parts.pop()
    result = " ".join(parts)
    if result == name.strip() or len(result) < 2:
        return None
    return result


def _merge_suffix_variants(product_aliases: dict[str, str]) -> dict[str, str]:
    updated = dict(product_aliases)
    canonical_set = set(updated.values())
    base_to_canonical: dict[str, str] = {}

    for canonical in sorted(canonical_set, key=len):
        base = _strip_product_suffix(canonical)
        if not base:
            continue
        if base in canonical_set:
            base_to_canonical[canonical] = base
        elif base in base_to_canonical:
            base_to_canonical[canonical] = base_to_canonical[base]
        else:
            base_to_canonical.setdefault(base, canonical)

    remap: dict[str, str] = {}
    for variant, target in base_to_canonical.items():
        if variant != target and target in canonical_set:
            remap[variant] = target

    if not remap:
        return updated
    for alias, canonical in updated.items():
        if canonical in remap:
            updated[alias] = remap[canonical]
    return updated


def _partition_products_by_brand(
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


def _merge_variant_results(
    response: str,
    product_aliases: dict[str, str],
    product_brand_map: dict[str, str],
    brand_aliases: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    parsed = _parse_json_response(response) or {}
    updated_aliases = dict(product_aliases)
    updated_map = dict(product_brand_map)

    for alias, canonical in (parsed.get("product_aliases") or {}).items():
        if alias and canonical:
            updated_aliases[alias] = str(canonical)
    for product, brand in (parsed.get("product_brand_map") or {}).items():
        if product and brand:
            canonical_brand = brand_aliases.get(brand, brand)
            updated_map[product] = canonical_brand

    return updated_aliases, updated_map
