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
        response = await self._call_deepseek(prompt)
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
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[CONSULTANT] validate_relevance starting: {len(brands)} brands, {len(products)} products")

        valid_brands = set(brands)
        valid_products = set(products)
        rejected_brands: set[str] = set()
        rejected_products: set[str] = set()
        rejection_reasons: dict[str, str] = {}

        if not self._has_remote_llm():
            logger.info(f"[CONSULTANT] No remote LLM available, accepting all entities")
            return valid_brands, valid_products, rejected_brands, rejected_products, rejection_reasons

        known_brands, known_products, known_rejected = self._load_validation_context(brands, products)

        logger.info(f"[CONSULTANT] Loading validation prompt...")
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
        logger.info(f"[CONSULTANT] Calling DeepSeek API for validation...")
        response = await self._call_deepseek(prompt)
        logger.info(f"[CONSULTANT] DeepSeek validation returned, parsing...")
        parsed = _parse_json_response(response) or {}
        logger.info(f"[CONSULTANT] Validation response parsed")

        parsed_valid_brands = {name for name in parsed.get("valid_brands") or [] if name}
        parsed_valid_products = {name for name in parsed.get("valid_products") or [] if name}

        if parsed_valid_brands or parsed_valid_products:
            valid_brands = parsed_valid_brands
            valid_products = parsed_valid_products

        for rejected in parsed.get("rejected") or []:
            name = rejected.get("name")
            reason = rejected.get("reason") or "not relevant to vertical"
            entity_type = (rejected.get("entity_type") or "").lower()
            if not name:
                continue
            rejection_reasons[name] = reason
            if entity_type == "brand":
                rejected_brands.add(name)
            elif entity_type == "product":
                rejected_products.add(name)
            elif name in valid_brands:
                rejected_brands.add(name)
            else:
                rejected_products.add(name)

        valid_brands -= rejected_brands
        valid_products -= rejected_products
        logger.info(f"[CONSULTANT] validate_relevance completed: {len(valid_brands)} valid brands, {len(valid_products)} valid products")
        return valid_brands, valid_products, rejected_brands, rejected_products, rejection_reasons

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

    async def _call_deepseek(self, prompt: str) -> str:
        if self._has_deepseek():
            try:
                from services.remote_llms import DeepSeekService
                service = DeepSeekService(db=None)
                answer, _, _, _ = await service.query(prompt)
                return answer
            except Exception as e:
                logger.warning(f"DeepSeek API failed, falling back to OpenRouter: {e}")

        if self._has_openrouter():
            from services.remote_llms import OpenRouterService
            service = OpenRouterService(db=None)
            answer, _, _, _ = await service.query(prompt, model_name=OPENROUTER_FALLBACK_MODEL)
            return answer

        raise RuntimeError("No remote LLM available (neither DeepSeek nor OpenRouter)")


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
