"""DeepSeek-backed normalization and relevance validation.

Falls back to OpenRouter (qwen/qwen3.5-397b-a17b) when DeepSeek is unavailable.
"""

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

OPENROUTER_FALLBACK_MODEL = "qwen/qwen3.5-397b-a17b"
VALIDATION_BATCH_SIZE = 200


class DeepSeekConsultant:
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
            logger.info(f"[CONSULTANT] normalize_and_map completed (no DeepSeek needed)")
            return brand_aliases, product_aliases, product_brand_map

        logger.info(f"[CONSULTANT] Loading prompt...")
        prompt = load_prompt(
            "extraction/deepseek_normalize_map",
            vertical=self.vertical,
            vertical_description=self.vertical_description,
            brands_json=json.dumps(brands, ensure_ascii=False),
            products_json=json.dumps(products, ensure_ascii=False),
            item_pairs_json=json.dumps(item_pairs, ensure_ascii=False),
            existing_product_brand_map_json=json.dumps(product_brand_map, ensure_ascii=False),
        )
        logger.info(f"[CONSULTANT] Calling DeepSeek API...")
        try:
            response = await self._call_deepseek(prompt)
        except Exception as e:
            logger.error(f"[CONSULTANT] Remote normalization failed, using local only: {e}")
            return brand_aliases, product_aliases, product_brand_map
        logger.info(f"[CONSULTANT] DeepSeek API returned, parsing response...")
        parsed = _parse_json_response(response) or {}
        logger.info(f"[CONSULTANT] Response parsed")

        logger.info(f"[CONSULTANT] Merging DeepSeek results...")
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

    async def validate_relevance(
        self,
        brands: list[str],
        products: list[str],
    ) -> tuple[set[str], set[str], set[str], set[str], dict[str, str]]:
        logger.info(f"[CONSULTANT] validate_relevance: {len(brands)} brands, {len(products)} products")
        if not self._has_remote_llm():
            logger.info("[CONSULTANT] No remote LLM available, accepting all entities")
            return set(brands), set(products), set(), set(), {}

        brand_candidates, product_candidates, rej_brands, rej_products, rej_reasons = (
            _apply_pre_filter(brands, products)
        )
        pre_valid_brands = self._find_prevalidated(brand_candidates, "brand")
        pre_valid_products = self._find_prevalidated(product_candidates, "product")
        new_brands = [b for b in brand_candidates if b not in pre_valid_brands]
        new_products = [p for p in product_candidates if p not in pre_valid_products]
        logger.info(f"[CONSULTANT] Auto-accepted: {len(pre_valid_brands)} brands, {len(pre_valid_products)} products")
        known = self._load_validation_context(brands, products)
        v_brands, v_products, r_brands, r_products, reasons = await self._validate_in_batches(
            new_brands, new_products, *known,
        )
        v_brands.update(pre_valid_brands)
        v_products.update(pre_valid_products)
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
            response = await self._call_deepseek(prompt)
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

    def _find_prevalidated(
        self,
        candidates: list[str],
        entity_type: str,
    ) -> set[str]:
        if self.knowledge_db is None or self.vertical_id is None:
            return set()
        model = KnowledgeBrand if entity_type == "brand" else KnowledgeProduct
        validated_keys = {
            normalize_entity_key(row.display_name)
            for row in self.knowledge_db.query(model)
            .filter(model.vertical_id == self.vertical_id, model.is_validated == True)
            .all()
        }
        return {c for c in candidates if normalize_entity_key(c) in validated_keys}

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
            alias_key = normalize_entity_key(entity)
            canonical = existing_map.get(alias_key)
            if not canonical:
                canonical = canonical_by_key.setdefault(alias_key, entity)
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

    def _has_deepseek(self) -> bool:
        try:
            from services.remote_llms import DeepSeekService
        except ImportError:
            return False
        return DeepSeekService(db=None).has_api_key()

    def _has_openrouter(self) -> bool:
        try:
            from services.remote_llms import OpenRouterService
        except ImportError:
            return False
        return OpenRouterService(db=None).has_api_key()

    def _has_remote_llm(self) -> bool:
        return self._has_deepseek() or self._has_openrouter()

    async def _call_deepseek(self, prompt: str, retries: int = 2, temperature: float | None = None) -> str:
        last_error = None
        for attempt in range(retries):
            if self._has_deepseek():
                try:
                    from services.remote_llms import DeepSeekService
                    service = DeepSeekService(db=None)
                    if temperature is not None:
                        service.temperature = temperature
                    answer, _, _, _ = await service.query(prompt)
                    return answer
                except Exception as e:
                    logger.warning(f"DeepSeek API failed (attempt {attempt+1}): {e}")
                    last_error = e

            if self._has_openrouter():
                try:
                    from services.remote_llms import OpenRouterService
                    service = OpenRouterService(db=None)
                    if temperature is not None:
                        service.temperature = temperature
                    answer, _, _, _ = await service.query(prompt, model_name=OPENROUTER_FALLBACK_MODEL)
                    return answer
                except Exception as e:
                    logger.warning(f"OpenRouter API failed (attempt {attempt+1}): {e}")
                    last_error = e

        raise RuntimeError(f"All LLM attempts failed: {last_error}")


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
    "on", "gtx", "wp",
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
    return not any(c.isupper() for c in cleaned)


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
