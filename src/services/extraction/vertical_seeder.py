"""Step -1: Cold start seeding for verticals with sparse knowledge bases."""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeProductBrandMapping,
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
        """Check if vertical needs seeding (< 10 validated brands)."""
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
        for brand_data in user_brands:
            display_name = brand_data.get("display_name", "")
            if not display_name:
                continue

            alias_key = normalize_entity_key(display_name)
            existing = (
                db.query(KnowledgeBrand)
                .filter(
                    KnowledgeBrand.vertical_id == self.vertical_id,
                    KnowledgeBrand.alias_key == alias_key,
                )
                .first()
            )
            if existing:
                continue

            brand = KnowledgeBrand(
                vertical_id=self.vertical_id,
                canonical_name=display_name,
                display_name=display_name,
                alias_key=alias_key,
                is_validated=True,
                validation_source="user",
            )
            db.add(brand)
            db.flush()

            aliases = brand_data.get("aliases", {})
            self._add_brand_aliases(db, brand.id, aliases)
            seeded += 1

        if seeded:
            db.flush()
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
        if not self.should_seed(db):
            return

        if user_brands:
            self.seed_from_user_brands(db, user_brands)

        if self.should_seed(db):
            await self.seed_from_deepseek(db)

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

        alias_key = normalize_entity_key(display_name)
        existing = (
            db.query(KnowledgeBrand)
            .filter(
                KnowledgeBrand.vertical_id == self.vertical_id,
                KnowledgeBrand.alias_key == alias_key,
            )
            .first()
        )
        if existing:
            return existing

        brand = KnowledgeBrand(
            vertical_id=self.vertical_id,
            canonical_name=display_name,
            display_name=display_name,
            alias_key=alias_key,
            is_validated=False,
            validation_source="seed",
        )
        db.add(brand)
        db.flush()

        # Add aliases: name_zh, name_en, and extra aliases
        aliases_to_add = []
        if name_zh:
            aliases_to_add.append((name_zh, "zh"))
        if name_en:
            aliases_to_add.append((name_en, "en"))
        for alias in brand_data.get("aliases", []):
            if alias and alias not in (name_en, name_zh):
                aliases_to_add.append((alias, None))

        for alias_text, lang in aliases_to_add:
            a_key = normalize_entity_key(alias_text)
            existing_alias = (
                db.query(KnowledgeBrandAlias)
                .filter(
                    KnowledgeBrandAlias.brand_id == brand.id,
                    KnowledgeBrandAlias.alias_key == a_key,
                )
                .first()
            )
            if not existing_alias:
                db.add(
                    KnowledgeBrandAlias(
                        brand_id=brand.id,
                        alias=alias_text,
                        alias_key=a_key,
                        language=lang,
                    )
                )

        return brand

    def _store_seed_product(
        self, db: Session, brand: KnowledgeBrand, product_data: dict
    ) -> Optional[KnowledgeProduct]:
        """Store a single product from the seed response."""
        name = product_data.get("name", "")
        if not name:
            return None

        alias_key = normalize_entity_key(name)
        existing = (
            db.query(KnowledgeProduct)
            .filter(
                KnowledgeProduct.vertical_id == self.vertical_id,
                KnowledgeProduct.alias_key == alias_key,
            )
            .first()
        )
        if existing:
            return existing

        product = KnowledgeProduct(
            vertical_id=self.vertical_id,
            brand_id=brand.id,
            canonical_name=name,
            display_name=name,
            alias_key=alias_key,
            is_validated=False,
            validation_source="seed",
        )
        db.add(product)
        db.flush()

        # Add product aliases
        for alias_text in product_data.get("aliases", []):
            if not alias_text or alias_text == name:
                continue
            a_key = normalize_entity_key(alias_text)
            existing_alias = (
                db.query(KnowledgeProductAlias)
                .filter(
                    KnowledgeProductAlias.product_id == product.id,
                    KnowledgeProductAlias.alias_key == a_key,
                )
                .first()
            )
            if not existing_alias:
                db.add(
                    KnowledgeProductAlias(
                        product_id=product.id,
                        alias=alias_text,
                        alias_key=a_key,
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
                            alias_key=a_key,
                            language=lang,
                        )
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
