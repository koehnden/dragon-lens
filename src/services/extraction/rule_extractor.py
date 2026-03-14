"""Knowledge-base backed rule extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeProductBrandMapping,
    KnowledgeRejectedEntity,
)
from services.extraction.models import BrandProductPair, ItemExtractionResult, ResponseItem
from services.knowledge_verticals import normalize_entity_key


@dataclass(frozen=True)
class _AliasEntry:
    alias: str
    alias_key: str
    canonical: str
    language: str | None = None


class KnowledgeBaseMatcher:
    """Fast matcher backed by the knowledge DB plus a run-scoped session cache."""

    def __init__(self, vertical_id: int | None, db: Session | None = None):
        self.vertical_id = vertical_id
        self.db = db
        self._brand_entries: list[_AliasEntry] = []
        self._product_entries: list[_AliasEntry] = []
        self._rejected: set[str] = set()
        self._product_brand_map: dict[str, str] = {}

        if vertical_id is not None and db is not None:
            self._load_from_db()

    def _load_from_db(self) -> None:
        brand_rows = (
            self.db.query(KnowledgeBrand)
            .filter(KnowledgeBrand.vertical_id == self.vertical_id)
            .all()
        )
        for brand in brand_rows:
            self._add_brand_entry(brand.canonical_name, brand.display_name)

        alias_rows = (
            self.db.query(
                KnowledgeBrandAlias.alias,
                KnowledgeBrandAlias.language,
                KnowledgeBrand.canonical_name,
            )
            .join(KnowledgeBrand, KnowledgeBrand.id == KnowledgeBrandAlias.brand_id)
            .filter(KnowledgeBrand.vertical_id == self.vertical_id)
            .all()
        )
        for alias, language, canonical in alias_rows:
            self._add_brand_entry(alias, canonical, language=language)

        product_rows = (
            self.db.query(KnowledgeProduct)
            .filter(KnowledgeProduct.vertical_id == self.vertical_id)
            .all()
        )
        for product in product_rows:
            self._add_product_entry(product.canonical_name, product.display_name)

        product_alias_rows = (
            self.db.query(
                KnowledgeProductAlias.alias,
                KnowledgeProductAlias.language,
                KnowledgeProduct.canonical_name,
            )
            .join(KnowledgeProduct, KnowledgeProduct.id == KnowledgeProductAlias.product_id)
            .filter(KnowledgeProduct.vertical_id == self.vertical_id)
            .all()
        )
        for alias, language, canonical in product_alias_rows:
            self._add_product_entry(alias, canonical, language=language)

        rejected_rows = (
            self.db.query(KnowledgeRejectedEntity.alias_key)
            .filter(KnowledgeRejectedEntity.vertical_id == self.vertical_id)
            .all()
        )
        self._rejected = {alias_key for (alias_key,) in rejected_rows if alias_key}

        mapping_rows = (
            self.db.query(
                KnowledgeProduct.canonical_name,
                KnowledgeBrand.canonical_name,
            )
            .join(KnowledgeProductBrandMapping, KnowledgeProductBrandMapping.product_id == KnowledgeProduct.id)
            .join(KnowledgeBrand, KnowledgeBrand.id == KnowledgeProductBrandMapping.brand_id)
            .filter(KnowledgeProductBrandMapping.vertical_id == self.vertical_id)
            .all()
        )
        for product_name, brand_name in mapping_rows:
            if product_name and brand_name:
                self._product_brand_map[product_name] = brand_name

    def match_item(self, item: ResponseItem) -> ItemExtractionResult:
        brands = self._match_entries(item.text, self._brand_entries)
        products = self._match_entries(item.text, self._product_entries)
        return ItemExtractionResult(item=item, pairs=self._build_pairs(brands, products))

    def add_to_session(self, brand: str | None, product: str | None) -> None:
        if brand:
            self._add_brand_entry(brand, brand)
        if product:
            self._add_product_entry(product, product)
        if product and brand:
            self._product_brand_map[product] = brand

    def _add_brand_entry(
        self,
        alias: str,
        canonical: str,
        language: str | None = None,
    ) -> None:
        self._append_entry(self._brand_entries, alias, canonical, language)

    def _add_product_entry(
        self,
        alias: str,
        canonical: str,
        language: str | None = None,
    ) -> None:
        self._append_entry(self._product_entries, alias, canonical, language)

    def _append_entry(
        self,
        entries: list[_AliasEntry],
        alias: str,
        canonical: str,
        language: str | None = None,
    ) -> None:
        alias = (alias or "").strip()
        canonical = (canonical or "").strip()
        if not alias or not canonical:
            return

        entry = _AliasEntry(
            alias=alias,
            alias_key=normalize_entity_key(alias),
            canonical=canonical,
            language=language,
        )
        if entry in entries:
            return
        entries.append(entry)
        entries.sort(key=lambda item: len(item.alias), reverse=True)

    def _match_entries(
        self,
        text: str,
        entries: Iterable[_AliasEntry],
    ) -> list[str]:
        matched: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            if entry.alias_key in self._rejected:
                continue
            if not _contains_alias(text, entry.alias):
                continue
            if entry.canonical in seen:
                continue
            matched.append(entry.canonical)
            seen.add(entry.canonical)
        return matched

    def _build_pairs(
        self,
        brands: list[str],
        products: list[str],
    ) -> list[BrandProductPair]:
        pairs: list[BrandProductPair] = []
        used_brands: set[str] = set()
        used_products: set[str] = set()

        for product in products:
            mapped_brand = self._product_brand_map.get(product)
            if mapped_brand:
                pairs.append(
                    BrandProductPair(
                        brand=mapped_brand,
                        product=product,
                        brand_source="kb",
                        product_source="kb",
                    )
                )
                used_products.add(product)
                used_brands.add(mapped_brand)

        unmatched_brands = [brand for brand in brands if brand not in used_brands]
        unmatched_products = [product for product in products if product not in used_products]

        for brand, product in zip(unmatched_brands, unmatched_products):
            pairs.append(
                BrandProductPair(
                    brand=brand,
                    product=product,
                    brand_source="kb",
                    product_source="kb",
                )
            )
            used_brands.add(brand)
            used_products.add(product)

        for brand in unmatched_brands[len(unmatched_products) :]:
            pairs.append(
                BrandProductPair(
                    brand=brand,
                    product=None,
                    brand_source="kb",
                    product_source="",
                )
            )

        for product in unmatched_products[len(unmatched_brands) :]:
            pairs.append(
                BrandProductPair(
                    brand=None,
                    product=product,
                    brand_source="",
                    product_source="kb",
                )
            )

        return pairs


def _contains_alias(text: str, alias: str) -> bool:
    alias = (alias or "").strip()
    if not alias:
        return False

    haystack = text or ""
    if _looks_ascii(alias):
        pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", re.IGNORECASE)
        return bool(pattern.search(haystack))
    return alias.casefold() in haystack.casefold()


def _looks_ascii(text: str) -> bool:
    return bool(text) and all(ord(char) < 128 for char in text)
