"""Batched Qwen extraction for list items."""

from __future__ import annotations

import json
import re
from collections import OrderedDict

from sqlalchemy.orm import Session

from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeRejectedEntity,
)
from prompts.loader import load_prompt
from services.extraction.models import BrandProductPair, ItemExtractionResult, ResponseItem

MAX_BATCH_ITEMS = 10
MAX_REJECTED_PER_TYPE = 20
MAX_VALIDATED_PER_TYPE = 50


class QwenBatchExtractor:
    """Extract brand/product pairs from item batches using Qwen."""

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

    async def extract_batch(
        self,
        items: list[ResponseItem],
        intro_context: str | None = None,
    ) -> list[ItemExtractionResult]:
        if not items:
            return []

        from services.ollama import OllamaService

        augmentation = self._load_augmentation()
        items_payload = json.dumps(
            [
                {
                    "item_index": index,
                    "response_id": item.response_id,
                    "text": item.text,
                }
                for index, item in enumerate(items)
            ],
            ensure_ascii=False,
        )
        intro_context_section = ""
        if intro_context:
            intro_context_section = f"CONTEXT:\n{intro_context.strip()}\n"

        system_prompt = load_prompt(
            "extraction/qwen_item_extraction",
            vertical=self.vertical,
            vertical_description=self.vertical_description,
            intro_context_section=intro_context_section,
            items_json=items_payload,
            validated_brands=augmentation["validated_brands"],
            validated_products=augmentation["validated_products"],
            rejected_brands=augmentation["rejected_brands"],
            rejected_products=augmentation["rejected_products"],
        )

        ollama = OllamaService()
        response = await ollama._call_ollama(
            model=ollama.ner_model,
            prompt="Return JSON only.",
            system_prompt=system_prompt,
            temperature=0.0,
        )

        parsed = _parse_qwen_response(response)
        by_index: dict[int, ItemExtractionResult] = {
            index: ItemExtractionResult(item=item)
            for index, item in enumerate(items)
        }

        for row in parsed:
            index = row.get("item_index")
            if index not in by_index:
                continue
            by_index[index].pairs = _pairs_from_row(row)

        return [by_index[index] for index in range(len(items))]

    async def extract_missing(
        self,
        missing_items: list[tuple[ResponseItem, str | None, str | None]],
        intro_contexts: dict[str | None, str],
    ) -> list[ItemExtractionResult]:
        if not missing_items:
            return []

        grouped: OrderedDict[str | None, list[ResponseItem]] = OrderedDict()
        for item, _, _ in missing_items:
            grouped.setdefault(item.response_id, []).append(item)

        batches: list[list[ResponseItem]] = []
        current: list[ResponseItem] = []
        for response_items in grouped.values():
            if current and len(current) + len(response_items) > MAX_BATCH_ITEMS:
                batches.append(current)
                current = []
            if len(response_items) > MAX_BATCH_ITEMS:
                for start in range(0, len(response_items), MAX_BATCH_ITEMS):
                    batches.append(response_items[start : start + MAX_BATCH_ITEMS])
                continue
            current.extend(response_items)
        if current:
            batches.append(current)

        results: list[ItemExtractionResult] = []
        for batch in batches:
            response_ids = {item.response_id for item in batch}
            contexts = [
                intro_contexts[response_id]
                for response_id in response_ids
                if response_id in intro_contexts and intro_contexts[response_id]
            ]
            intro_context = "\n\n".join(dict.fromkeys(contexts))
            results.extend(await self.extract_batch(batch, intro_context or None))
        return results

    def _load_augmentation(self) -> dict[str, list[dict]]:
        if self.knowledge_db is None or self.vertical_id is None:
            return {
                "validated_brands": [],
                "validated_products": [],
                "rejected_brands": [],
                "rejected_products": [],
            }

        validated_brands = (
            self.knowledge_db.query(KnowledgeBrand)
            .filter(
                KnowledgeBrand.vertical_id == self.vertical_id,
                KnowledgeBrand.is_validated == True,
            )
            .order_by(KnowledgeBrand.updated_at.desc())
            .limit(MAX_VALIDATED_PER_TYPE)
            .all()
        )
        validated_products = (
            self.knowledge_db.query(KnowledgeProduct)
            .filter(
                KnowledgeProduct.vertical_id == self.vertical_id,
                KnowledgeProduct.is_validated == True,
            )
            .order_by(KnowledgeProduct.updated_at.desc())
            .limit(MAX_VALIDATED_PER_TYPE)
            .all()
        )
        rejected = (
            self.knowledge_db.query(KnowledgeRejectedEntity)
            .filter(KnowledgeRejectedEntity.vertical_id == self.vertical_id)
            .order_by(KnowledgeRejectedEntity.created_at.desc())
            .limit(MAX_REJECTED_PER_TYPE * 2)
            .all()
        )

        brand_aliases = (
            self.knowledge_db.query(KnowledgeBrandAlias.alias, KnowledgeBrandAlias.brand_id)
            .join(KnowledgeBrand, KnowledgeBrand.id == KnowledgeBrandAlias.brand_id)
            .filter(KnowledgeBrand.vertical_id == self.vertical_id)
            .all()
        )
        aliases_by_brand_id: dict[int, list[str]] = {}
        for alias, brand_id in brand_aliases:
            aliases_by_brand_id.setdefault(brand_id, []).append(alias)

        return {
            "validated_brands": [
                {
                    "display_name": brand.display_name,
                    "aliases": aliases_by_brand_id.get(brand.id, []),
                }
                for brand in validated_brands
            ],
            "validated_products": [
                {"display_name": product.display_name}
                for product in validated_products
            ],
            "rejected_brands": [
                {"name": row.name, "reason": row.reason}
                for row in rejected
                if row.entity_type.value.lower() == "brand"
            ][:MAX_REJECTED_PER_TYPE],
            "rejected_products": [
                {"name": row.name, "reason": row.reason}
                for row in rejected
                if row.entity_type.value.lower() == "product"
            ][:MAX_REJECTED_PER_TYPE],
        }


def _parse_qwen_response(text: str) -> list[dict]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []


def _pairs_from_row(row: dict) -> list[BrandProductPair]:
    if isinstance(row.get("pairs"), list):
        pairs = []
        for pair_row in row["pairs"]:
            pairs.append(
                BrandProductPair(
                    brand=_clean_value(pair_row.get("brand")),
                    product=_clean_value(pair_row.get("product")),
                    brand_source="qwen" if _clean_value(pair_row.get("brand")) else "",
                    product_source="qwen" if _clean_value(pair_row.get("product")) else "",
                )
            )
        return [pair for pair in pairs if pair.brand or pair.product]

    brand = _clean_value(row.get("brand"))
    product = _clean_value(row.get("product"))
    if not brand and not product:
        return []
    return [
        BrandProductPair(
            brand=brand,
            product=product,
            brand_source="qwen" if brand else "",
            product_source="qwen" if product else "",
        )
    ]


def _clean_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "null":
        return None
    return text
