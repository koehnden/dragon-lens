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
from services.extraction.normalizer import (
    apply_parenthetical_aliases,
    ensure_str,
    has_collisions,
    parse_json_response,
    strip_possessive,
)
from services.extraction.pre_filter import apply_pre_filter
from services.extraction.product_consolidation import (
    build_reverse_brand_map,
    merge_suffix_variants,
    merge_variant_results,
    partition_products_by_brand,
    strip_brand_prefixes,
)
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
        logger.info("[CONSULTANT] normalize_and_map: %d brands, %d products", len(brands), len(products))
        brand_aliases, product_aliases, product_brand_map = self._local_normalize(brands, products, item_pairs)
        if not self._needs_remote_normalization(brands, products, brand_aliases, product_aliases, product_brand_map):
            return brand_aliases, product_aliases, product_brand_map
        return await self._remote_normalize(brands, products, item_pairs, brand_aliases, product_aliases, product_brand_map)

    def _local_normalize(
        self,
        brands: list[str],
        products: list[str],
        item_pairs: list[tuple[str | None, str | None]],
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        brand_aliases = apply_parenthetical_aliases(self._normalize_entities(brands, entity_type="brand"), brands)
        product_aliases = apply_parenthetical_aliases(self._normalize_entities(products, entity_type="product"), products)
        product_brand_map = self._build_proximity_map(item_pairs, brand_aliases, product_aliases)
        product_brand_map.update(self._existing_product_brand_map())
        return brand_aliases, product_aliases, product_brand_map

    def _needs_remote_normalization(
        self,
        brands: list[str],
        products: list[str],
        brand_aliases: dict[str, str],
        product_aliases: dict[str, str],
        product_brand_map: dict[str, str],
    ) -> bool:
        if not self._has_remote_llm():
            return False
        has_unmapped = any(product_aliases.get(p, p) not in product_brand_map for p in products)
        return has_collisions(brand_aliases) or has_collisions(product_aliases) or has_unmapped

    async def _remote_normalize(
        self,
        brands: list[str],
        products: list[str],
        item_pairs: list[tuple[str | None, str | None]],
        brand_aliases: dict[str, str],
        product_aliases: dict[str, str],
        product_brand_map: dict[str, str],
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        prompt = self._build_normalize_prompt(brands, products, item_pairs, product_brand_map)
        try:
            response = await self._call_llm(prompt)
        except Exception as e:
            logger.error("[CONSULTANT] Remote normalization failed: %s", e)
            return brand_aliases, product_aliases, product_brand_map
        _merge_remote_aliases(parse_json_response(response) or {}, brand_aliases, product_aliases, product_brand_map)
        return brand_aliases, product_aliases, product_brand_map

    def _build_normalize_prompt(
        self,
        brands: list[str],
        products: list[str],
        item_pairs: list[tuple[str | None, str | None]],
        product_brand_map: dict[str, str],
    ) -> str:
        return load_prompt(
            "extraction/consolidation_normalize_map",
            vertical=self.vertical,
            vertical_description=self.vertical_description,
            brands_json=json.dumps(brands, ensure_ascii=False),
            products_json=json.dumps(products, ensure_ascii=False),
            item_pairs_json=json.dumps(item_pairs, ensure_ascii=False),
            existing_product_brand_map_json=json.dumps(product_brand_map, ensure_ascii=False),
        )

    async def consolidate_products(
        self,
        product_aliases: dict[str, str],
        product_brand_map: dict[str, str],
        brand_aliases: dict[str, str],
    ) -> tuple[dict[str, str], dict[str, str]]:
        reverse_brand_map = build_reverse_brand_map(brand_aliases)
        product_aliases, product_brand_map = strip_brand_prefixes(product_aliases, product_brand_map, reverse_brand_map)
        product_aliases = merge_suffix_variants(product_aliases)
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
        products_by_brand, unmapped = partition_products_by_brand(product_aliases, product_brand_map)
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
            logger.error("[CONSULTANT] Variant grouping failed: %s", e)
            return product_aliases, product_brand_map
        return merge_variant_results(response, product_aliases, product_brand_map, brand_aliases)

    async def validate_relevance(
        self,
        brands: list[str],
        products: list[str],
    ) -> tuple[set[str], set[str], set[str], set[str], dict[str, str]]:
        logger.info("[CONSULTANT] validate_relevance: %d brands, %d products", len(brands), len(products))
        brand_cands, product_cands, rej_brands, rej_products, rej_reasons = apply_pre_filter(brands, products)
        if not self._has_remote_llm():
            return set(brand_cands), set(product_cands), rej_brands, rej_products, rej_reasons
        known = self._load_validation_context(brands, products)
        v_brands, v_products, r_brands, r_products, reasons = await self._validate_in_batches(
            brand_cands, product_cands, *known,
        )
        return _combine_rejections(v_brands, v_products, rej_brands | r_brands, rej_products | r_products, rej_reasons | reasons)

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
        results = []
        for i in range(n_batches):
            b = brand_batches[i] if i < len(brand_batches) else []
            p = product_batches[i] if i < len(product_batches) else []
            logger.debug("[CONSULTANT] Batch %d/%d: %d brands, %d products", i + 1, n_batches, len(b), len(p))
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
            logger.error("[CONSULTANT] Batch validation failed: %s", e)
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
        for entity_type, names in ((EntityType.BRAND, rejected_brands), (EntityType.PRODUCT, rejected_products)):
            for name in names:
                self._store_single_rejection(entity_type, name, rejection_reasons)

    def _store_single_rejection(
        self,
        entity_type: EntityType,
        name: str,
        rejection_reasons: dict[str, str],
    ) -> None:
        alias_key = normalize_entity_key(name)
        exists = (
            self.knowledge_db.query(KnowledgeRejectedEntity)
            .filter(
                KnowledgeRejectedEntity.vertical_id == self.vertical_id,
                KnowledgeRejectedEntity.entity_type == entity_type,
                KnowledgeRejectedEntity.alias_key == alias_key,
            )
            .first()
        )
        if exists:
            return
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
        brand_keys = {normalize_entity_key(b) for b in candidate_brands}
        product_keys = {normalize_entity_key(p) for p in candidate_products}
        return (
            self._query_known_entities(KnowledgeBrand, brand_keys),
            self._query_known_entities(KnowledgeProduct, product_keys),
            self._query_known_rejected(),
        )

    def _query_known_entities(
        self,
        model_cls: type[KnowledgeBrand] | type[KnowledgeProduct],
        exclude_keys: set[str],
    ) -> list[str]:
        rows = (
            self.knowledge_db.query(model_cls)
            .filter(model_cls.vertical_id == self.vertical_id, model_cls.is_validated == True)
            .limit(30)
            .all()
        )
        return [r.display_name for r in rows if normalize_entity_key(r.display_name) not in exclude_keys]

    def _query_known_rejected(self) -> list[dict]:
        rows = (
            self.knowledge_db.query(KnowledgeRejectedEntity)
            .filter(KnowledgeRejectedEntity.vertical_id == self.vertical_id)
            .order_by(KnowledgeRejectedEntity.created_at.desc())
            .limit(20)
            .all()
        )
        return [{"name": r.name, "reason": r.reason} for r in rows]

    def _normalize_entities(
        self,
        entities: list[str],
        *,
        entity_type: str,
    ) -> dict[str, str]:
        existing_map = self._existing_alias_map(entity_type)
        canonical_by_key: OrderedDict[str, str] = OrderedDict()
        normalized: dict[str, str] = {}
        for entity in entities:
            entity = (entity or "").strip()
            if not entity:
                continue
            cleaned = strip_possessive(entity)
            alias_key = normalize_entity_key(cleaned)
            canonical = existing_map.get(alias_key) or canonical_by_key.setdefault(alias_key, cleaned)
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
            mapping.setdefault(product_aliases.get(product, product), brand_aliases.get(brand, brand))
        return mapping

    def _existing_alias_map(self, entity_type: str) -> dict[str, str]:
        if entity_type == "brand":
            return self._query_alias_map(KnowledgeBrand, KnowledgeBrandAlias, "brand_id")
        return self._query_alias_map(KnowledgeProduct, KnowledgeProductAlias, "product_id")

    def _query_alias_map(
        self,
        model_cls: type[KnowledgeBrand] | type[KnowledgeProduct],
        alias_cls: type[KnowledgeBrandAlias] | type[KnowledgeProductAlias],
        fk_attr: str,
    ) -> dict[str, str]:
        if self.knowledge_db is None or self.vertical_id is None:
            return {}
        mapping = {
            normalize_entity_key(r.canonical_name): r.canonical_name
            for r in self.knowledge_db.query(model_cls).filter(model_cls.vertical_id == self.vertical_id).all()
        }
        alias_rows = (
            self.knowledge_db.query(alias_cls.alias, model_cls.canonical_name)
            .join(model_cls, model_cls.id == getattr(alias_cls, fk_attr))
            .filter(model_cls.vertical_id == self.vertical_id)
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
                    logger.warning("OpenRouter %s failed (attempt %d): %s", model, attempt + 1, e)
                    last_error = e
        raise RuntimeError(f"All LLM attempts failed: {last_error}")


def _merge_remote_aliases(
    parsed: dict,
    brand_aliases: dict[str, str],
    product_aliases: dict[str, str],
    product_brand_map: dict[str, str],
) -> None:
    for alias, canonical in (parsed.get("brand_aliases") or {}).items():
        if alias:
            brand_aliases[alias] = ensure_str(canonical) or alias
    for alias, canonical in (parsed.get("product_aliases") or {}).items():
        if alias:
            product_aliases[alias] = ensure_str(canonical) or alias
    for product, brand in (parsed.get("product_brand_map") or {}).items():
        if product and brand:
            product_brand_map[product_aliases.get(product, product)] = brand_aliases.get(brand, brand)


def _combine_rejections(
    v_brands: set[str],
    v_products: set[str],
    rej_brands: set[str],
    rej_products: set[str],
    rej_reasons: dict[str, str],
) -> tuple[set[str], set[str], set[str], set[str], dict[str, str]]:
    logger.info("[CONSULTANT] validate done: %d brands, %d products", len(v_brands - rej_brands), len(v_products - rej_products))
    return v_brands - rej_brands, v_products - rej_products, rej_brands, rej_products, rej_reasons


def _chunk_list(items: list, size: int) -> list[list]:
    if not items:
        return []
    return [items[i:i + size] for i in range(0, len(items), size)]


def _parse_batch_validation(
    response: str,
    batch_brands: list[str],
    batch_products: list[str],
) -> tuple[set[str], set[str], set[str], set[str], dict[str, str]]:
    parsed = parse_json_response(response) or {}
    if not parsed:
        logger.warning("[CONSULTANT] Batch validation parse failed, accepting batch")
        return set(batch_brands), set(batch_products), set(), set(), {}
    kept_brands = _match_valid_to_input(batch_brands, parsed.get("valid_brands") or [])
    kept_products = _match_valid_to_input(batch_products, parsed.get("valid_products") or [])
    rej_brands = set(batch_brands) - kept_brands
    rej_products = set(batch_products) - kept_products
    logger.debug("[CONSULTANT] Batch: %d brands sent, %d kept, %d rejected", len(batch_brands), len(kept_brands), len(rej_brands))
    return kept_brands, kept_products, rej_brands, rej_products, {n: "not_relevant_to_vertical" for n in rej_brands | rej_products}


def _match_valid_to_input(input_entities: list[str], llm_valid: list) -> set[str]:
    valid_lower = {str(name).lower() for name in llm_valid if name}
    return {entity for entity in input_entities if entity.lower() in valid_lower}


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
