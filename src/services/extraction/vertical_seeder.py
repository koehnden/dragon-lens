"""Step -1: Cold start seeding for verticals with sparse knowledge bases."""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from services.extraction.normalizer import parse_json_response

from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeProductBrandMapping,
    KnowledgeVertical,
)
from services.knowledge_verticals import normalize_entity_key

logger = logging.getLogger(__name__)

SEED_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "extraction" / "seed_vertical.md"

MIN_VALIDATED_BRANDS = 10


@dataclass
class _BrandCache:
    by_id: dict[int, KnowledgeBrand] = field(default_factory=dict)
    by_alias_key: dict[str, KnowledgeBrand] = field(default_factory=dict)
    alias_keys_by_brand_id: dict[int, set[str]] = field(default_factory=dict)


@dataclass
class _ProductCache:
    by_id: dict[int, KnowledgeProduct] = field(default_factory=dict)
    by_alias_key: dict[str, KnowledgeProduct] = field(default_factory=dict)
    alias_keys_by_product_id: dict[int, set[str]] = field(default_factory=dict)
    mapping_pairs: set[tuple[int, int]] = field(default_factory=set)


class VerticalSeeder:
    """Seed a vertical's knowledge base for cold start."""

    def __init__(self, vertical: str, vertical_description: str, vertical_id: int):
        self.vertical = vertical
        self.vertical_description = vertical_description
        self.vertical_id = vertical_id

    def should_seed(self, db: Session) -> bool:
        """Check if vertical needs a one-time seed bootstrap."""
        vertical = db.query(KnowledgeVertical).filter(
            KnowledgeVertical.id == self.vertical_id
        ).first()
        if vertical and vertical.seeded_at is not None:
            return False

        count = (
            db.query(KnowledgeBrand)
            .filter(
                KnowledgeBrand.vertical_id == self.vertical_id,
                KnowledgeBrand.is_validated == True,
            )
            .count()
        )
        return count < MIN_VALIDATED_BRANDS

    def seed_from_user_brands(self, db: Session, user_brands: list[dict]) -> int:
        """Insert user-provided brands + aliases as validated.

        Args:
            db: Knowledge DB session
            user_brands: List of brand dicts with display_name and aliases
                         (from example JSON format: {"display_name": "VW",
                          "aliases": {"zh": [...], "en": [...]}})

        Returns:
            Count of brands seeded.
        """
        seeded = 0
        updated_existing = False
        brand_cache = self._load_brand_cache(db)

        with db.begin_nested():
            for brand_data in user_brands:
                display_name = brand_data.get("display_name", "")
                if not display_name:
                    continue

                alias_texts = {display_name}
                aliases = brand_data.get("aliases", {}) or {}
                for alias_list in aliases.values():
                    alias_texts.update(a for a in alias_list if a)

                existing = self._find_existing_brand(db, alias_texts, brand_cache=brand_cache)
                if existing:
                    self._add_brand_aliases(
                        db,
                        existing.id,
                        aliases,
                        brand_cache=brand_cache,
                    )
                    if not existing.is_validated:
                        existing.is_validated = True
                        existing.validation_source = "user"
                        updated_existing = True
                    continue

                brand = KnowledgeBrand(
                    vertical_id=self.vertical_id,
                    canonical_name=display_name,
                    display_name=display_name,
                    is_validated=True,
                    validation_source="user",
                )
                db.add(brand)
                db.flush()

                self._register_brand(brand_cache, brand)
                self._add_brand_aliases(
                    db,
                    brand.id,
                    aliases,
                    brand_cache=brand_cache,
                )
                seeded += 1

            if seeded or updated_existing:
                db.flush()
        if seeded:
            logger.info(
                "Seeded %d user brands for vertical '%s'", seeded, self.vertical
            )
        return seeded

    async def seed_from_remote_llm(self, db: Session) -> int:
        from services.extraction.consultant import OPENROUTER_PRIMARY_MODEL
        try:
            from services.remote_llms import OpenRouterService
        except ImportError:
            logger.warning("OpenRouterService not available, skipping seed")
            return 0

        service = OpenRouterService(db=None)
        if not service.has_api_key():
            logger.info("No OpenRouter API key, skipping seed for '%s'", self.vertical)
            return 0

        prompt = self._build_seed_prompt()
        logger.info(f"[SEEDER] Calling OpenRouter for seed...")
        try:
            answer, _, _, _ = await service.query(prompt, model_name=OPENROUTER_PRIMARY_MODEL)
            logger.info(f"[SEEDER] OpenRouter returned successfully, answer length={len(answer)}")
        except Exception:
            logger.exception("Remote LLM seed call failed for '%s'", self.vertical)
            return 0

        return self._store_seed_response(db, answer)

    async def ensure_seeded(
        self,
        db: Session,
        user_brands: Optional[list[dict]] = None,
    ) -> None:
        """Main entry point: seed if needed, skip if already seeded.

        Order:
        1. Insert user brands first (ground truth, validated=True)
        2. If still < 10 validated, call remote LLM for market knowledge
        3. LLM results stored as unvalidated seeds
        """
        if user_brands:
            self.seed_from_user_brands(db, user_brands)

        vertical = db.query(KnowledgeVertical).filter(
            KnowledgeVertical.id == self.vertical_id
        ).first()
        if vertical and vertical.seeded_at is not None:
            db.flush()
            return

        if self.should_seed(db):
            seeded = await self.seed_from_remote_llm(db)
            if seeded:
                self._mark_seeded(db, "openrouter_v1")
        elif self._validated_brand_count(db) >= MIN_VALIDATED_BRANDS:
            self._mark_seeded(db, "user_only")

        db.flush()

    def _build_seed_prompt(self) -> str:
        template = SEED_PROMPT_PATH.read_text(encoding="utf-8")
        return template.replace(
            "{{ vertical }}", _sanitize_prompt_value(self.vertical)
        ).replace(
            "{{ vertical_description }}", _sanitize_prompt_value(self.vertical_description)
        )

    def _store_seed_response(self, db: Session, response_text: str) -> int:
        logger.info(f"[SEEDER] _store_seed_response starting, parsing response...")
        data = parse_json_response(response_text)
        if not data or "brands" not in data:
            logger.warning("Could not parse seed response")
            return 0
        logger.info(f"[SEEDER] Parsed {len(data.get('brands', []))} brands from response")

        seeded = 0
        logger.info(f"[SEEDER] Loading brand and product caches...")
        brand_cache = self._load_brand_cache(db)
        product_cache = self._load_product_cache(db)
        logger.info(f"[SEEDER] Caches loaded")

        logger.info(f"[SEEDER] Beginning nested transaction...")
        with db.begin_nested():
            logger.info(f"[SEEDER] Processing brands...")
            for i, brand_data in enumerate(data["brands"]):
                logger.info(f"[SEEDER] Processing brand {i+1}/{len(data['brands'])}")
                brand = self._store_seed_brand(db, brand_data, brand_cache=brand_cache)
                if not brand:
                    logger.info(f"[SEEDER] Brand {i+1} skipped (already exists or invalid)")
                    continue
                seeded += 1
                logger.info(f"[SEEDER] Brand {i+1} stored, seeded count={seeded}")

                products = brand_data.get("products", [])
                logger.info(f"[SEEDER] Processing {len(products)} products for brand {i+1}")
                for j, product_data in enumerate(products):
                    logger.info(f"[SEEDER] Processing product {j+1}/{len(products)}")
                    self._store_seed_product(
                        db,
                        brand,
                        product_data,
                        product_cache=product_cache,
                    )
                    logger.info(f"[SEEDER] Product {j+1} stored")

            if seeded:
                logger.info(f"[SEEDER] Flushing {seeded} seeded brands...")
                db.flush()
                logger.info(f"[SEEDER] Flush completed")
            logger.info(
                "Seeded %d brands from remote LLM for vertical '%s'",
                seeded, self.vertical,
            )
        logger.info(f"[SEEDER] _store_seed_response completed")
        return seeded

    def _store_seed_brand(
        self,
        db: Session,
        brand_data: dict,
        *,
        brand_cache: _BrandCache | None = None,
    ) -> Optional[KnowledgeBrand]:
        """Store a single brand from the seed response."""
        name_en = brand_data.get("name_en", "")
        name_zh = brand_data.get("name_zh", "")
        display_name = name_en or name_zh
        if not display_name:
            return None

        alias_texts = {display_name, name_en, name_zh}
        alias_texts.update(a for a in brand_data.get("aliases", []) if a)
        existing = self._find_existing_brand(db, alias_texts, brand_cache=brand_cache)
        if existing:
            self._add_seed_brand_aliases(
                db,
                existing.id,
                name_en,
                name_zh,
                brand_data.get("aliases", []),
                brand_cache=brand_cache,
            )
            return existing

        brand = KnowledgeBrand(
            vertical_id=self.vertical_id,
            canonical_name=display_name,
            display_name=display_name,
            is_validated=False,
            validation_source="seed",
        )
        db.add(brand)
        db.flush()

        if brand_cache is not None:
            self._register_brand(brand_cache, brand)
        self._add_seed_brand_aliases(
            db,
            brand.id,
            name_en,
            name_zh,
            brand_data.get("aliases", []),
            brand_cache=brand_cache,
        )

        return brand

    def _store_seed_product(
        self,
        db: Session,
        brand: KnowledgeBrand,
        product_data: dict,
        *,
        product_cache: _ProductCache | None = None,
    ) -> Optional[KnowledgeProduct]:
        """Store a single product from the seed response."""
        name = product_data.get("name", "")
        if not name:
            return None

        alias_texts = {name}
        alias_texts.update(a for a in product_data.get("aliases", []) if a)
        existing = self._find_existing_product(db, alias_texts, product_cache=product_cache)
        if existing:
            self._ensure_product_brand_mapping(
                db,
                product_id=existing.id,
                brand_id=brand.id,
                product_cache=product_cache,
            )
            return existing

        product = KnowledgeProduct(
            vertical_id=self.vertical_id,
            brand_id=brand.id,
            canonical_name=name,
            display_name=name,
            is_validated=False,
            validation_source="seed",
        )
        db.add(product)
        db.flush()
        if product_cache is not None:
            self._register_product(product_cache, product)

        # Add product aliases
        existing_alias_keys = (
            product_cache.alias_keys_by_product_id.setdefault(product.id, set())
            if product_cache is not None
            else None
        )
        for alias_text in product_data.get("aliases", []):
            if not alias_text or alias_text == name:
                continue
            alias_key = normalize_entity_key(alias_text)
            if existing_alias_keys is not None and alias_key in existing_alias_keys:
                continue
            if existing_alias_keys is None:
                existing_alias = (
                    db.query(KnowledgeProductAlias)
                    .filter(
                        KnowledgeProductAlias.product_id == product.id,
                        KnowledgeProductAlias.alias_key == alias_key,
                    )
                    .first()
                )
                if existing_alias:
                    continue
            db.add(
                KnowledgeProductAlias(
                    product_id=product.id,
                    alias=alias_text,
                )
            )
            if existing_alias_keys is not None:
                existing_alias_keys.add(alias_key)
                product_cache.by_alias_key[alias_key] = product

        # Create product-brand mapping
        self._ensure_product_brand_mapping(
            db,
            product_id=product.id,
            brand_id=brand.id,
            product_cache=product_cache,
        )

        return product

    def _add_brand_aliases(
        self,
        db: Session,
        brand_id: int,
        aliases: dict[str, list[str]],
        *,
        brand_cache: _BrandCache | None = None,
    ) -> None:
        """Add brand aliases from user brand data format."""
        existing_alias_keys = (
            brand_cache.alias_keys_by_brand_id.setdefault(brand_id, set())
            if brand_cache is not None
            else None
        )
        for lang, alias_list in aliases.items():
            for alias_text in alias_list:
                if not alias_text:
                    continue
                a_key = normalize_entity_key(alias_text)
                if existing_alias_keys is not None and a_key in existing_alias_keys:
                    continue
                if existing_alias_keys is None:
                    existing = (
                        db.query(KnowledgeBrandAlias)
                        .filter(
                            KnowledgeBrandAlias.brand_id == brand_id,
                            KnowledgeBrandAlias.alias_key == a_key,
                        )
                        .first()
                    )
                    if existing:
                        continue
                db.add(
                    KnowledgeBrandAlias(
                        brand_id=brand_id,
                        alias=alias_text,
                        language=lang,
                    )
                )
                if existing_alias_keys is not None:
                    existing_alias_keys.add(a_key)
                    brand = brand_cache.by_id.get(brand_id)
                    if brand is not None:
                        brand_cache.by_alias_key[a_key] = brand

    def _add_seed_brand_aliases(
        self,
        db: Session,
        brand_id: int,
        name_en: str,
        name_zh: str,
        aliases: list[str],
        *,
        brand_cache: _BrandCache | None = None,
    ) -> None:
        alias_payloads: list[tuple[str, str | None]] = []
        if name_zh:
            alias_payloads.append((name_zh, "zh"))
        if name_en:
            alias_payloads.append((name_en, "en"))
        for alias in aliases:
            if alias and alias not in {name_en, name_zh}:
                alias_payloads.append((alias, None))

        existing_alias_keys = (
            brand_cache.alias_keys_by_brand_id.setdefault(brand_id, set())
            if brand_cache is not None
            else None
        )
        for alias_text, language in alias_payloads:
            alias_key = normalize_entity_key(alias_text)
            if existing_alias_keys is not None and alias_key in existing_alias_keys:
                continue
            if existing_alias_keys is None:
                existing_alias = (
                    db.query(KnowledgeBrandAlias)
                    .filter(
                        KnowledgeBrandAlias.brand_id == brand_id,
                        KnowledgeBrandAlias.alias_key == alias_key,
                    )
                    .first()
                )
                if existing_alias:
                    continue
            db.add(
                KnowledgeBrandAlias(
                    brand_id=brand_id,
                    alias=alias_text,
                    language=language,
                )
            )
            if existing_alias_keys is not None:
                existing_alias_keys.add(alias_key)
                brand = brand_cache.by_id.get(brand_id)
                if brand is not None:
                    brand_cache.by_alias_key[alias_key] = brand

    def _find_existing_brand(
        self,
        db: Session,
        alias_texts: set[str],
        *,
        brand_cache: _BrandCache | None = None,
    ) -> Optional[KnowledgeBrand]:
        alias_keys = {normalize_entity_key(text) for text in alias_texts if text}
        alias_keys.discard("")
        if not alias_keys:
            return None

        if brand_cache is not None:
            for alias_key in alias_keys:
                existing = brand_cache.by_alias_key.get(alias_key)
                if existing:
                    return existing

        existing = (
            db.query(KnowledgeBrand)
            .filter(
                KnowledgeBrand.vertical_id == self.vertical_id,
                KnowledgeBrand.alias_key.in_(alias_keys),
            )
            .first()
        )
        if existing:
            return existing

        alias_row = (
            db.query(KnowledgeBrandAlias)
            .join(KnowledgeBrand, KnowledgeBrand.id == KnowledgeBrandAlias.brand_id)
            .filter(
                KnowledgeBrand.vertical_id == self.vertical_id,
                KnowledgeBrandAlias.alias_key.in_(alias_keys),
            )
            .first()
        )
        if not alias_row:
            return None
        return (
            db.query(KnowledgeBrand)
            .filter(KnowledgeBrand.id == alias_row.brand_id)
            .first()
        )

    def _find_existing_product(
        self,
        db: Session,
        alias_texts: set[str],
        *,
        product_cache: _ProductCache | None = None,
    ) -> Optional[KnowledgeProduct]:
        alias_keys = {normalize_entity_key(text) for text in alias_texts if text}
        alias_keys.discard("")
        if not alias_keys:
            return None

        if product_cache is not None:
            for alias_key in alias_keys:
                existing = product_cache.by_alias_key.get(alias_key)
                if existing:
                    return existing

        existing = (
            db.query(KnowledgeProduct)
            .filter(
                KnowledgeProduct.vertical_id == self.vertical_id,
                KnowledgeProduct.alias_key.in_(alias_keys),
            )
            .first()
        )
        if existing:
            return existing

        alias_row = (
            db.query(KnowledgeProductAlias)
            .join(KnowledgeProduct, KnowledgeProduct.id == KnowledgeProductAlias.product_id)
            .filter(
                KnowledgeProduct.vertical_id == self.vertical_id,
                KnowledgeProductAlias.alias_key.in_(alias_keys),
            )
            .first()
        )
        if not alias_row:
            return None
        return (
            db.query(KnowledgeProduct)
            .filter(KnowledgeProduct.id == alias_row.product_id)
            .first()
        )

    def _mark_seeded(self, db: Session, seed_version: str) -> None:
        vertical = db.query(KnowledgeVertical).filter(
            KnowledgeVertical.id == self.vertical_id
        ).first()
        if not vertical or vertical.seeded_at is not None:
            return
        vertical.seeded_at = datetime.now(timezone.utc)
        vertical.seed_version = seed_version

    def _validated_brand_count(self, db: Session) -> int:
        return (
            db.query(KnowledgeBrand)
            .filter(
                KnowledgeBrand.vertical_id == self.vertical_id,
                KnowledgeBrand.is_validated == True,
            )
            .count()
        )

    def _load_brand_cache(self, db: Session) -> _BrandCache:
        cache = _BrandCache()
        brands = (
            db.query(KnowledgeBrand)
            .filter(KnowledgeBrand.vertical_id == self.vertical_id)
            .all()
        )
        brands_by_id = {brand.id: brand for brand in brands}
        for brand in brands:
            self._register_brand(cache, brand)

        alias_rows = (
            db.query(KnowledgeBrandAlias.brand_id, KnowledgeBrandAlias.alias_key)
            .join(KnowledgeBrand, KnowledgeBrand.id == KnowledgeBrandAlias.brand_id)
            .filter(KnowledgeBrand.vertical_id == self.vertical_id)
            .all()
        )
        for brand_id, alias_key in alias_rows:
            brand = brands_by_id.get(brand_id)
            if not brand or not alias_key:
                continue
            cache.by_alias_key[alias_key] = brand
            cache.alias_keys_by_brand_id.setdefault(brand_id, set()).add(alias_key)
        return cache

    def _load_product_cache(self, db: Session) -> _ProductCache:
        cache = _ProductCache()
        products = (
            db.query(KnowledgeProduct)
            .filter(KnowledgeProduct.vertical_id == self.vertical_id)
            .all()
        )
        products_by_id = {product.id: product for product in products}
        for product in products:
            self._register_product(cache, product)

        alias_rows = (
            db.query(KnowledgeProductAlias.product_id, KnowledgeProductAlias.alias_key)
            .join(KnowledgeProduct, KnowledgeProduct.id == KnowledgeProductAlias.product_id)
            .filter(KnowledgeProduct.vertical_id == self.vertical_id)
            .all()
        )
        for product_id, alias_key in alias_rows:
            product = products_by_id.get(product_id)
            if not product or not alias_key:
                continue
            cache.by_alias_key[alias_key] = product
            cache.alias_keys_by_product_id.setdefault(product_id, set()).add(alias_key)

        cache.mapping_pairs = {
            (product_id, brand_id)
            for product_id, brand_id in db.query(
                KnowledgeProductBrandMapping.product_id,
                KnowledgeProductBrandMapping.brand_id,
            )
            .filter(KnowledgeProductBrandMapping.vertical_id == self.vertical_id)
            .all()
            if product_id and brand_id
        }
        return cache

    def _register_brand(self, cache: _BrandCache, brand: KnowledgeBrand) -> None:
        if not brand.id:
            return
        cache.by_id[brand.id] = brand
        cache.by_alias_key[brand.alias_key] = brand
        cache.alias_keys_by_brand_id.setdefault(brand.id, set())

    def _register_product(self, cache: _ProductCache, product: KnowledgeProduct) -> None:
        if not product.id:
            return
        cache.by_id[product.id] = product
        cache.by_alias_key[product.alias_key] = product
        cache.alias_keys_by_product_id.setdefault(product.id, set())

    def _ensure_product_brand_mapping(
        self,
        db: Session,
        *,
        product_id: int,
        brand_id: int,
        product_cache: _ProductCache | None = None,
    ) -> None:
        mapping_key = (product_id, brand_id)
        if product_cache is not None and mapping_key in product_cache.mapping_pairs:
            return
        if product_cache is None:
            existing = (
                db.query(KnowledgeProductBrandMapping)
                .filter(
                    KnowledgeProductBrandMapping.vertical_id == self.vertical_id,
                    KnowledgeProductBrandMapping.product_id == product_id,
                    KnowledgeProductBrandMapping.brand_id == brand_id,
                )
                .first()
            )
            if existing:
                return
        db.add(
            KnowledgeProductBrandMapping(
                vertical_id=self.vertical_id,
                product_id=product_id,
                brand_id=brand_id,
                is_validated=False,
                source="seed",
            )
        )
        if product_cache is not None:
            product_cache.mapping_pairs.add(mapping_key)



def _sanitize_prompt_value(value: str) -> str:
    cleaned = re.sub(r"`{3,}", "", (value or ""))
    cleaned = cleaned.replace("\x00", " ").strip()
    return cleaned[:1000]
