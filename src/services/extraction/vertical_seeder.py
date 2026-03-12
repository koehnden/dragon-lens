"""Step -1: Cold start seeding for verticals with sparse knowledge bases."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

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

SEED_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "extraction" / "deepseek_seed_vertical.md"

MIN_VALIDATED_BRANDS = 10


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
        for brand_data in user_brands:
            display_name = brand_data.get("display_name", "")
            if not display_name:
                continue

            alias_texts = {display_name}
            aliases = brand_data.get("aliases", {}) or {}
            for alias_list in aliases.values():
                alias_texts.update(a for a in alias_list if a)

            existing = self._find_existing_brand(db, alias_texts)
            if existing:
                self._add_brand_aliases(db, existing.id, aliases)
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

            self._add_brand_aliases(db, brand.id, aliases)
            seeded += 1

        if seeded or updated_existing:
            db.flush()
        if seeded:
            logger.info(
                "Seeded %d user brands for vertical '%s'", seeded, self.vertical
            )
        return seeded

    async def seed_from_deepseek(self, db: Session) -> int:
        """Ask DeepSeek for top brands/products for this vertical.

        Stores everything with is_validated=False, source="seed".
        Returns count of brands seeded.
        """
        try:
            from services.remote_llms import DeepSeekService
        except ImportError:
            logger.warning("DeepSeekService not available, skipping seed")
            return 0

        deepseek = DeepSeekService(db=None)
        if not deepseek.has_api_key():
            logger.info("No DeepSeek API key, skipping seed for '%s'", self.vertical)
            return 0

        prompt = self._build_seed_prompt()
        try:
            answer, _, _, _ = await deepseek.query(prompt)
        except Exception:
            logger.exception("DeepSeek seed call failed for '%s'", self.vertical)
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
        2. If still < 10 validated, call DeepSeek for market knowledge
        3. DeepSeek results stored as unvalidated seeds
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
            seeded = await self.seed_from_deepseek(db)
            if seeded:
                self._mark_seeded(db, "deepseek_v1")
        elif self._validated_brand_count(db) >= MIN_VALIDATED_BRANDS:
            self._mark_seeded(db, "user_only")

        db.flush()

    def _build_seed_prompt(self) -> str:
        """Build the DeepSeek seed prompt from template."""
        template = SEED_PROMPT_PATH.read_text(encoding="utf-8")
        return template.replace(
            "{{ vertical }}", self.vertical
        ).replace(
            "{{ vertical_description }}", self.vertical_description
        )

    def _store_seed_response(self, db: Session, response_text: str) -> int:
        """Parse DeepSeek JSON response and store brands/products."""
        data = _parse_json_response(response_text)
        if not data or "brands" not in data:
            logger.warning("Could not parse DeepSeek seed response")
            return 0

        seeded = 0
        for brand_data in data["brands"]:
            brand = self._store_seed_brand(db, brand_data)
            if not brand:
                continue
            seeded += 1

            for product_data in brand_data.get("products", []):
                self._store_seed_product(db, brand, product_data)

        if seeded:
            db.flush()
            logger.info(
                "Seeded %d brands from DeepSeek for vertical '%s'",
                seeded, self.vertical,
            )
        return seeded

    def _store_seed_brand(
        self, db: Session, brand_data: dict
    ) -> Optional[KnowledgeBrand]:
        """Store a single brand from the seed response."""
        name_en = brand_data.get("name_en", "")
        name_zh = brand_data.get("name_zh", "")
        display_name = name_en or name_zh
        if not display_name:
            return None

        alias_texts = {display_name, name_en, name_zh}
        alias_texts.update(a for a in brand_data.get("aliases", []) if a)
        existing = self._find_existing_brand(db, alias_texts)
        if existing:
            self._add_seed_brand_aliases(db, existing.id, name_en, name_zh, brand_data.get("aliases", []))
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

        self._add_seed_brand_aliases(db, brand.id, name_en, name_zh, brand_data.get("aliases", []))

        return brand

    def _store_seed_product(
        self, db: Session, brand: KnowledgeBrand, product_data: dict
    ) -> Optional[KnowledgeProduct]:
        """Store a single product from the seed response."""
        name = product_data.get("name", "")
        if not name:
            return None

        alias_texts = {name}
        alias_texts.update(a for a in product_data.get("aliases", []) if a)
        existing = self._find_existing_product(db, alias_texts)
        if existing:
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

        # Add product aliases
        for alias_text in product_data.get("aliases", []):
            if not alias_text or alias_text == name:
                continue
            existing_alias = (
                db.query(KnowledgeProductAlias)
                .filter(
                    KnowledgeProductAlias.product_id == product.id,
                    KnowledgeProductAlias.alias_key == normalize_entity_key(alias_text),
                )
                .first()
            )
            if not existing_alias:
                db.add(
                    KnowledgeProductAlias(
                        product_id=product.id,
                        alias=alias_text,
                    )
                )

        # Create product-brand mapping
        db.add(
            KnowledgeProductBrandMapping(
                vertical_id=self.vertical_id,
                product_id=product.id,
                brand_id=brand.id,
                is_validated=False,
                source="seed",
            )
        )

        return product

    def _add_brand_aliases(
        self, db: Session, brand_id: int, aliases: dict[str, list[str]]
    ) -> None:
        """Add brand aliases from user brand data format."""
        for lang, alias_list in aliases.items():
            for alias_text in alias_list:
                if not alias_text:
                    continue
                a_key = normalize_entity_key(alias_text)
                existing = (
                    db.query(KnowledgeBrandAlias)
                    .filter(
                        KnowledgeBrandAlias.brand_id == brand_id,
                        KnowledgeBrandAlias.alias_key == a_key,
                    )
                    .first()
                )
                if not existing:
                    db.add(
                        KnowledgeBrandAlias(
                            brand_id=brand_id,
                            alias=alias_text,
                            language=lang,
                        )
                    )

    def _add_seed_brand_aliases(
        self,
        db: Session,
        brand_id: int,
        name_en: str,
        name_zh: str,
        aliases: list[str],
    ) -> None:
        alias_payloads: list[tuple[str, str | None]] = []
        if name_zh:
            alias_payloads.append((name_zh, "zh"))
        if name_en:
            alias_payloads.append((name_en, "en"))
        for alias in aliases:
            if alias and alias not in {name_en, name_zh}:
                alias_payloads.append((alias, None))

        for alias_text, language in alias_payloads:
            existing_alias = (
                db.query(KnowledgeBrandAlias)
                .filter(
                    KnowledgeBrandAlias.brand_id == brand_id,
                    KnowledgeBrandAlias.alias_key == normalize_entity_key(alias_text),
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

    def _find_existing_brand(
        self,
        db: Session,
        alias_texts: set[str],
    ) -> Optional[KnowledgeBrand]:
        alias_keys = {normalize_entity_key(text) for text in alias_texts if text}
        alias_keys.discard("")
        if not alias_keys:
            return None

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
    ) -> Optional[KnowledgeProduct]:
        alias_keys = {normalize_entity_key(text) for text in alias_texts if text}
        alias_keys.discard("")
        if not alias_keys:
            return None

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


def _parse_json_response(text: str) -> Optional[dict[str, Any]]:
    """Extract JSON from a response that may contain markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop first and last lines (fences)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                return None
        return None
